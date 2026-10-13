using System.Globalization;
using System.Text;
using System.Text.Json;
using HopitalApi.Data;
using HopitalApi.Dtos;
using HopitalApi.Models;
using HopitalApi.Services;
using HopitalApi.Services.Recherche;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

/// <summary>
/// Dataset de recherche multi-hôpitaux : dictionnaire des variables harmonisées,
/// déclaration des colonnes de chaque hôpital, correspondances de valeurs, import
/// des registres, comparaison des hôpitaux et export pour l'entraînement.
/// Tous les chiffres sont calculés sur les lignes réellement importées.
/// </summary>
[ApiController]
[Route("api/recherche")]
[Authorize(Roles = "admin,data,direction")]
public class RechercheController : BaseController
{
    readonly AppDbContext _db;
    readonly AuditService _audit;
    readonly ImportRegistreService _import;
    readonly IndicateursService _indicateurs;
    public RechercheController(AppDbContext db, AuditService audit, ImportRegistreService import, IndicateursService indicateurs)
    { _db = db; _audit = audit; _import = import; _indicateurs = indicateurs; }

    // ── Indicateurs hospitaliers (TOM, DMS, rotation…) ───────────────────

    /// <summary>Indicateurs d'un service, par mois ou par année, sur la période exploitable et avant le verrou.</summary>
    [HttpGet("indicateurs")]
    public async Task<IActionResult> Indicateurs([FromQuery] int etablissementId, [FromQuery] int serviceId, [FromQuery] string par = "mois")
    {
        if (par is not ("mois" or "annee")) return BadRequest(new { message = "par = mois ou annee." });
        return Ok(await _indicateurs.CalculerAsync(etablissementId, serviceId, par));
    }

    // ── Dictionnaire ──────────────────────────────────────────────────────

    [HttpGet("dictionnaire")]
    public async Task<IActionResult> Dictionnaire_()
    {
        var parametres = await _db.Parametres.AsNoTracking().ToListAsync();
        var motifsRegles = await _db.ReglesOrientation.Select(r => r.Motif).Distinct().ToListAsync();
        var diagnostics = ReferentielsController.Liste(parametres, Dictionnaire.ListeDiagnostics);
        var motifs = motifsRegles.Concat(ReferentielsController.Liste(parametres, Dictionnaire.ListeMotifs))
            .Distinct().OrderBy(m => m).ToArray();
        return Ok(new
        {
            registres = Dictionnaire.Registres,
            roles = Dictionnaire.Roles,
            unitesAge = Dictionnaire.UnitesAge,
            variables = Dictionnaire.Variables.Select(v => new
            {
                v.Code, v.Libelle, v.Registre, v.Type, v.Usage, v.Requise, v.Aide, v.Categorielle,
                v.ListeParametre,
                valeurs = v.Valeurs ?? (v.ListeParametre == Dictionnaire.ListeDiagnostics ? diagnostics
                    : v.ListeParametre == Dictionnaire.ListeMotifs ? motifs : null)
            })
        });
    }

    // ── Déclaration des colonnes d'un hôpital ─────────────────────────────

    [HttpGet("etablissements/{id:int}/colonnes")]
    public async Task<IActionResult> Colonnes(int id, [FromQuery] string registre)
    {
        var decl = await _db.ColonnesSource.AsNoTracking()
            .Where(c => c.EtablissementId == id && c.Registre == registre).ToListAsync();
        return Ok(Dictionnaire.DuRegistre(registre).Select(v =>
        {
            var d = decl.FirstOrDefault(x => x.VariableCode == v.Code);
            return new { variableCode = v.Code, nomColonne = d?.NomColonne, valeurFixe = d?.ValeurFixe, note = d?.Note };
        }));
    }

