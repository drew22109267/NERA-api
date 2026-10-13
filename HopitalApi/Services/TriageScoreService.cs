using System.Text.Json;
using HopitalApi.Models;

namespace HopitalApi.Services;

public record Contribution(string Label, double Poids);

public record ResultatTriage(
    bool Disponible, string? Raison,
    double? Score, int? Categorie, double? Confiance, bool Incertain,
    List<string> Manquants, List<Contribution> Contributions,
    double? IndexChoc, int? Pam, int QSofa, int QSofaConnus, int Mews, string Modele);

/// <summary>
/// Évaluation au poste de triage.
///
/// Seuls des scores cliniques publiés sont calculés, à partir des constantes réellement
/// saisies : index de choc (FC/PAS), pression artérielle moyenne, qSOFA, MEWS.
///
/// Aucun modèle de priorisation n'est branché : aucune catégorie, aucun score ni
/// aucune confiance ne sont proposés (<c>Disponible = false</c>) et la catégorie est
/// fixée par l'infirmier. Le SVM, une fois entraîné sur les données réelles, remplira
/// <see cref="Evaluer"/> en conservant cette signature.
/// </summary>
public class TriageScoreService
{
    public const string Version = "aucun";
    const string RaisonIndisponible =
        "Aucun modèle de triage validé n'est branché : la catégorie est fixée par l'infirmier.";

    public ResultatTriage Evaluer(Triage t, Patient p, string motif, string modeEntree)
    {
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
        if (t.Avpu == "Réponse à la voix") mews += 1;
        if (t.Avpu == "Réponse à la douleur") mews += 2;

        var manquants = new List<string>();
        if (t.Fr is null) manquants.Add("fréquence respiratoire");
        if (t.Pas is null) manquants.Add("PA systolique");
        if (t.Spo2 is null) manquants.Add("SpO₂");
        if (string.IsNullOrEmpty(t.Avpu) || t.Avpu == "Non évalué") manquants.Add("niveau de conscience");

        return new ResultatTriage(
            false, RaisonIndisponible,
            null, null, null, false,
            manquants, new List<Contribution>(),
            indexChoc, pam, qsofa, qsofaConnus, mews, Version);
    }

    public static string Serialiser(object o) => JsonSerializer.Serialize(o);
}
