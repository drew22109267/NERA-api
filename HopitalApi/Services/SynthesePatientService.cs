using HopitalApi.Data;
using HopitalApi.Models;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Services;

/// <summary>
/// Synthèse de l'espace patient : constantes dans le temps, risque de réadmission,
/// suivi des maladies chroniques, dépenses estimées et recours aux soins.
///
/// Tout est calculé sur les données réellement enregistrées. Aucune valeur n'est
/// inventée : une mesure absente vaut null et l'interface l'affiche comme
/// « non mesuré ». Les montants n'apparaissent que si l'établissement a saisi sa
/// grille tarifaire dans Administration.
///
/// Aucun score inventé : le risque de réadmission reste « non disponible » tant
/// qu'aucun modèle validé n'est branché, et le niveau d'une maladie chronique ne
/// découle que de seuils cliniques publiés appliqués à une mesure réelle — sans
/// mesure, il vaut null.
/// </summary>
public class SynthesePatientService
{
    readonly AppDbContext _db;
    public SynthesePatientService(AppDbContext db) => _db = db;

    static readonly string[] MoisCourts =
        { "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc." };

    public record Mois(string Cle, string Label);
    public record Contribution(string Label, int Points, string Detail);
    /// <summary>Niveau null = non mesuré ou sans seuil clinique applicable ; Repere cite le seuil utilisé.</summary>
    public record RisqueChronique(string Nom, string? Niveau, string Detail, string Suivi, bool Declare, string? Repere);
    public record Poste(string Nom, double Montant);

    static string CleMois(DateTime d) => $"{d.Year}-{d.Month:D2}";

    static List<Mois> DerniersMois(int n = 12)
    {
        var liste = new List<Mois>();
        var maintenant = DateTime.UtcNow;
        for (var i = n - 1; i >= 0; i--)
        {
            var m = new DateTime(maintenant.Year, maintenant.Month, 1).AddMonths(-i);
            liste.Add(new Mois(CleMois(m), MoisCourts[m.Month - 1]));
        }
        return liste;
    }

    static int? Jours(DateTime? d) => d is null ? null : (int)Math.Floor((DateTime.UtcNow - d.Value).TotalDays);

    /// <summary>Durée d'un séjour en jours, jusqu'à la sortie ou jusqu'à aujourd'hui.</summary>
    static double JoursSejour(Sejour s) => Math.Max(1, Math.Ceiling(((s.Sortie ?? DateTime.UtcNow) - s.Entree).TotalDays));

    /// <summary>Constantes relevées aux dix derniers triages, du plus ancien au plus récent.</summary>
    static List<object> Serie(List<Passage> passages) =>
        passages.Where(p => p.Triage is not null)
            .OrderByDescending(p => p.Arrivee).Take(10).Reverse()
            .Select(p => (object)new
            {
                date = p.Arrivee, reference = p.Reference,
                pas = p.Triage!.Pas, pad = p.Triage.Pad, fc = p.Triage.Fc, fr = p.Triage.Fr,
                spo2 = p.Triage.Spo2, temperature = p.Triage.Temperature,
                glycemie = p.Triage.Glycemie, poids = p.Triage.Poids,
                eva = p.Triage.Eva, avpu = p.Triage.Avpu
            }).ToList();

    /// <summary>Dernière valeur non nulle d'une constante, tous triages confondus.</summary>
    static double? Derniere(List<Passage> passages, Func<Triage, double?> champ) =>
        passages.Where(p => p.Triage is not null).OrderByDescending(p => p.Arrivee)
            .Select(p => champ(p.Triage!)).FirstOrDefault(v => v is not null);

    // ── 1. Risque de réadmission à 30 jours ──────────────────────────────
    /// <summary>Emplacement du modèle de réadmission : rien n'est estimé sans lui.</summary>
    static object RisqueReadmission() => new
    {
        disponible = false, horizon = "30 jours",
        raison = "Aucun modèle de réadmission validé n'est branché : aucun score n'est affiché."
    };

    // ── 2. Maladies chroniques déclarées et dépistages suggérés ──────────
    // Seuils cliniques publiés ; aucun niveau n'est attribué sans mesure réelle.
    const string RepereTension = "Grades d'HTA ESC/ESH 2018 : ≥ 140 et ≥ 160 mmHg";
    const string RepereGlycemie = "ADA : hypoglycémie < 0,70 g/L (sévère < 0,54) ; hyperglycémie ≥ 2,0 g/L, ≥ 2,5 g/L";
    const string RepereSpo2 = "GINA : SpO₂ < 95 % exacerbation, < 90 % menace vitale";
    const string RepereFc = "Tachycardie > 100/min, bradycardie < 60/min (adulte)";
    const string RepereGrossesse = "HTA gravidique ≥ 140 mmHg, sévère ≥ 160 mmHg (ACOG)";