    [HttpPut("etablissements/{id:int}/colonnes"), Authorize(Roles = "admin,data")]
    public async Task<IActionResult> EnregistrerColonnes(int id, ColonnesRegistreDto dto)
    {
        if (!await _db.Etablissements.AnyAsync(e => e.Id == id)) return NotFound(new { message = "Hôpital introuvable." });
        if (!Dictionnaire.Registres.Contains(dto.Registre)) return BadRequest(new { message = "Registre inconnu." });

        var vues = new Dictionary<string, string>();
        foreach (var c in dto.Colonnes)
        {
            var v = Dictionnaire.Trouver(dto.Registre, c.VariableCode);
            if (v is null) return BadRequest(new { message = $"Variable inconnue : {c.VariableCode}." });
            var col = c.NomColonne?.Trim();
            if (string.IsNullOrEmpty(col)) continue;
            if (Dictionnaire.EstIdentifiant(col))
                return BadRequest(new { message = $"« {col} » est une donnée identifiante : elle ne peut pas être importée." });
            if (vues.TryGetValue(Dictionnaire.Cle(col), out var autre))
                return BadRequest(new { message = $"La colonne « {col} » est déjà reliée à « {autre} »." });
            vues[Dictionnaire.Cle(col)] = v.Libelle;
            if (!string.IsNullOrWhiteSpace(c.ValeurFixe) && (v.Code != "age_unite" || !Dictionnaire.UnitesAge.Contains(c.ValeurFixe)))
                return BadRequest(new { message = "Seule l'unité de l'âge (jours, mois, ans) peut être déclarée sans colonne." });
        }

        _db.ColonnesSource.RemoveRange(_db.ColonnesSource.Where(c => c.EtablissementId == id && c.Registre == dto.Registre));
        foreach (var c in dto.Colonnes)
        {
            var col = c.NomColonne?.Trim();
            var fixe = c.VariableCode == "age_unite" && !string.IsNullOrWhiteSpace(c.ValeurFixe) ? c.ValeurFixe : null;
            if (string.IsNullOrEmpty(col) && fixe is null && string.IsNullOrWhiteSpace(c.Note)) continue;
            _db.ColonnesSource.Add(new ColonneSource
            {
                EtablissementId = id, Registre = dto.Registre, VariableCode = c.VariableCode,
                NomColonne = string.IsNullOrEmpty(col) ? null : col, ValeurFixe = fixe, Note = c.Note?.Trim()
            });
        }
        await _db.SaveChangesAsync();
        await _audit.LogAsync("modification", "Déclaration des colonnes d'un registre", $"hôpital {id}", dto.Registre);
        return NoContent();
    }

    // ── Correspondances de valeurs ────────────────────────────────────────

    [HttpGet("etablissements/{id:int}/correspondances")]
    public async Task<IActionResult> Correspondances(int id) =>
        Ok(await _db.Correspondances.AsNoTracking().Where(c => c.EtablissementId == id)
            .OrderBy(c => c.VariableCode).ThenBy(c => c.ValeurBrute)
            .Select(c => new { c.Id, c.VariableCode, c.ValeurBrute, c.ValeurNormalisee }).ToListAsync());

