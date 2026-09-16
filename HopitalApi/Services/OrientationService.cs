using HopitalApi.Data;
using HopitalApi.Models;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Services;

public record PropositionService(
    int ServiceId, string Code, string Nom, string Pole,
    int LitsLibres, int LitsArmes, double TauxOccupation,
    double Score, string Niveau, List<string> Raisons, bool Recommande);

public record ResultatOrientation(
    string Motif, int? Categorie, string Explication,
    List<PropositionService> Propositions, string? Avertissement);

/// <summary>
/// Redistribution des patients entre services. Croise la règle clinique
/// (pathologie → service), les contraintes d'âge et de sexe, la catégorie de
/// triage et la disponibilité réelle des lits.
/// </summary>
public class OrientationService
{
    readonly AppDbContext _db;
    public OrientationService(AppDbContext db) => _db = db;

    public async Task<ResultatOrientation> OrienterAsync(string motif, int age, string sexe, int? categorie, List<string>? antecedents = null)
    {
        antecedents ??= new List<string>();
        var services = await _db.Services.Where(s => s.Actif && s.Hospitalisation).ToListAsync();
        if (services.Count == 0)
            return new ResultatOrientation(motif, categorie, "Aucun service d'hospitalisation paramétré.",
                new List<PropositionService>(), "Base de services vide — paramétrez l'établissement avant d'orienter.");

        var regles = await _db.ReglesOrientation
            .Where(r => r.Motif == motif && age >= r.AgeMin && age <= r.AgeMax)
            .OrderBy(r => r.Priorite).ToListAsync();

        regles = regles.Where(r => r.SexeRequis == null || r.SexeRequis == sexe).ToList();

        var cibles = new List<(string Code, double Bonus, string Raison)>();
        foreach (var r in regles)
        {
            if (r.CategorieMax.HasValue && categorie.HasValue && categorie > r.CategorieMax)
                continue;
            cibles.Add((r.ServiceCode, 3.0, $"Filière clinique « {motif} »{(r.Commentaire is null ? "" : " — " + r.Commentaire)}"));
            if (r.ServiceAlternatifCode is not null)
                cibles.Add((r.ServiceAlternatifCode, 1.6, "Service de repli prévu pour cette filière"));
        }

        // Catégorie 1 : la réanimation entre systématiquement dans les propositions.
        if (categorie == 1)
            cibles.Add((age < 15 ? "REAPED" : "REA", 2.4, "Catégorie 1 — prise en charge en réanimation à envisager"));

        if (antecedents.Contains("Drépanocytose")) cibles.Add(("HEMATO", 1.0, "Antécédent drépanocytaire suivi en hématologie"));
        if (antecedents.Contains("Grossesse en cours") && sexe == "F") cibles.Add(("MATER", 1.2, "Grossesse en cours"));
        if (antecedents.Contains("Diabète")) cibles.Add(("ENDO", 0.6, "Diabète connu"));
        if (antecedents.Contains("VIH")) cibles.Add(("INFEC", 0.6, "Immunodépression connue"));

        if (cibles.Count == 0)
            cibles.Add((age < 15 ? "PED" : "MED", 1.5, "Aucune règle spécifique — orientation par défaut selon l'âge"));

        var props = new List<PropositionService>();
        foreach (var groupe in cibles.GroupBy(x => x.Code))
        {
            var svc = services.FirstOrDefault(s => s.Code == groupe.Key);
            if (svc is null) continue;
            if (age < svc.AgeMin || age > svc.AgeMax) continue;

            var libres = Math.Max(0, svc.LitsArmes - svc.Occupes - svc.Bloques);
            var taux = svc.LitsArmes > 0 ? (double)svc.Occupes / svc.LitsArmes : 1;
            var raisons = groupe.Select(x => x.Raison).Distinct().ToList();

            var score = groupe.Sum(x => x.Bonus);
            // Disponibilité : jusqu'à +2 si le service est dégagé, pénalité forte s'il est saturé.
            score += libres switch { 0 => -2.5, 1 => -0.6, <= 3 => 0.4, <= 8 => 1.2, _ => 2.0 };
            if (taux >= 0.95) { score -= 1.2; raisons.Add("Service saturé — orientation déconseillée sans arbitrage"); }
            else if (taux >= 0.85) raisons.Add("Service en tension");
            if (libres == 0) raisons.Add("Aucun lit libre actuellement");
            if (svc.Bloques > 0) raisons.Add($"{svc.Bloques} lit(s) bloqué(s) pour motif non médical");

            var niveau = taux >= 0.95 ? "crit" : taux >= 0.85 ? "warn" : "ok";
            props.Add(new PropositionService(svc.Id, svc.Code, svc.Nom, svc.Pole, libres, svc.LitsArmes,
                Math.Round(taux, 3), Math.Round(score, 2), niveau, raisons, false));
        }

        props = props.OrderByDescending(p => p.Score).ThenByDescending(p => p.LitsLibres).Take(5).ToList();
        if (props.Count > 0) props[0] = props[0] with { Recommande = true };

        string? avert = null;
        if (props.Count == 0)
            avert = "Aucun service compatible avec l'âge et le motif dans cet établissement — transfert externe à envisager.";
        else if (props.All(p => p.LitsLibres == 0))
            avert = "Aucun lit libre dans les services compatibles. Enregistrez une demande non satisfaite si le patient est réorienté.";

        var explication = props.Count > 0
            ? $"Filière « {motif} » pour un patient de {age} ans : {props[0].Nom} arrive en tête sur {props.Count} service(s) compatible(s), en croisant la règle clinique et les lits réellement disponibles."
            : $"Aucune destination compatible pour « {motif} » à {age} ans.";

        return new ResultatOrientation(motif, categorie, explication, props, avert);
    }

    public async Task<List<string>> MotifsAsync() =>
        await _db.ReglesOrientation.Select(r => r.Motif).Distinct().OrderBy(m => m).ToListAsync();
}
