using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using HopitalApi.Controllers;
using HopitalApi.Data;
using HopitalApi.Models;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Services.Recherche;

public record LigneMessage(int Ligne, string Message);
public record ValeurNonHarmonisee(string Variable, string ValeurBrute, int Occurrences);

public record RapportImport(
    bool Apercu, int? LotId, string Registre, string NomFichier,
    int LignesLues, int LignesImportees, int LignesRejetees, int Doublons, int SortiesCalculees,
    List<string> ColonnesReconnues, List<string> ColonnesIgnorees, List<string> ColonnesIdentifiantesIgnorees,
    List<LigneMessage> Erreurs, List<LigneMessage> Avertissements, List<ValeurNonHarmonisee> NonHarmonisees,
    DateOnly? PremiereDate, DateOnly? DerniereDate);

public class ImportException : Exception { public ImportException(string m) : base(m) { } }

/// <summary>
/// Import d'un registre (CSV) d'un hôpital dans le dataset harmonisé.
///
/// La déclaration des colonnes de l'hôpital dit quelle colonne porte quelle
/// variable ; les correspondances disent quelle valeur brute devient quelle valeur
/// harmonisée. Rien n'est deviné : une valeur illisible est rejetée ou laissée nulle
/// et signalée dans le rapport, ligne par ligne. Les colonnes identifiantes (nom,
/// prénom, téléphone) ne sont jamais lues.
/// </summary>
public class ImportRegistreService
{
    const int MaxMessages = 300;
    // Au-delà, une durée est une erreur d'écriture (même seuil que NERA : nera/chargement.py, max_nuits).
    const int DureeMaxNuits = 90;
    readonly AppDbContext _db;
    public ImportRegistreService(AppDbContext db) => _db = db;

    // ── Contexte d'harmonisation d'un hôpital ─────────────────────────────

    /// <summary>Tout ce qu'il faut pour harmoniser les valeurs d'un hôpital.</summary>
    public class Contexte
    {
        public required int EtablissementId { get; init; }
        public required Dictionary<(string Var, string Cle), string> Correspondances { get; init; }
        public required string[] Diagnostics { get; init; }
        public required string[] Motifs { get; init; }
        public required List<Service> Services { get; init; }

        public string[] Autorisees(VariableHarmonisee v) =>
            v.Valeurs ?? (v.ListeParametre == Dictionnaire.ListeDiagnostics ? Diagnostics
                : v.ListeParametre == Dictionnaire.ListeMotifs ? Motifs : Array.Empty<string>());

        /// <summary>Valeur harmonisée, ou null si aucune correspondance n'existe.</summary>
        public string? Normaliser(VariableHarmonisee v, string? brut)
        {
            var cle = Dictionnaire.Cle(brut);
            if (cle.Length == 0) return null;
            var directe = Autorisees(v).FirstOrDefault(a => Dictionnaire.Cle(a) == cle);
            if (directe is not null) return directe;
            return Correspondances.TryGetValue((Dictionnaire.GroupeCorrespondance(v.Code), cle), out var n) ? n : null;
        }

        public Service? Service(string? brut)
        {
            var cle = Dictionnaire.Cle(brut);
            if (cle.Length == 0) return null;
            var s = Services.FirstOrDefault(x => Dictionnaire.Cle(x.Code) == cle || Dictionnaire.Cle(x.Nom) == cle);
            if (s is not null) return s;
            return Correspondances.TryGetValue(("service", cle), out var code)
                ? Services.FirstOrDefault(x => x.Code == code) : null;
        }
    }

    public async Task<Contexte> ContexteAsync(int etablissementId)
    {
        var parametres = await _db.Parametres.AsNoTracking().ToListAsync();
        var motifsRegles = await _db.ReglesOrientation.Select(r => r.Motif).Distinct().ToListAsync();
        return new Contexte
        {
            EtablissementId = etablissementId,
            Correspondances = (await _db.Correspondances.AsNoTracking()
                    .Where(c => c.EtablissementId == etablissementId).ToListAsync())
                .ToDictionary(c => (c.VariableCode, c.Cle), c => c.ValeurNormalisee),
            Diagnostics = ReferentielsController.Liste(parametres, Dictionnaire.ListeDiagnostics),
            Motifs = motifsRegles.Concat(ReferentielsController.Liste(parametres, Dictionnaire.ListeMotifs))
                .Distinct().OrderBy(m => m).ToArray(),
            Services = await _db.Services.AsNoTracking().Where(s => s.EtablissementId == etablissementId).ToListAsync()
        };
    }