    static string? NiveauTension(double? pas) => pas switch
    { null => null, >= 160 => "crit", >= 140 => "warn", _ => "ok" };
    static string? NiveauGlycemie(double? g) => g switch
    { null => null, < 0.54 or >= 2.5 => "crit", < 0.7 or >= 2.0 => "warn", _ => "ok" };
    static string? NiveauSpo2(double? s) => s switch
    { null => null, < 90 => "crit", < 95 => "warn", _ => "ok" };
    static string? NiveauFc(double? fc) => fc switch
    { null => null, > 100 or < 60 => "warn", _ => "ok" };

    static int Rang(string? n) => n switch { "crit" => 3, "warn" => 2, "ok" => 1, _ => 0 };

    static List<RisqueChronique> RisquesChroniques(Patient dossier, List<Passage> passages)
    {
        var p12 = passages.Where(p => Jours(p.Arrivee) <= 365).ToList();
        int Compte(string mot) => p12.Count(p => (p.Motif ?? "").Contains(mot, StringComparison.OrdinalIgnoreCase));
        var crises = Compte("drépan") + Compte("respiratoire");
        var infections = Compte("infection") + Compte("fièvre");
        var convulsions = Compte("convulsion");

        var pas = Derniere(passages, t => t.Pas);
        var pad = Derniere(passages, t => t.Pad);
        var fc = Derniere(passages, t => t.Fc);
        var spo2 = Derniere(passages, t => t.Spo2);
        var gly = Derniere(passages, t => t.Glycemie);

        string Tension() => pas is null ? "Tension non relevée — contrôle à programmer."
            : $"Dernière mesure {pas}{(pad is not null ? $"/{pad}" : "")} mmHg.";

        var res = new List<RisqueChronique>();
        foreach (var a in dossier.Antecedents ?? new List<string>())
        {
            (string nom, string? niveau, string detail, string suivi, string? repere) r = a switch
            {
                "HTA" => ("Hypertension artérielle", NiveauTension(pas), Tension(),
                    "Tension à chaque passage, objectif < 140/90 mmHg", RepereTension),
                "Diabète" => ("Diabète", NiveauGlycemie(gly),
                    gly is null ? "Glycémie non relevée — contrôle à programmer." : $"Dernière glycémie {gly} g/L.",
                    "Glycémie capillaire, objectif 0,7–1,1 g/L à jeun", RepereGlycemie),
                "Asthme" => ("Asthme", NiveauSpo2(spo2),
                    $"SpO₂ {(spo2 is not null ? spo2 + " %" : "non mesurée")} · {crises} crise(s) respiratoire(s) sur 12 mois.",
                    "SpO₂ et fréquence respiratoire", RepereSpo2),
                "Drépanocytose" => ("Drépanocytose", null,
                    $"{crises} crise(s) enregistrée(s) sur les 12 derniers mois.",
                    "Fréquence des crises vaso-occlusives", null),
                "Insuffisance rénale" => ("Insuffisance rénale", NiveauTension(pas),
                    $"Suivi néphrologique à maintenir · {Tension()}",
                    "Tension, poids et créatinine", RepereTension),
                "Cardiopathie" => ("Cardiopathie", NiveauFc(fc),
                    $"Fréquence cardiaque {(fc is not null ? fc + "/min" : "non mesurée")}.",
                    "Fréquence cardiaque et tension", RepereFc),
                "VIH" => ("VIH", null,
                    $"{infections} épisode(s) infectieux sur 12 mois.",
                    "Observance du traitement et infections répétées", null),
                "Épilepsie" => ("Épilepsie", null,
                    $"{convulsions} crise(s) convulsive(s) enregistrée(s) sur 12 mois.",
                    "Fréquence des crises convulsives", null),
                "Grossesse en cours" => ("Grossesse en cours", NiveauTension(pas),
                    $"{Tension()} Surveillance de la pré-éclampsie.",
                    "Tension et consultations prénatales", RepereGrossesse),
                _ => (a, null, "Antécédent déclaré — pas de règle de suivi automatique.", "Suivi clinique", null)
            };
            res.Add(new RisqueChronique(r.nom, r.niveau, r.detail, r.suivi, true, r.repere));
        }

        bool DejaSuivi(string n) => res.Any(x => x.Nom == n);
        if (pas is not null && pas >= 140 && !DejaSuivi("Hypertension artérielle"))
            res.Add(new RisqueChronique("Hypertension à confirmer", NiveauTension(pas),
                $"Tension {pas} mmHg relevée sans antécédent d'HTA déclaré.", "Trois mesures à distance des urgences", false, RepereTension));
        if (gly is not null && gly >= 1.26 && !DejaSuivi("Diabète"))
            res.Add(new RisqueChronique("Hyperglycémie à confirmer", NiveauGlycemie(gly) == "crit" ? "crit" : "warn",
                $"Glycémie {gly} g/L relevée sans diabète déclaré.", "Glycémie à jeun en laboratoire",
                false, "OMS : glycémie à jeun ≥ 1,26 g/L évocatrice de diabète"));
        if (spo2 is not null && spo2 < 95 && !DejaSuivi("Asthme"))
            res.Add(new RisqueChronique("Saturation basse à explorer", NiveauSpo2(spo2),
                $"SpO₂ {spo2} % au dernier triage.", "Consultation pneumologique", false, RepereSpo2));
        return res.OrderByDescending(r => Rang(r.Niveau)).ToList();
    }

