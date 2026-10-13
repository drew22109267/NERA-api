using HopitalApi.Data;
using HopitalApi.Models;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Services.Recherche;

public record LigneIndicateurs(string Periode, int Jours, int Admissions, double Sorties, double JourneesHospitalisation,
    double? Tom, double? TomBas, double? TomHaut, double OccupationMax, int JoursSureffectif, double? Dms, double? RotationLits,
    double? IntervalleRotation, double Deces, double? Mortalite);

/// <summary>Présents à minuit : attendus, et fourchette « tout inclusif » (Bas) – « tout en nuits » (Haut).</summary>
public record PointOccupation(DateOnly Jour, double Presents, double Bas, double Haut);

public record ConventionJours(int Lignes, int Inclusives, int Nuits, int AutresEcarts, double? PartInclusive,
    double PartRetenue, Dictionary<string, double> PartInclusiveParMois, string Conclusion);

public record ResultatIndicateurs(
    int? Lits, string SourceLits, DateOnly Verrou, DateOnly? Debut, DateOnly? Fin,
    string? PremierMoisComplet, int RodageJours, Dictionary<string, double> PartDureeConnueParMois,
    Dictionary<string, int> Statuts, ConventionJours Convention,
    List<LigneIndicateurs> Lignes, List<PointOccupation> Serie, string? Message);

/// <summary>
/// Indicateurs hospitaliers calculés sur les registres importés — mêmes définitions que la chaîne
/// d'analyse du mémoire (backend/modeles/nera) :
///
///   Occupation (recensement de minuit) : un patient compte le jour d si entrée ≤ d &lt; sortie.
///   Journées d'hospitalisation JH = Σ présents ; TOM = JH / (lits × jours) × 100.
///   DMS = durée moyenne (nuits) des séjours terminés dans la période ; rotation = sorties / lits ;
///   intervalle de rotation = (lits × jours − JH) / sorties ; mortalité = décès / sorties × 100.
///
/// Statut de la sortie : écrite (observée), calculée à l'import (entrée + nombre de jours),
/// censurée (pas de sortie, admission récente : encore hospitalisé) ou inconnue (pas de sortie,
/// admission ancienne) — les séjours à sortie inconnue sont exclus du comptage.
///
/// Convention du nombre de jours : selon le médecin, « n jours » veut dire n nuits (sortie = e + n)
/// ou n jours entrée et sortie comprises (sortie = e + n − 1). Pour une sortie calculée, on ne sait pas.
///   p̂  = part de lignes inclusives parmi les sorties écrites (0,5 sans aucune ligne mesurable) ;
///   p_M = (k_M + 10·p̂) / (n_M + 10) pour le mois d'admission M (rapprochée de p̂ si peu de lignes).
///   Occupation attendue : la nuit incertaine e + n − 1 compte pour 1 − p ; la sortie pèse p le jour
///   e + n − 1 et 1 − p le jour e + n. Fourchette : p = 1 (tout inclusif, Bas) et p = 0 (tout en nuits, Haut).
///
/// Période exploitable : premier mois à partir duquel chaque mois a ≥ 90 % de durées connues,
/// plus un rodage (95e centile des durées, au moins 14 jours).
/// Coffre-fort : rien n'est compté à partir de la date du verrou (période de test final).
/// </summary>
public class IndicateursService
{
    const double PseudoLignes = 10;
    readonly AppDbContext _db;
    public IndicateursService(AppDbContext db) => _db = db;

    /// <summary>Sortie = e + n (borne haute, telle qu'importée) ; SortieBasse = e + n − 1 si la sortie est calculée.</summary>
    record Sejour(DateOnly Entree, DateOnly? Sortie, DateOnly? SortieBasse, double P, string? Issue, string Statut, int? Nuits);

    /// <summary>Une fin possible d'un séjour, avec son poids (deux fins pour une sortie calculée ambiguë).</summary>
    record Fin(DateOnly Entree, DateOnly Jour, double Poids, bool Reelle, string? Issue);

    async Task<string?> Param(string cle) => (await _db.Parametres.AsNoTracking().FirstOrDefaultAsync(p => p.Cle == cle))?.Valeur;

    static string Mois(DateOnly d) => $"{d.Year}-{d.Month:D2}";