    // ── Lecture du fichier ────────────────────────────────────────────────

    static string Decoder(byte[] octets)
    {
        try { return new UTF8Encoding(false, true).GetString(octets).TrimStart('﻿'); }
        // Excel « CSV (séparateur : point-virgule) » enregistre en Windows-1252.
        catch (DecoderFallbackException) { return Encoding.GetEncoding(1252).GetString(octets); }
    }

    static List<List<string>> LireCsv(string texte)
    {
        var premiere = texte.Split('\n').FirstOrDefault(l => l.Trim().Length > 0) ?? "";
        var sep = new[] { ';', ',', '\t' }.OrderByDescending(c => premiere.Count(x => x == c)).First();

        var lignes = new List<List<string>>();
        var ligne = new List<string>();
        var champ = new StringBuilder();
        var guillemets = false;
        for (var i = 0; i < texte.Length; i++)
        {
            var c = texte[i];
            if (guillemets)
            {
                if (c == '"' && i + 1 < texte.Length && texte[i + 1] == '"') { champ.Append('"'); i++; }
                else if (c == '"') guillemets = false;
                else champ.Append(c);
            }
            else if (c == '"') guillemets = true;
            else if (c == sep) { ligne.Add(champ.ToString()); champ.Clear(); }
            else if (c == '\n' || c == '\r')
            {
                if (c == '\r' && i + 1 < texte.Length && texte[i + 1] == '\n') i++;
                ligne.Add(champ.ToString()); champ.Clear();
                lignes.Add(ligne); ligne = new List<string>();
            }
            else champ.Append(c);
        }
        if (champ.Length > 0 || ligne.Count > 0) { ligne.Add(champ.ToString()); lignes.Add(ligne); }
        return lignes;
    }

    // ── Import ────────────────────────────────────────────────────────────