    [HttpPut("etablissements/{id:int}/correspondances"), Authorize(Roles = "admin,data")]
    public async Task<IActionResult> EnregistrerCorrespondance(int id, CorrespondanceDto dto)
    {
        if (!await _db.Etablissements.AnyAsync(e => e.Id == id)) return NotFound(new { message = "Hôpital introuvable." });
        var v = Dictionnaire.Variables.FirstOrDefault(x => x.Code == dto.VariableCode);
        if (v is null) return BadRequest(new { message = "Variable inconnue." });

        string[] autorisees;
        if (v.Type == "service")
            autorisees = await _db.Services.Where(s => s.EtablissementId == id).Select(s => s.Code).ToArrayAsync();
        else if (v.Categorielle || v.Type == "unite_age")
            autorisees = (await _import.ContexteAsync(id)).Autorisees(v);
        else return BadRequest(new { message = $"« {v.Libelle} » est une variable libre : elle n'a pas de correspondance." });

        if (!autorisees.Contains(dto.ValeurNormalisee))
            return BadRequest(new { message = autorisees.Length == 0
                ? $"Aucune valeur harmonisée n'est définie pour « {v.Libelle} » : renseignez d'abord la liste dans Administration."
                : $"« {dto.ValeurNormalisee} » n'est pas une valeur harmonisée de « {v.Libelle} »." });

        var cle = Dictionnaire.Cle(dto.ValeurBrute);
        if (cle.Length == 0) return BadRequest(new { message = "Valeur brute vide." });
        var groupe = Dictionnaire.GroupeCorrespondance(v.Code);
        var c = await _db.Correspondances.FirstOrDefaultAsync(x => x.EtablissementId == id && x.VariableCode == groupe && x.Cle == cle);
        if (c is null) _db.Correspondances.Add(c = new Correspondance { EtablissementId = id, VariableCode = groupe, Cle = cle });
        c.ValeurBrute = dto.ValeurBrute.Trim();
        c.ValeurNormalisee = dto.ValeurNormalisee;
        await _db.SaveChangesAsync();
        var n = await _import.ReharmoniserAsync(id);
        await _audit.LogAsync("modification", "Correspondance de valeur", $"{v.Code} : {c.ValeurBrute}", c.ValeurNormalisee);
        return Ok(new { lignesMisesAJour = n });
    }

    [HttpDelete("correspondances/{cid:int}"), Authorize(Roles = "admin,data")]
    public async Task<IActionResult> SupprimerCorrespondance(int cid)
    {
        var c = await _db.Correspondances.FindAsync(cid);
        if (c is null) return NotFound(new { message = "Correspondance introuvable." });
        _db.Correspondances.Remove(c);
        await _db.SaveChangesAsync();
        var n = await _import.ReharmoniserAsync(c.EtablissementId);
        await _audit.LogAsync("suppression", "Correspondance de valeur", $"{c.VariableCode} : {c.ValeurBrute}");
        return Ok(new { lignesMisesAJour = n });
    }

    /// <summary>Valeurs brutes déjà importées qui n'ont encore aucune valeur harmonisée.</summary>
    [HttpGet("etablissements/{id:int}/non-harmonisees")]
    public async Task<IActionResult> NonHarmonisees(int id)
    {
        var h = await _db.Hospitalisations.AsNoTracking().Where(x => x.EtablissementId == id).ToListAsync();
        var c = await _db.Consultations.AsNoTracking().Where(x => x.EtablissementId == id).ToListAsync();
        var paires = new List<(string Variable, string? Brut, bool Manque)>();
        foreach (var x in h)
        {
            paires.Add(("service", x.ServiceBrut, x.ServiceId is null));
            paires.Add(("sexe", x.SexeBrut, x.Sexe is null));
            paires.Add(("diagnostic_entree", x.DiagnosticEntreeBrut, x.DiagnosticEntree is null));
            paires.Add(("diagnostic_sortie", x.DiagnosticSortieBrut, x.DiagnosticSortie is null));
            paires.Add(("issue", x.IssueBrute, x.Issue is null));
            paires.Add(("ancien_nouveau", x.AncienNouveauBrut, x.AncienNouveau is null));
            paires.Add(("ge_tdr", x.GeTdrBrut, x.GeTdr is null));
        }
        foreach (var x in c)
        {
            paires.Add(("service", x.ServiceBrut, x.ServiceId is null));
            paires.Add(("sexe", x.SexeBrut, x.Sexe is null));
            paires.Add(("symptomes", x.SymptomesBrut, x.Motif is null));
            paires.Add(("orientation", x.OrientationBrute, x.Orientation is null));
        }
        return Ok(paires.Where(p => p.Manque && !string.IsNullOrWhiteSpace(p.Brut))
            .GroupBy(p => (p.Variable, Cle: Dictionnaire.Cle(p.Brut)))
            .Select(g => new { variable = g.Key.Variable, valeurBrute = g.First().Brut!.Trim(), occurrences = g.Count() })
            .OrderBy(x => x.variable).ThenByDescending(x => x.occurrences).ToList());
    }

    // ── Import ────────────────────────────────────────────────────────────