    public async Task<ResultatIndicateurs> CalculerAsync(int etablissementId, int serviceId, string par = "mois")
    {
        var verrou = DateOnly.TryParse(await Param("recherche.dateVerrou"), out var v) ? v : new DateOnly(2026, 9, 1);
        var fenetre = int.TryParse(await Param("recherche.fenetreCensure"), out var f) ? f : 30;
        var aujourdhui = DateOnly.FromDateTime(DateTime.UtcNow);
        var extraction = verrou < aujourdhui ? verrou : aujourdhui;

        var service = await _db.Services.AsNoTracking().FirstOrDefaultAsync(s => s.Id == serviceId && s.EtablissementId == etablissementId);
        int? lits = service is null ? null : service.LitsArmes > 0 ? service.LitsArmes : service.LitsInstalles > 0 ? service.LitsInstalles : null;
        var sourceLits = service is null ? "service introuvable"
            : service.LitsArmes > 0 ? "lits armés du service" : service.LitsInstalles > 0 ? "lits installés du service" : "non renseigné";

        var brut = await _db.Hospitalisations.AsNoTracking()
            .Where(h => h.EtablissementId == etablissementId && h.ServiceId == serviceId && h.DateEntree < verrou)
            .Select(h => new { h.DateEntree, h.DateSortie, h.DateSortieCalculee, h.DureeJoursDeclaree, h.Issue })
            .ToListAsync();

        // Convention du nombre de jours, mesurée sur les sorties ÉCRITES avec un nombre de jours (avant le verrou).
        var mesures = brut.Where(h => h.DateSortie is not null && !h.DateSortieCalculee && h.DureeJoursDeclaree is not null
                                      && h.DateSortie < verrou)
            .Select(h => (Mois: Mois(h.DateEntree), Ecart: h.DateSortie!.Value.DayNumber - h.DateEntree.DayNumber - h.DureeJoursDeclaree!.Value))
            .ToList();
        int k = mesures.Count(m => m.Ecart == -1), nNuits = mesures.Count(m => m.Ecart == 0);
        double? pGlobal = k + nNuits > 0 ? (double)k / (k + nNuits) : null;
        var p0 = pGlobal ?? 0.5;
        var pMois = mesures.GroupBy(m => m.Mois).ToDictionary(g => g.Key,
            g => (g.Count(m => m.Ecart == -1) + PseudoLignes * p0) / (g.Count(m => m.Ecart is -1 or 0) + PseudoLignes));
        var convention = new ConventionJours(mesures.Count, k, nNuits, mesures.Count - k - nNuits,
            pGlobal is double pg ? Math.Round(100 * pg, 1) : null, p0,
            pMois.OrderBy(kv => kv.Key).ToDictionary(kv => kv.Key, kv => Math.Round(100 * kv.Value, 1)),
            pGlobal is null
                ? "Aucune ligne n'a à la fois une sortie écrite et un nombre de jours : part inclusive prise à 50 %. La fourchette reste valable."
                : $"{Math.Round(100 * p0, 1)} % des {k + nNuits} lignes mesurables comptent le jour d'entrée et le jour de sortie : " +
                  "chaque sortie calculée est pondérée par cette part (occupation attendue), entre « tout inclusif » et « tout en nuits ».");

        // Séjours, avec le coffre appliqué : une sortie postérieure au verrou n'était pas connue.
        var sejours = brut.Select(h =>
        {
            DateOnly? sortie = h.DateSortie is DateOnly d && d < verrou ? d : null;
            var issue = sortie is null ? null : h.Issue;
            var calculee = sortie is not null && h.DateSortieCalculee;
            var statut = sortie is not null ? (calculee ? "calculee" : "observee")
                : h.DateEntree >= extraction.AddDays(-fenetre) ? "censuree" : "inconnue";
            DateOnly? basse = calculee && sortie!.Value.AddDays(-1) >= h.DateEntree ? sortie.Value.AddDays(-1) : sortie;
            var p = calculee ? pMois.GetValueOrDefault(Mois(h.DateEntree), p0) : 0;
            int? nuits = statut == "inconnue" ? null : (sortie ?? extraction).DayNumber - h.DateEntree.DayNumber;
            return new Sejour(h.DateEntree, sortie, basse, p, issue, statut, nuits);
        }).Where(s => s.Sortie is null || s.Sortie >= s.Entree).ToList();

        var statuts = new[] { "observee", "calculee", "censuree", "inconnue" }.ToDictionary(c => c, c => sejours.Count(s => s.Statut == c));
        var parts = sejours.GroupBy(s => Mois(s.Entree)).OrderBy(g => g.Key)
            .ToDictionary(g => g.Key, g => (double)g.Count(s => s.Statut != "inconnue") / g.Count());
        var parMois = parts.ToDictionary(kv => kv.Key, kv => Math.Round(100 * kv.Value, 1));

        string? premierMois = null;
        var cles = parts.Keys.ToList();
        for (var i = 0; i < cles.Count; i++)
            if (cles.Skip(i).All(c => parts[c] >= 0.9)) { premierMois = cles[i]; break; }
        if (premierMois is null)
            return new(lits, sourceLits, verrou, null, null, null, 0, parMois, statuts, convention, new(), new(),
                sejours.Count == 0 ? "Aucun séjour importé pour ce service." : "Aucune période où la durée de séjour est renseignée de façon complète.");

        var connues = sejours.Where(s => s.Statut is "observee" or "calculee" && s.Nuits is not null).Select(s => s.Nuits!.Value).OrderBy(x => x).ToList();
        // 95e centile par interpolation linéaire (même règle que pandas), puis partie entière.
        int p95 = 30;
        if (connues.Count > 0)
        {
            var pos = 0.95 * (connues.Count - 1);
            int ib = (int)Math.Floor(pos), ih = (int)Math.Ceiling(pos);
            p95 = (int)(connues[ib] + (connues[ih] - connues[ib]) * (pos - ib));
        }
        var rodage = premierMois == cles[0] ? 0 : Math.Max(14, p95);
        var debut = DateOnly.ParseExact(premierMois + "-01", "yyyy-MM-dd").AddDays(rodage);
        var fin = extraction.AddDays(-1);
        if (fin < debut)
            return new(lits, sourceLits, verrou, debut, fin, premierMois, rodage, parMois, statuts, convention, new(), new(),
                "Période exploitable trop courte.");

        var exploitables = sejours.Where(s => s.Statut != "inconnue").ToList();
        var n = fin.DayNumber - debut.DayNumber + 1;

        // Fins possibles selon le scénario : poids w = P(inclusif) sur e + n − 1, 1 − w sur e + n.
        List<Fin> Fins(Func<Sejour, double> w)
        {
            var liste = new List<Fin>();
            foreach (var s in exploitables)
            {
                if (s.Sortie is not DateOnly so) { liste.Add(new(s.Entree, extraction, 1, false, null)); continue; }
                var wb = s.Statut == "calculee" && s.SortieBasse < so ? w(s) : 0;
                if (wb > 0) liste.Add(new(s.Entree, s.SortieBasse!.Value, wb, true, s.Issue));
                if (1 - wb > 0) liste.Add(new(s.Entree, so, 1 - wb, true, s.Issue));
            }
            return liste;
        }

        // Recensement de minuit par tableau de différences : +1 à l'entrée, −poids à chaque fin possible.
        // Ce qui précède le début est cumulé dans le point de départ.
        double[] Presents(List<Fin> fins)
        {
            var delta = new double[n];
            double avant = 0;
            foreach (var s in exploitables)
            {
                var e = s.Entree.DayNumber - debut.DayNumber;
                if (e < 0) avant += 1; else if (e < n) delta[e] += 1;
            }
            foreach (var x in fins)
            {
                var o = x.Jour.DayNumber - debut.DayNumber;
                if (o < 0) avant -= x.Poids; else if (o < n) delta[o] -= x.Poids;
            }
            var presents = new double[n];
            var courant = avant;
            for (var i = 0; i < n; i++) { courant += delta[i]; presents[i] = Math.Round(courant, 10); }
            return presents;
        }
        var admissions = new int[n];
        foreach (var s in exploitables)
        {
            var e = s.Entree.DayNumber - debut.DayNumber;
            if (e >= 0 && e < n) admissions[e]++;
        }

        var finsAttendues = Fins(s => s.P);
        var attendus = Presents(finsAttendues);
        var bas = Presents(Fins(_ => 1));
        var hauts = Presents(Fins(_ => 0));

        var termines = finsAttendues.Where(x => x.Reelle && x.Jour > debut && x.Jour <= fin.AddDays(1)).ToList();
        string Cle(DateOnly d) => par == "annee" ? d.Year.ToString() : Mois(d);

        double? Tom(double[] presents, List<int> idx) =>
            lits is int l && idx.Count > 0 ? Math.Round(100.0 * idx.Sum(i => presents[i]) / (l * idx.Count), 1) : null;

        LigneIndicateurs Bloc(string periode, IEnumerable<int> indicesJours, List<Fin> sorties)
        {
            var idx = indicesJours.ToList();
            int J = idx.Count;
            double JH = idx.Sum(i => attendus[i]), ns = sorties.Sum(x => x.Poids), deces = sorties.Where(x => x.Issue == "Décès").Sum(x => x.Poids);
            return new LigneIndicateurs(periode, J, idx.Sum(i => admissions[i]), Math.Round(ns, 2), Math.Round(JH, 2),
                Tom(attendus, idx), Tom(bas, idx), Tom(hauts, idx),
                J > 0 ? Math.Round(idx.Max(i => attendus[i]), 2) : 0,
                lits is int l2 ? idx.Count(i => attendus[i] > l2) : 0,
                ns > 0 ? Math.Round(sorties.Sum(x => x.Poids * (x.Jour.DayNumber - x.Entree.DayNumber)) / ns, 2) : null,
                lits is int l3 ? Math.Round(ns / l3, 2) : null,
                lits is int l4 && ns > 0 ? Math.Round((l4 * (double)J - JH) / ns, 2) : null,
                Math.Round(deces, 2), ns > 0 ? Math.Round(100.0 * deces / ns, 2) : null);
        }

        var lignes = Enumerable.Range(0, n).GroupBy(i => Cle(debut.AddDays(i)))
            .Select(g => Bloc(g.Key, g, termines.Where(x => Cle(x.Jour) == g.Key).ToList())).ToList();
        lignes.Add(Bloc("Total", Enumerable.Range(0, n), termines));

        var serie = Enumerable.Range(0, n)
            .Select(i => new PointOccupation(debut.AddDays(i), Math.Round(attendus[i], 4), Math.Round(bas[i], 4), Math.Round(hauts[i], 4)))
            .ToList();
        return new(lits, sourceLits, verrou, debut, fin, premierMois, rodage, parMois, statuts, convention, lignes, serie,
            lits is null ? "Nombre de lits du service non renseigné : renseignez-le dans Administration pour obtenir le taux d'occupation." : null);
    }
}