    public async Task<RapportImport> ImporterAsync(int etablissementId, string registre, int? serviceParDefautId,
        string nomFichier, byte[] contenu, bool apercu, string? auteur)
    {
        if (!Dictionnaire.Registres.Contains(registre)) throw new ImportException("Registre inconnu.");
        if (!await _db.Etablissements.AnyAsync(e => e.Id == etablissementId)) throw new ImportException("Hôpital inconnu.");

        var declarations = await _db.ColonnesSource.AsNoTracking()
            .Where(c => c.EtablissementId == etablissementId && c.Registre == registre).ToListAsync();
        var mappees = declarations.Where(d => !string.IsNullOrWhiteSpace(d.NomColonne)).ToList();
        if (mappees.Count == 0)
            throw new ImportException("Déclarez d'abord les colonnes de ce registre pour cet hôpital (onglet Harmonisation).");

        var requise = Dictionnaire.DuRegistre(registre).First(v => v.Requise);
        if (mappees.All(d => d.VariableCode != requise.Code))
            throw new ImportException($"La variable « {requise.Libelle} » doit être reliée à une colonne du registre.");

        var ctx = await ContexteAsync(etablissementId);
        Service? serviceDefaut = null;
        if (serviceParDefautId is int sid)
        {
            serviceDefaut = ctx.Services.FirstOrDefault(s => s.Id == sid)
                ?? throw new ImportException("Le service choisi n'appartient pas à cet hôpital.");
        }
        if (serviceDefaut is null && mappees.All(d => d.VariableCode != "service"))
            throw new ImportException("Ce registre n'a pas de colonne « service » : choisissez le service du fichier.");

        var lignes = LireCsv(Decoder(contenu)).Where(l => l.Any(c => c.Trim().Length > 0)).ToList();
        if (lignes.Count < 2) throw new ImportException("Le fichier ne contient pas de ligne de données sous l'en-tête.");

        var entete = lignes[0].Select(h => h.Trim()).ToList();
        var index = new Dictionary<string, int>();
        var manquantes = new List<string>();
        foreach (var d in mappees)
        {
            var i = entete.FindIndex(h => Dictionnaire.Cle(h) == Dictionnaire.Cle(d.NomColonne));
            if (i < 0) manquantes.Add(d.NomColonne!);
            else index[d.VariableCode] = i;
        }
        if (manquantes.Count > 0)
            throw new ImportException($"Colonne(s) déclarée(s) absente(s) du fichier : {string.Join(", ", manquantes)}. " +
                "Vérifiez qu'il s'agit bien du registre de cet hôpital.");

        var utilisees = index.Values.ToHashSet();
        var identifiantes = entete.Where((h, i) => !utilisees.Contains(i) && Dictionnaire.EstIdentifiant(h)).ToList();
        var ignorees = entete.Where((h, i) => !utilisees.Contains(i) && !Dictionnaire.EstIdentifiant(h) && h.Length > 0).ToList();

        var uniteFixe = declarations.FirstOrDefault(d => d.VariableCode == "age_unite")?.ValeurFixe;
        var erreurs = new List<LigneMessage>();
        var avert = new List<LigneMessage>();
        var nonHarm = new Dictionary<(string, string), int>();
        void Erreur(int l, string m) { if (erreurs.Count < MaxMessages) erreurs.Add(new(l, m)); }
        void Avert(int l, string m) { if (avert.Count < MaxMessages) avert.Add(new(l, m)); }
        void NonHarm(string v, string? brut)
        {
            if (string.IsNullOrWhiteSpace(brut)) return;
            var k = (v, brut.Trim());
            nonHarm[k] = nonHarm.GetValueOrDefault(k) + 1;
        }

        var aujourdhui = DateOnly.FromDateTime(DateTime.UtcNow);
        var existantes = registre == Dictionnaire.Hospitalisation
            ? (await _db.Hospitalisations.AsNoTracking().Where(h => h.EtablissementId == etablissementId)
                .ToListAsync()).Select(CleDoublon).ToHashSet()
            : (await _db.Consultations.AsNoTracking().Where(h => h.EtablissementId == etablissementId)
                .ToListAsync()).Select(CleDoublon).ToHashSet();

        var hosp = new List<EnregistrementHospitalisation>();
        var cons = new List<EnregistrementConsultation>();
        int rejetees = 0, doublons = 0, sortiesCalculees = 0;

        for (var n = 1; n < lignes.Count; n++)
        {
            var numero = n + 1; // numéro de ligne tel qu'Excel l'affiche
            var cellules = lignes[n];
            string? Val(string code) => index.TryGetValue(code, out var i) && i < cellules.Count
                ? (cellules[i].Trim() is { Length: > 0 } t ? t : null) : null;
            var ok = true;
            void Rejet(string m) { Erreur(numero, m); ok = false; }

            // Champs communs aux deux registres
            var svcBrut = Val("service");
            var service = svcBrut is null ? serviceDefaut : ctx.Service(svcBrut);
            if (svcBrut is not null && service is null) NonHarm("service", svcBrut);

            var (ageVal, ageUnite) = Dictionnaire.LireAge(Val("age"));
            if (Val("age") is { } ageBrut && ageVal is null) Avert(numero, $"Âge illisible « {ageBrut} » : laissé vide.");
            if (Val("age_unite") is { } uBrut)
            {
                var u = Dictionnaire.LireUnite(uBrut) ?? ctx.Normaliser(Dictionnaire.Trouver(registre, "age_unite")!, uBrut);
                if (u is null) NonHarm("age_unite", uBrut);
                ageUnite = u ?? ageUnite;
            }
            ageUnite ??= uniteFixe;
            var ageMois = Dictionnaire.AgeEnMois(ageVal, ageUnite);
            if (ageVal is not null && ageUnite is null) Avert(numero, "Unité de l'âge inconnue : âge en mois non calculé.");
            if (ageMois is > 130 * 12) { Avert(numero, $"Âge invraisemblable ({ageVal} {ageUnite}) : laissé vide."); ageVal = null; ageMois = null; }

            var sexeBrut = Val("sexe");
            var sexe = ctx.Normaliser(Dictionnaire.Trouver(registre, "sexe")!, sexeBrut);
            if (sexeBrut is not null && sexe is null) NonHarm("sexe", sexeBrut);

            double? Borner(string code, double v)
            {
                var (min, max) = Dictionnaire.Bornes[code];
                if (v >= min && v <= max) return v;
                Avert(numero, $"{Dictionnaire.Trouver(registre, code)!.Libelle} hors plage physiologique ({v}) : laissé vide.");
                return null;
            }
            double? Mesure(string code)
            {
                var b = Val(code);
                if (b is null) return null;
                var v = Dictionnaire.LireNombre(b);
                if (v is null) { Avert(numero, $"{Dictionnaire.Trouver(registre, code)!.Libelle} illisible « {b} » : laissé vide."); return null; }
                return Borner(code, v.Value);
            }
            int? Entier(string code) => Mesure(code) is double x ? (int)Math.Round(x) : null;
            var fc = Entier("fc"); var fr = Entier("fr"); var spo2 = Entier("spo2");
            var temp = Mesure("temperature"); var poids = Mesure("poids");
            int? pas = null, pad = null;
            if (Val("pas") is { } tBrut)
            {
                var (s1, d1, cmhg) = Dictionnaire.LireTension(tBrut);
                if (cmhg) Avert(numero, $"Tension « {tBrut} » notée en cmHg, convertie en {s1}/{d1} mmHg.");
                pas = s1 is int a ? (Borner("pas", a) is double x ? (int)x : null) : null;
                pad = d1 is int b ? (Borner("pad", b) is double y ? (int)y : null) : null;
                if (s1 is null) Avert(numero, $"Tension illisible « {tBrut} » : laissée vide.");
            }
            if (Val("pad") is not null) pad = Entier("pad");

            if (registre == Dictionnaire.Hospitalisation)
            {
                // Une date suivie de « ? » (doute à la transcription : « 23/12/24 ? ») reste lue, avec un avertissement.
                DateOnly? LireDateDouteuse(string champ)
                {
                    var brut = Val(champ);
                    var d = Dictionnaire.LireDate(brut);
                    if (d is null && brut is not null && Dictionnaire.LireDate(Regex.Replace(brut, @"\s*\?+\s*$", "")) is { } d2)
                    {
                        Avert(numero, $"{champ} « {brut} » lue comme {d2:dd/MM/yyyy} (doute à la transcription).");
                        return d2;
                    }
                    return d;
                }
                // Nombre de jours : une date ou un prix recopié dans cette case (« 31/12/24 », « 22500 ») est ignoré.
                var djBrut = Val("duree_jours");
                int? duree = djBrut is not null && !djBrut.Contains('/') && Dictionnaire.LireNombre(djBrut) is double dj ? (int)Math.Round(dj) : null;
                if (duree is < 0) { Avert(numero, $"Nombre de jours négatif ({duree}) : laissé vide."); duree = null; }
                if (duree > DureeMaxNuits || (djBrut is not null && djBrut.Contains('/')))
                { Avert(numero, $"Nombre de jours aberrant « {djBrut} » (date ou prix recopié ?) : laissé vide."); duree = null; }

                DateOnly? enregistrement = null;
                if (Val("date_enregistrement") is { } dBrut)
                {
                    enregistrement = LireDateDouteuse("date_enregistrement");
                    if (enregistrement is null) Avert(numero, $"Date d'enregistrement illisible « {dBrut} » : laissée vide.");
                }
                DateOnly? sortie = null;
                if (Val("date_sortie") is { } sBrut)
                {
                    sortie = LireDateDouteuse("date_sortie");
                    // Une sortie illisible n'est pas une sortie absente : elle est recalculée avec le nombre de jours
                    // s'il est lu ; sinon le séjour garde une durée inconnue (NERA l'exclut ou l'estime), sans être rejeté.
                    if (sortie is null)
                        Avert(numero, $"Date de sortie illisible « {sBrut} » : " + (duree is null ? "durée inconnue." : "recalculée avec le nombre de jours."));
                }
                var entree = LireDateDouteuse("date_entree");
                // Date d'entrée illisible (« 0?/03/25 ») : sortie − nombre de jours si les deux sont lus, sans dépasser
                // la date d'enregistrement ; sinon la date d'enregistrement (le plus souvent le jour même ou la veille).
                if (entree is null && enregistrement is not null)
                {
                    var deduite = sortie is not null && duree is not null ? sortie.Value.AddDays(-duree.Value) : (DateOnly?)null;
                    entree = deduite is not null && deduite <= enregistrement && deduite >= enregistrement.Value.AddDays(-DureeMaxNuits)
                        ? deduite : enregistrement;
                    Avert(numero, $"Date d'entrée illisible « {Val("date_entree")} » : prise au {entree:dd/MM/yyyy} "
                        + (entree == deduite && deduite != enregistrement ? "(sortie − nombre de jours)." : "(date d'enregistrement)."));
                }
                if (entree is null) Rejet($"Date d'entrée absente ou illisible « {Val("date_entree")} », sans date d'enregistrement.");
                if (entree is not null && sortie is not null && sortie < entree) Rejet("Date de sortie antérieure à la date d'entrée.");
                if (entree is not null && sortie is not null && sortie.Value.DayNumber - entree.Value.DayNumber > DureeMaxNuits)
                { Avert(numero, $"Séjour de plus de {DureeMaxNuits} nuits ({entree:dd/MM/yyyy} → {sortie:dd/MM/yyyy}) : sortie laissée vide."); sortie = null; }
                if (entree is not null && enregistrement is not null && enregistrement < entree)
                    Avert(numero, $"Enregistrée le {enregistrement:dd/MM/yyyy}, avant l'admission du {entree:dd/MM/yyyy}.");
                var calculee = false;
                if (ok && duree is not null && entree is not null && sortie is not null)
                {
                    var ecart = sortie.Value.DayNumber - entree.Value.DayNumber;
                    if (Math.Abs(duree.Value - ecart) > 1)
                        Avert(numero, $"Durée déclarée {duree} j, écart entre les dates {ecart} j.");
                }
                // Sortie non écrite : déduite du nombre de jours du registre, et marquée comme telle.
                if (ok && sortie is null && duree is not null && entree is not null)
                {
                    sortie = entree.Value.AddDays(duree.Value);
                    calculee = true;
                }
                if (entree > aujourdhui || sortie > aujourdhui) Rejet("Date postérieure à aujourd'hui.");

                var anBrut = Val("ancien_nouveau");
                var ancienNouveau = Dictionnaire.LireAncienNouveau(anBrut)
                    ?? ctx.Normaliser(Dictionnaire.Trouver(registre, "ancien_nouveau")!, anBrut);
                if (ancienNouveau is null) NonHarm("ancien_nouveau", anBrut);
                var geBrut = Val("ge_tdr");
                var (geLu, densite) = Dictionnaire.LireGe(geBrut);
                var ge = geLu ?? ctx.Normaliser(Dictionnaire.Trouver(registre, "ge_tdr")!, geBrut);
                if (ge is null) NonHarm("ge_tdr", geBrut);

                var vDiag = Dictionnaire.Trouver(registre, "diagnostic_entree")!;
                var vDiagS = Dictionnaire.Trouver(registre, "diagnostic_sortie")!;
                var vIssue = Dictionnaire.Trouver(registre, "issue")!;
                var diag = ctx.Normaliser(vDiag, Val("diagnostic_entree"));
                if (diag is null) NonHarm("diagnostic_entree", Val("diagnostic_entree"));
                var diagS = ctx.Normaliser(vDiagS, Val("diagnostic_sortie"));
                if (diagS is null) NonHarm("diagnostic_sortie", Val("diagnostic_sortie"));
                var issue = ctx.Normaliser(vIssue, Val("issue"));
                if (issue is null) NonHarm("issue", Val("issue"));
                if (issue is not null && sortie is null) Avert(numero, $"Issue « {issue} » sans date de sortie.");

                decimal? prix = Dictionnaire.LireNombre(Val("prix")) is double px ? (decimal)px : null;
                if (Val("prix") is { } pBrut && prix is null) Avert(numero, $"Prix illisible « {pBrut} » : laissé vide.");

                if (!ok) { rejetees++; continue; }
                var e = new EnregistrementHospitalisation
                {
                    EtablissementId = etablissementId, ServiceId = service?.Id, NumeroLigne = numero,
                    IdAnonyme = Val("id_anonyme"), ServiceBrut = svcBrut, DateEnregistrement = enregistrement,
                    DateEntree = entree!.Value, DateSortie = sortie, DateSortieCalculee = calculee, DureeJoursDeclaree = duree,
                    AncienNouveauBrut = anBrut, AncienNouveau = ancienNouveau,
                    GeTdrBrut = geBrut, GeTdr = ge, DensiteParasitaire = densite,
                    Temperature = temp, Fc = fc, Fr = fr, Spo2 = spo2, Poids = poids, Pas = pas, Pad = pad,
                    AgeValeur = ageVal, AgeUnite = ageUnite, AgeMois = ageMois,
                    SexeBrut = sexeBrut, Sexe = sexe, Quartier = Val("quartier"),
                    DiagnosticEntreeBrut = Val("diagnostic_entree"), DiagnosticEntree = diag,
                    Bilan = Val("bilan"), TraitementInitial = Val("traitement_initial"),
                    DiagnosticSortieBrut = Val("diagnostic_sortie"), DiagnosticSortie = diagS,
                    TraitementSortie = Val("traitement_sortie"),
                    IssueBrute = Val("issue"), Issue = issue, Prix = prix
                };
                if (!existantes.Add(CleDoublon(e))) { doublons++; continue; }
                if (calculee) sortiesCalculees++;
                hosp.Add(e);
            }
            else
            {
                var date = Dictionnaire.LireDate(Val("date"));
                if (date is null) Rejet($"Date absente ou illisible « {Val("date")} ».");
                if (date > aujourdhui) Rejet("Date postérieure à aujourd'hui.");


                var vMotif = Dictionnaire.Trouver(registre, "symptomes")!;
                var vOrient = Dictionnaire.Trouver(registre, "orientation")!;
                var motif = ctx.Normaliser(vMotif, Val("symptomes"));
                if (motif is null) NonHarm("symptomes", Val("symptomes"));
                var orient = ctx.Normaliser(vOrient, Val("orientation"));
                if (orient is null) NonHarm("orientation", Val("orientation"));


                if (!ok) { rejetees++; continue; }
                var e = new EnregistrementConsultation
                {
                    EtablissementId = etablissementId, ServiceId = service?.Id, NumeroLigne = numero,
                    IdAnonyme = Val("id_anonyme"), ServiceBrut = svcBrut, Date = date!.Value,
                    AgeValeur = ageVal, AgeUnite = ageUnite, AgeMois = ageMois,
                    SexeBrut = sexeBrut, Sexe = sexe, Quartier = Val("quartier"),
                    SymptomesBrut = Val("symptomes"), Motif = motif,
                    Fc = fc, Pas = pas, Pad = pad, Fr = fr, Temperature = temp, Spo2 = spo2, Poids = poids,
                    OrientationBrute = Val("orientation"), Orientation = orient
                };
                if (!existantes.Add(CleDoublon(e))) { doublons++; continue; }
                cons.Add(e);
            }
        }

        var dates = registre == Dictionnaire.Hospitalisation ? hosp.Select(h => h.DateEntree) : cons.Select(c => c.Date);
        var listeDates = dates.ToList();
        var rapport = new RapportImport(apercu, null, registre, nomFichier,
            lignes.Count - 1, hosp.Count + cons.Count, rejetees, doublons, sortiesCalculees,
            index.Keys.ToList(), ignorees, identifiantes, erreurs, avert,
            nonHarm.Select(kv => new ValeurNonHarmonisee(kv.Key.Item1, kv.Key.Item2, kv.Value))
                .OrderBy(v => v.Variable).ThenByDescending(v => v.Occurrences).ToList(),
            listeDates.Count > 0 ? listeDates.Min() : null, listeDates.Count > 0 ? listeDates.Max() : null);

        if (apercu || rapport.LignesImportees == 0) return rapport;

        await using var tx = await _db.Database.BeginTransactionAsync();
        var lot = new LotImport
        {
            EtablissementId = etablissementId, Registre = registre, ServiceParDefautId = serviceDefaut?.Id,
            NomFichier = nomFichier, ImportePar = auteur, LignesLues = rapport.LignesLues,
            LignesImportees = rapport.LignesImportees, LignesRejetees = rejetees, Doublons = doublons
        };
        _db.LotsImport.Add(lot);
        await _db.SaveChangesAsync();
        foreach (var h in hosp) h.LotImportId = lot.Id;
        foreach (var c in cons) c.LotImportId = lot.Id;
        _db.Hospitalisations.AddRange(hosp);
        _db.Consultations.AddRange(cons);
        rapport = rapport with { LotId = lot.Id };
        lot.RapportJson = JsonSerializer.Serialize(rapport, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        await _db.SaveChangesAsync();
        await tx.CommitAsync();
        return rapport;
    }

    /// <summary>Même séjour déjà présent : même identifiant, même service, même date (ou même empreinte sans identifiant).</summary>
    static string CleDoublon(EnregistrementHospitalisation h) => string.IsNullOrWhiteSpace(h.IdAnonyme)
        ? $"~|{h.ServiceId}|{h.DateEntree}|{h.DateSortie}|{h.AgeValeur}|{h.SexeBrut}|{Dictionnaire.Cle(h.DiagnosticEntreeBrut)}"
        : $"{Dictionnaire.Cle(h.IdAnonyme)}|{h.ServiceId}|{h.DateEntree}";

    static string CleDoublon(EnregistrementConsultation c) => string.IsNullOrWhiteSpace(c.IdAnonyme)
        ? $"~|{c.ServiceId}|{c.Date}|{c.AgeValeur}|{c.SexeBrut}|{Dictionnaire.Cle(c.SymptomesBrut)}|{c.Fc}|{c.Pas}|{c.Poids}"
        : $"{Dictionnaire.Cle(c.IdAnonyme)}|{c.ServiceId}|{c.Date}";

    // ── Réharmonisation après ajout d'une correspondance ──────────────────

    /// <summary>Réapplique les correspondances aux lignes déjà importées de l'hôpital. Renvoie le nombre de lignes modifiées.</summary>
    public async Task<int> ReharmoniserAsync(int etablissementId)
    {
        var ctx = await ContexteAsync(etablissementId);
        var vh = Dictionnaire.DuRegistre(Dictionnaire.Hospitalisation).ToDictionary(v => v.Code);
        var vc = Dictionnaire.DuRegistre(Dictionnaire.Consultation).ToDictionary(v => v.Code);
        var modifiees = 0;

        foreach (var h in await _db.Hospitalisations.Where(x => x.EtablissementId == etablissementId).ToListAsync())
        {
            var avant = (h.ServiceId, h.Sexe, h.DiagnosticEntree, h.DiagnosticSortie, h.Issue, h.AncienNouveau, h.GeTdr);
            if (h.ServiceBrut is not null) h.ServiceId = ctx.Service(h.ServiceBrut)?.Id ?? h.ServiceId;
            h.Sexe = ctx.Normaliser(vh["sexe"], h.SexeBrut);
            h.AncienNouveau = Dictionnaire.LireAncienNouveau(h.AncienNouveauBrut) ?? ctx.Normaliser(vh["ancien_nouveau"], h.AncienNouveauBrut);
            h.GeTdr = Dictionnaire.LireGe(h.GeTdrBrut).Resultat ?? ctx.Normaliser(vh["ge_tdr"], h.GeTdrBrut);
            h.DiagnosticEntree = ctx.Normaliser(vh["diagnostic_entree"], h.DiagnosticEntreeBrut);
            h.DiagnosticSortie = ctx.Normaliser(vh["diagnostic_sortie"], h.DiagnosticSortieBrut);
            h.Issue = ctx.Normaliser(vh["issue"], h.IssueBrute);
            if (avant != (h.ServiceId, h.Sexe, h.DiagnosticEntree, h.DiagnosticSortie, h.Issue, h.AncienNouveau, h.GeTdr)) modifiees++;
        }
        foreach (var c in await _db.Consultations.Where(x => x.EtablissementId == etablissementId).ToListAsync())
        {
            var avant = (c.ServiceId, c.Sexe, c.Motif, c.Orientation);
            if (c.ServiceBrut is not null) c.ServiceId = ctx.Service(c.ServiceBrut)?.Id ?? c.ServiceId;
            c.Sexe = ctx.Normaliser(vc["sexe"], c.SexeBrut);
            c.Motif = ctx.Normaliser(vc["symptomes"], c.SymptomesBrut);
            c.Orientation = ctx.Normaliser(vc["orientation"], c.OrientationBrute);
            if (avant != (c.ServiceId, c.Sexe, c.Motif, c.Orientation)) modifiees++;
        }
        await _db.SaveChangesAsync();
        return modifiees;
    }
}