    // ── 3. Dépenses estimées, d'après la grille de l'établissement ───────
    static object Depenses(Patient dossier, List<Passage> passages, List<RendezVous> rdv,
        List<Sejour> sejours, List<Mois> mois, List<Parametre> parametres)
    {
        double? Param(string cle)
        {
            var v = parametres.FirstOrDefault(p => p.Cle == cle)?.Valeur;
            return double.TryParse(v, System.Globalization.NumberStyles.Any,
                System.Globalization.CultureInfo.InvariantCulture, out var n) ? n : null;
        }

        var cles = new[] { "tarif.consultation", "tarif.triage", "tarif.categorie.1", "tarif.categorie.2",
            "tarif.categorie.3", "tarif.categorie.4", "tarif.journeeHospitalisation", "tarif.laboratoire",
            "tarif.imagerie", "tarif.medicaments", "tarif.rendezVous" };
        // Sans aucun tarif saisi, rien n'est affiché plutôt que d'estimer au hasard.
        if (!cles.Any(c => Param(c) is > 0))
            return new { configure = false, total = 0.0, parPoste = Array.Empty<Poste>(), serieMensuelle = mois.Select(_ => 0.0).ToArray() };

        double T(string cle) => Param(cle) ?? 0;
        double ParCategorie(int? c) => c is null ? 0 : T($"tarif.categorie.{c}");
        double CoutPassage(Passage p)
        {
            var m = T("tarif.consultation");
            if (p.Triage is not null) m += T("tarif.triage");
            m += ParCategorie(p.Categorie);
            if (p.Categorie is 1 or 2) m += T("tarif.laboratoire") + T("tarif.imagerie");
            else if (p.Categorie == 3) m += T("tarif.laboratoire");
            return m + T("tarif.medicaments");
        }

        var honores = rdv.Where(r => r.Statut == "Honoré").ToList();
        var serie = mois.Select(m =>
            passages.Where(p => CleMois(p.Arrivee) == m.Cle).Sum(CoutPassage)
            + honores.Count(r => CleMois(r.Date.ToDateTime(TimeOnly.MinValue)) == m.Cle) * T("tarif.rendezVous")
            + sejours.Where(s => CleMois(s.Entree) == m.Cle).Sum(s => JoursSejour(s) * T("tarif.journeeHospitalisation"))
        ).ToArray();

        var parPoste = new[]
        {
            new Poste("Consultations & triage", passages.Count * T("tarif.consultation") + passages.Count(p => p.Triage is not null) * T("tarif.triage")),
            new Poste("Actes selon priorité", passages.Sum(p => ParCategorie(p.Categorie))),
            new Poste("Laboratoire & imagerie", passages.Sum(p => p.Categorie is 1 or 2 ? T("tarif.laboratoire") + T("tarif.imagerie") : p.Categorie == 3 ? T("tarif.laboratoire") : 0)),
            new Poste("Médicaments", passages.Count * T("tarif.medicaments")),
            new Poste("Hospitalisation", sejours.Sum(s => JoursSejour(s) * T("tarif.journeeHospitalisation"))),
            new Poste("Consultations programmées", honores.Count * T("tarif.rendezVous"))
        }.Where(x => x.Montant > 0).OrderByDescending(x => x.Montant).ToArray();

        var total = parPoste.Sum(x => x.Montant);
        var couv = Param($"couverture.{dossier.ModePaiement}");
        double? part = couv is null ? null : Math.Max(0, Math.Min(1, couv > 1 ? couv.Value / 100 : couv.Value));

        return new
        {
            configure = true, total,
            couvert = part is null ? (double?)null : Math.Round(total * part.Value),
            resteACharge = part is null ? total : Math.Round(total * (1 - part.Value)),
            partCouverte = part,
            modePaiement = string.IsNullOrWhiteSpace(dossier.ModePaiement) ? "non renseigné" : dossier.ModePaiement,
            serieMensuelle = serie,
            total12Mois = serie.Sum(),
            moyenneParPassage = passages.Count > 0 ? Math.Round(total / passages.Count) : 0,
            parPoste,
            // Coût estimé de chaque passage, pour la colonne du tableau d'historique
            parPassage = passages.ToDictionary(p => p.Id.ToString(), p => Math.Round(CoutPassage(p)))
        };
    }