    [HttpPost("import"), Authorize(Roles = "admin,data"), RequestSizeLimit(50_000_000)]
    public async Task<IActionResult> Importer([FromForm] IFormFile fichier, [FromForm] int etablissementId,
        [FromForm] string registre, [FromForm] int? serviceId, [FromForm] bool apercu = true)
    {
        if (fichier is null || fichier.Length == 0) return BadRequest(new { message = "Fichier vide." });
        if (!fichier.FileName.EndsWith(".csv", StringComparison.OrdinalIgnoreCase) && !fichier.FileName.EndsWith(".txt", StringComparison.OrdinalIgnoreCase))
            return BadRequest(new { message = "Format attendu : CSV. Dans Excel : Fichier › Enregistrer sous › CSV (séparateur : point-virgule)." });
        using var ms = new MemoryStream();
        await fichier.CopyToAsync(ms);
        try
        {
            var r = await _import.ImporterAsync(etablissementId, registre, serviceId, fichier.FileName, ms.ToArray(), apercu, UserNom);
            if (!apercu && r.LotId is not null)
                await _audit.LogAsync("creation", "Import d'un registre", fichier.FileName,
                    $"{registre} · {r.LignesImportees} ligne(s) importée(s), {r.LignesRejetees} rejetée(s)");
            return Ok(r);
        }
        catch (ImportException e) { return BadRequest(new { message = e.Message }); }
    }

    [HttpGet("lots")]
    public async Task<IActionResult> Lots([FromQuery] int? etablissementId)
    {
        var q = _db.LotsImport.AsNoTracking().Include(l => l.Etablissement).AsQueryable();
        if (etablissementId is int id) q = q.Where(l => l.EtablissementId == id);
        return Ok(await q.OrderByDescending(l => l.ImporteLe).Select(l => new
        {
            l.Id, l.EtablissementId, etablissement = l.Etablissement!.Nom, l.Registre, l.NomFichier, l.ImporteLe,
            l.ImportePar, l.LignesLues, l.LignesImportees, l.LignesRejetees, l.Doublons
        }).ToListAsync());
    }

