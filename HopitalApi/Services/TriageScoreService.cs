using System.Text.Json;
using HopitalApi.Models;

namespace HopitalApi.Services;

public record Contribution(string Label, double Poids);

public record ResultatTriage(
    double Score, int Categorie, double Confiance, bool Incertain,
    List<string> Manquants, List<Contribution> Contributions,
    double? IndexChoc, int? Pam, int QSofa, int QSofaConnus, int Mews, string Modele);

/// <summary>
/// Score de priorité de triage. Implémentation par règles pondérées — structure
/// identique à un noyau linéaire : chaque variable porte une contribution signée
/// directement exposable comme explication.
///
/// ⚠ Le modèle d'apprentissage (SVM) n'est PAS implémenté ici. Ce service est
/// l'emplacement prévu pour l'appel au microservice de modèles : garder la même
/// signature et remplacer le corps de <see cref="Evaluer"/>.
/// </summary>
public class TriageScoreService
{
    public const string Version = "regles-v1";

    static readonly string[] MotifsGraves =
    {
        "Détresse respiratoire", "Trouble de la conscience", "Convulsions", "Hémorragie",
        "Douleur thoracique", "Arrêt cardio-respiratoire", "Hémorragie obstétricale",
        "Accident vasculaire cérébral", "Nouveau-né en détresse", "Brûlure"
    };

    public ResultatTriage Evaluer(Triage t, Patient p, string motif, string modeEntree)
    {
        var c = new List<Contribution>();
        void Add(string label, double w) { if (Math.Abs(w) > 0.001) c.Add(new Contribution(label, Math.Round(w, 2))); }

        double? indexChoc = t.Pas is > 0 && t.Fc is > 0 ? Math.Round((double)t.Fc.Value / t.Pas.Value, 2) : null;
        int? pam = t.Pas.HasValue && t.Pad.HasValue ? (int)Math.Round((t.Pas.Value + 2.0 * t.Pad.Value) / 3) : null;

        // qSOFA — uniquement sur les critères réellement renseignés.
        int qsofa = 0, qsofaConnus = 0;
        if (t.Fr.HasValue) { qsofaConnus++; if (t.Fr >= 22) qsofa++; }
        if (t.Pas.HasValue) { qsofaConnus++; if (t.Pas <= 100) qsofa++; }
        if (!string.IsNullOrEmpty(t.Avpu)) { qsofaConnus++; if (t.Avpu != "Alerte" && t.Avpu != "Non évalué") qsofa++; }

        // MEWS
        int mews = 0;
        if (t.Fr is int fr) mews += fr <= 8 ? 2 : fr <= 14 ? 0 : fr <= 20 ? 1 : fr <= 29 ? 2 : 3;
        if (t.Fc is int fc) mews += fc <= 40 ? 2 : fc <= 50 ? 1 : fc <= 100 ? 0 : fc <= 110 ? 1 : fc <= 129 ? 2 : 3;
        if (t.Pas is int pas) mews += pas <= 70 ? 3 : pas <= 80 ? 2 : pas <= 100 ? 1 : pas <= 199 ? 0 : 2;
        if (t.Temperature is double tp) mews += tp < 35 ? 2 : tp <= 38.4 ? 0 : 2;
        if (t.Spo2 is int sp) mews += sp < 90 ? 3 : sp < 94 ? 1 : 0;
        if (t.Avpu == "Réponse à la voix") mews += 1;
        if (t.Avpu == "Réponse à la douleur") mews += 2;

        if (t.Fr is int f2) Add($"Fréquence respiratoire {f2}/min", f2 >= 30 ? 1.3 : f2 >= 22 ? 0.7 : f2 < 10 ? 1.1 : -0.2);
        if (t.Spo2 is int s2) Add($"SpO₂ {s2} %", s2 < 90 ? 1.5 : s2 < 94 ? 0.6 : -0.3);
        if (t.Pas is int p2) Add($"PA systolique {p2} mmHg", p2 <= 80 ? 1.6 : p2 <= 100 ? 0.8 : p2 >= 200 ? 0.6 : -0.2);
        if (t.Fc is int c2) Add($"Fréquence cardiaque {c2}/min", c2 >= 130 ? 1.0 : c2 >= 110 ? 0.5 : c2 <= 45 ? 0.9 : -0.15);
        if (indexChoc is double ic) Add($"Index de choc {ic}", ic >= 1.2 ? 1.2 : ic >= 0.9 ? 0.5 : 0);
        if (t.Temperature is double t2) Add($"Température {t2} °C", t2 >= 39.5 ? 0.5 : t2 < 35 ? 0.8 : 0);
        if (t.Glycemie is double g2) Add($"Glycémie {g2} g/L", g2 < 0.6 ? 1.1 : g2 > 3 ? 0.6 : 0);
        if (t.Avpu == "Réponse à la voix") Add("Conscience — réponse à la voix", 0.9);
        if (t.Avpu == "Réponse à la douleur") Add("Conscience — réponse à la douleur", 1.7);
        if (t.Glasgow is int gl && gl < 13) Add($"Glasgow {gl}/15", gl <= 8 ? 1.8 : 0.9);
        Add($"Âge {p.Age} ans", p.Age >= 70 ? 0.4 : p.Age <= 5 ? 0.5 : -0.1);
        if (t.Eva is int eva && eva >= 8) Add($"Douleur EVA {eva}/10", 0.4);
        if (MotifsGraves.Contains(motif)) Add($"Motif : {motif}", 0.6);
        if (modeEntree == "Ambulance") Add("Arrivée en ambulance", 0.4);
        if (p.Antecedents.Contains("Grossesse en cours")) Add("Grossesse en cours", 0.3);
        if (p.Antecedents.Contains("Drépanocytose")) Add("Drépanocytose", 0.25);
        if (p.Antecedents.Contains("VIH")) Add("Immunodépression connue", 0.2);

        var score = c.Sum(x => x.Poids);
        var categorie = score >= 3.2 ? 1 : score >= 1.8 ? 2 : score >= 0.6 ? 3 : 4;

        double[] bornes = { 3.2, 1.8, 0.6 };
        var marge = bornes.Min(b => Math.Abs(score - b));
        var confiance = Math.Clamp(0.55 + marge / 3, 0.42, 0.97);

        var manquants = new List<string>();
        if (t.Fr is null) manquants.Add("fréquence respiratoire");
        if (t.Pas is null) manquants.Add("PA systolique");
        if (t.Spo2 is null) manquants.Add("SpO₂");
        if (string.IsNullOrEmpty(t.Avpu) || t.Avpu == "Non évalué") manquants.Add("niveau de conscience");
        confiance = Math.Max(0.35, confiance - manquants.Count * 0.07);

        return new ResultatTriage(
            Math.Round(score, 2), categorie, Math.Round(confiance, 2), confiance < 0.65,
            manquants,
            c.OrderByDescending(x => Math.Abs(x.Poids)).Take(6).ToList(),
            indexChoc, pam, qsofa, qsofaConnus, mews, Version);
    }

    public static string Serialiser(object o) => JsonSerializer.Serialize(o);
}