    // ── 4. Recours aux soins et assiduité ────────────────────────────────
    static object Recours(List<Passage> passages, List<RendezVous> rdv, List<Mois> mois)
    {
        var p12 = passages.Where(p => Jours(p.Arrivee) <= 365).ToList();
        var recents = passages.OrderByDescending(p => p.Arrivee).ToList();
        var attentes = recents.Where(p => p.TriageLe is not null)
            .Select(p => (int)(p.TriageLe!.Value - p.Arrivee).TotalMinutes).Where(m => m >= 0).ToList();

        var honores = rdv.Count(r => r.Statut == "Honoré");
        var manques = rdv.Count(r => r.Statut == "Manqué");
        var passes = honores + manques;
        var aujourdhui = DateOnly.FromDateTime(DateTime.UtcNow);

        return new
        {
            passages12Mois = p12.Count,
            passagesTotal = passages.Count,
            serieMensuelle = mois.Select(m => passages.Count(p => CleMois(p.Arrivee) == m.Cle)).ToArray(),
            attenteMoyenne = attentes.Count > 0 ? (int?)Math.Round(attentes.Average()) : null,
            attenteSerie = recents.Take(8).Reverse()
                .Select(p => p.TriageLe is null ? 0 : (int)(p.TriageLe.Value - p.Arrivee).TotalMinutes).ToArray(),
            motifFrequent = p12.GroupBy(p => p.Motif).OrderByDescending(g => g.Count()).FirstOrDefault()?.Key,
            categories = new[] { 1, 2, 3, 4 }.Select(c => new { cat = c, n = p12.Count(p => p.Categorie == c) }).ToArray(),
            nonTries = p12.Count(p => p.Categorie is null),
            rdv = new
            {
                honores, manques,
                annules = rdv.Count(r => r.Statut == "Annulé"),
                aVenir = rdv.Count(r => r.Statut != "Annulé" && r.Date >= aujourdhui),
                total = rdv.Count,
                assiduite = passes > 0 ? (int?)Math.Round(100.0 * honores / passes) : null
            }
        };
    }

    public async Task<object?> SyntheseAsync(int patientId)
    {
        var dossier = await _db.Patients.AsNoTracking().FirstOrDefaultAsync(p => p.Id == patientId);
        if (dossier is null) return null;

        var passages = await _db.Passages.AsNoTracking().Include(p => p.Triage)
            .Where(p => p.PatientId == patientId).ToListAsync();
        var rdv = await _db.RendezVous.AsNoTracking().Where(r => r.PatientId == patientId).ToListAsync();
        var sejours = await _db.Sejours.AsNoTracking().Where(s => s.PatientId == patientId).ToListAsync();
        var parametres = await _db.Parametres.AsNoTracking().ToListAsync();
        var mois = DerniersMois();

        return new
        {
            mois = mois.Select(m => new { cle = m.Cle, label = m.Label }).ToArray(),
            serie = Serie(passages),
            sante = RisqueReadmission(),
            chroniques = RisquesChroniques(dossier, passages),
            cout = Depenses(dossier, passages, rdv, sejours, mois, parametres),
            soins = Recours(passages, rdv, mois)
        };
    }
}