    [HttpGet("lots/{id:int}")]
    public async Task<IActionResult> Lot(int id)
    {
        var l = await _db.LotsImport.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id);
        return l is null ? NotFound(new { message = "Lot introuvable." }) : Content(l.RapportJson, "application/json");
    }

    /// <summary>Annule un import : ses lignes sont retirées du dataset.</summary>
    [HttpDelete("lots/{id:int}"), Authorize(Roles = "admin,data")]
    public async Task<IActionResult> SupprimerLot(int id)
    {
        var l = await _db.LotsImport.FindAsync(id);
        if (l is null) return NotFound(new { message = "Lot introuvable." });
        _db.LotsImport.Remove(l);
        await _db.SaveChangesAsync();
        await _audit.LogAsync("suppression", "Annulation d'un import", l.NomFichier, $"{l.LignesImportees} ligne(s) retirée(s)");
        return NoContent();
    }

    // ── Comparaison des hôpitaux et variables communes ────────────────────

    static readonly Dictionary<string, Func<EnregistrementHospitalisation, bool>> RempliH = new()
    {
        ["id_anonyme"] = x => x.IdAnonyme != null, ["service"] = x => x.ServiceId != null,
        ["date_enregistrement"] = x => x.DateEnregistrement != null,
        ["date_entree"] = _ => true, ["date_sortie"] = x => x.DateSortie != null,
        ["ancien_nouveau"] = x => x.AncienNouveau != null, ["ge_tdr"] = x => x.GeTdr != null,
        ["temperature"] = x => x.Temperature != null, ["fc"] = x => x.Fc != null, ["fr"] = x => x.Fr != null,
        ["spo2"] = x => x.Spo2 != null, ["poids"] = x => x.Poids != null, ["pas"] = x => x.Pas != null,
        ["pad"] = x => x.Pad != null,
        ["duree_jours"] = x => x.DureeJoursDeclaree != null, ["age"] = x => x.AgeValeur != null,
        ["age_unite"] = x => x.AgeUnite != null, ["sexe"] = x => x.Sexe != null, ["quartier"] = x => x.Quartier != null,
        ["diagnostic_entree"] = x => x.DiagnosticEntree != null, ["bilan"] = x => x.Bilan != null,
        ["traitement_initial"] = x => x.TraitementInitial != null, ["diagnostic_sortie"] = x => x.DiagnosticSortie != null,
        ["traitement_sortie"] = x => x.TraitementSortie != null, ["issue"] = x => x.Issue != null, ["prix"] = x => x.Prix != null
    };

    static readonly Dictionary<string, Func<EnregistrementConsultation, bool>> RempliC = new()
    {
        ["id_anonyme"] = x => x.IdAnonyme != null, ["service"] = x => x.ServiceId != null, ["date"] = _ => true,
        ["age"] = x => x.AgeValeur != null, ["age_unite"] = x => x.AgeUnite != null, ["sexe"] = x => x.Sexe != null,
        ["quartier"] = x => x.Quartier != null, ["symptomes"] = x => x.Motif != null, ["fc"] = x => x.Fc != null,
        ["pas"] = x => x.Pas != null, ["pad"] = x => x.Pad != null, ["fr"] = x => x.Fr != null,
        ["temperature"] = x => x.Temperature != null, ["spo2"] = x => x.Spo2 != null, ["poids"] = x => x.Poids != null,
        ["orientation"] = x => x.Orientation != null
    };

    static object Couverture(List<DateOnly> dates)
    {
        if (dates.Count == 0) return new { premiere = (DateOnly?)null, derniere = (DateOnly?)null, mois = 0, moisManquants = Array.Empty<string>() };
        var min = dates.Min(); var max = dates.Max();
        var presents = dates.Select(d => d.Year * 12 + d.Month - 1).ToHashSet();
        var manquants = new List<string>();
        for (var m = min.Year * 12 + min.Month - 1; m <= max.Year * 12 + max.Month - 1; m++)
            if (!presents.Contains(m)) manquants.Add($"{m / 12}-{m % 12 + 1:D2}");
        return new { premiere = (DateOnly?)min, derniere = (DateOnly?)max, mois = presents.Count, moisManquants = manquants };
    }

    [HttpGet("comparaison")]
    public async Task<IActionResult> Comparaison()
    {
        var etabs = await _db.Etablissements.AsNoTracking().Where(e => e.Actif).OrderBy(e => e.Id).ToListAsync();
        var decl = await _db.ColonnesSource.AsNoTracking().ToListAsync();
        var services = await _db.Services.AsNoTracking().ToListAsync();
        var hosp = await _db.Hospitalisations.AsNoTracking().ToListAsync();
        var cons = await _db.Consultations.AsNoTracking().ToListAsync();

        // Hôpitaux participants : ceux qui ont un rôle ; à défaut, tous les hôpitaux actifs.
        var participants = etabs.Where(e => e.RoleRecherche != "").Select(e => e.Id).ToList();
        if (participants.Count < 2) participants = etabs.Select(e => e.Id).ToList();

        bool Declaree(int etabId, string registre, string code) => decl.Any(d => d.EtablissementId == etabId
            && d.Registre == registre && Dictionnaire.Couverte(code, d.VariableCode) && (d.NomColonne != null || d.ValeurFixe != null));

        object Registre<T>(int etabId, string registre, List<T> lignes, Func<T, DateOnly> date,
            Func<T, int?> service, Dictionary<string, Func<T, bool>> rempli) => new
        {
            lignes = lignes.Count,
            couverture = Couverture(lignes.Select(date).ToList()),
            parService = lignes.GroupBy(service).Select(g => new
            {
                serviceId = g.Key,
                service = services.FirstOrDefault(s => s.Id == g.Key)?.Nom ?? "non attribué",
                lignes = g.Count(),
                couverture = Couverture(g.Select(date).ToList())
            }).OrderByDescending(x => x.lignes).ToList(),
            variables = Dictionnaire.DuRegistre(registre).Select(v => new
            {
                v.Code,
                declaree = Declaree(etabId, registre, v.Code),
                completude = lignes.Count == 0 ? (double?)null : Math.Round(100.0 * lignes.Count(rempli[v.Code]) / lignes.Count, 1)
            }).ToList()
        };

        var hopitaux = etabs.Select(e => new
        {
            e.Id, e.Code, e.Nom, e.RoleRecherche, participant = participants.Contains(e.Id),
            hospitalisation = Registre(e.Id, Dictionnaire.Hospitalisation, hosp.Where(x => x.EtablissementId == e.Id).ToList(),
                x => x.DateEntree, x => x.ServiceId, RempliH),
            consultation = Registre(e.Id, Dictionnaire.Consultation, cons.Where(x => x.EtablissementId == e.Id).ToList(),
                x => x.Date, x => x.ServiceId, RempliC)
        }).ToList();

        var communes = Dictionnaire.Registres.ToDictionary(r => r, r => Dictionnaire.DuRegistre(r)
            .Where(v => participants.Count > 0 && participants.All(id => Declaree(id, r, v.Code)))
            .Select(v => new { v.Code, v.Libelle, v.Usage }).ToList());

        return Ok(new
        {
            participants,
            roleAttribue = etabs.Any(e => e.RoleRecherche == "Développement") && etabs.Any(e => e.RoleRecherche == "Validation externe"),
            hopitaux,
            communes
        });
    }

    // ── Export pour l'entraînement ────────────────────────────────────────

    /// <summary>
    /// Dataset harmonisé, une ligne par enregistrement, avec l'hôpital et son rôle.
    /// communesSeulement : seules les variables déclarées par tous les hôpitaux participants.
    /// </summary>
    [HttpGet("export.csv"), Authorize(Roles = "admin,data")]
    public async Task<IActionResult> Export([FromQuery] string registre, [FromQuery] bool communesSeulement = true)
    {
        if (!Dictionnaire.Registres.Contains(registre)) return BadRequest(new { message = "Registre inconnu." });
        var etabs = await _db.Etablissements.AsNoTracking().ToDictionaryAsync(e => e.Id);
        var services = await _db.Services.AsNoTracking().ToDictionaryAsync(s => s.Id);
        var decl = await _db.ColonnesSource.AsNoTracking().Where(d => d.Registre == registre).ToListAsync();
        var participants = etabs.Values.Where(e => e.Actif && e.RoleRecherche != "").Select(e => e.Id).ToList();
        if (participants.Count < 2) participants = etabs.Values.Where(e => e.Actif).Select(e => e.Id).ToList();

        var codes = Dictionnaire.DuRegistre(registre).Select(v => v.Code)
            .Where(c => !communesSeulement || participants.All(id => decl.Any(d => d.EtablissementId == id
                && Dictionnaire.Couverte(c, d.VariableCode) && (d.NomColonne != null || d.ValeurFixe != null))))
            .ToList();

        string F(object? o) => o switch
        {
            null => "",
            DateOnly d => d.ToString("yyyy-MM-dd"),
            double x => x.ToString(CultureInfo.InvariantCulture),
            decimal x => x.ToString(CultureInfo.InvariantCulture),
            string s => s.Contains(';') || s.Contains('"') || s.Contains('\n') ? $"\"{s.Replace("\"", "\"\"")}\"" : s,
            _ => Convert.ToString(o, CultureInfo.InvariantCulture) ?? ""
        };

        var sb = new StringBuilder();
        var entete = new List<string> { "hopital", "role", "service_code" };
        if (registre == Dictionnaire.Hospitalisation)
        {
            entete.AddRange(codes.Where(c => c != "service"));
            if (codes.Contains("age")) entete.Add("age_mois");
            if (codes.Contains("ge_tdr")) entete.Add("densite_parasitaire");
            entete.Add("sortie_calculee");
            entete.Add("duree_sejour_jours");
            sb.AppendLine(string.Join(";", entete));
            var lignes = await _db.Hospitalisations.AsNoTracking().Where(x => participants.Contains(x.EtablissementId))
                .OrderBy(x => x.EtablissementId).ThenBy(x => x.DateEntree).ToListAsync();
            foreach (var x in lignes)
            {
                var v = new Dictionary<string, object?>
                {
                    ["id_anonyme"] = x.IdAnonyme, ["date_enregistrement"] = x.DateEnregistrement,
                    ["date_entree"] = x.DateEntree, ["date_sortie"] = x.DateSortie,
                    ["ancien_nouveau"] = x.AncienNouveau, ["ge_tdr"] = x.GeTdr,
                    ["temperature"] = x.Temperature, ["fc"] = x.Fc, ["fr"] = x.Fr, ["spo2"] = x.Spo2,
                    ["poids"] = x.Poids, ["pas"] = x.Pas, ["pad"] = x.Pad,
                    ["duree_jours"] = x.DureeJoursDeclaree, ["age"] = x.AgeValeur, ["age_unite"] = x.AgeUnite,
                    ["sexe"] = x.Sexe, ["quartier"] = x.Quartier, ["diagnostic_entree"] = x.DiagnosticEntree,
                    ["bilan"] = x.Bilan, ["traitement_initial"] = x.TraitementInitial,
                    ["diagnostic_sortie"] = x.DiagnosticSortie, ["traitement_sortie"] = x.TraitementSortie,
                    ["issue"] = x.Issue, ["prix"] = x.Prix
                };
                var cells = new List<string> { F(etabs[x.EtablissementId].Code), F(etabs[x.EtablissementId].RoleRecherche),
                    F(x.ServiceId is int s ? services[s].Code : null) };
                cells.AddRange(codes.Where(c => c != "service").Select(c => F(v[c])));
                if (codes.Contains("age")) cells.Add(F(x.AgeMois));
                if (codes.Contains("ge_tdr")) cells.Add(F(x.DensiteParasitaire));
                cells.Add(x.DateSortieCalculee ? "1" : "0");
                cells.Add(F(x.DateSortie is DateOnly ds ? ds.DayNumber - x.DateEntree.DayNumber : null));
                sb.AppendLine(string.Join(";", cells));
            }
        }
        else
        {
            entete.AddRange(codes.Where(c => c != "service"));
            if (codes.Contains("age")) entete.Add("age_mois");
            sb.AppendLine(string.Join(";", entete));
            var lignes = await _db.Consultations.AsNoTracking().Where(x => participants.Contains(x.EtablissementId))
                .OrderBy(x => x.EtablissementId).ThenBy(x => x.Date).ToListAsync();
            foreach (var x in lignes)
            {
                var v = new Dictionary<string, object?>
                {
                    ["id_anonyme"] = x.IdAnonyme, ["date"] = x.Date, ["age"] = x.AgeValeur, ["age_unite"] = x.AgeUnite,
                    ["sexe"] = x.Sexe, ["quartier"] = x.Quartier, ["symptomes"] = x.Motif, ["fc"] = x.Fc,
                    ["pas"] = x.Pas, ["pad"] = x.Pad, ["fr"] = x.Fr, ["temperature"] = x.Temperature,
                    ["spo2"] = x.Spo2, ["poids"] = x.Poids, ["orientation"] = x.Orientation
                };
                var cells = new List<string> { F(etabs[x.EtablissementId].Code), F(etabs[x.EtablissementId].RoleRecherche),
                    F(x.ServiceId is int s ? services[s].Code : null) };
                cells.AddRange(codes.Where(c => c != "service").Select(c => F(v[c])));
                if (codes.Contains("age")) cells.Add(F(x.AgeMois));
                sb.AppendLine(string.Join(";", cells));
            }
        }
        await _audit.LogAsync("consultation", "Export du dataset harmonisé", registre,
            communesSeulement ? "variables communes" : "toutes les variables");
        return File(Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(sb.ToString())).ToArray(),
            "text/csv", $"dataset-{registre}-{DateTime.UtcNow:yyyy-MM-dd}.csv");
    }
}
