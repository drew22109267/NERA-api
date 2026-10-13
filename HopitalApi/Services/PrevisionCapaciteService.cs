using HopitalApi.Models;

namespace HopitalApi.Services;

public record PointPrevision(int Jour, double Bas, double Median, double Haut, int Capacite);
public record PrevisionService(int ServiceId, string Nom, int Capacite, bool Disponible, string? Raison,
    List<PointPrevision> Points, Dictionary<int, double> RisqueSaturation, List<(string Label, int Valeur)> Decomposition);

/// <summary>
/// Prévision d'occupation avec intervalle.
///
/// Aucun modèle de prévision n'est branché : le service le dit (<c>Disponible = false</c>)
/// et ne renvoie ni courbe, ni intervalle, ni risque. Aucune valeur n'est simulée.
/// Le modèle quantile (SVR), une fois entraîné sur l'historique réel des séjours,
/// remplira <see cref="Prevoir"/> en conservant la forme de sortie (médiane + bande).
/// La décomposition, elle, ne contient que des comptes réels du service.
/// </summary>
public class PrevisionCapaciteService
{
    public const string Version = "aucun";
    const string RaisonIndisponible =
        "Aucun modèle de prévision validé n'est branché. La prévision apparaîtra une fois le modèle entraîné sur l'historique réel des séjours.";

    public PrevisionService Prevoir(Service s, int horizon = 30,
        double hausseAdmissions = 0, double reductionBlocage = 0, int litsSupp = 0)
    {
        var capacite = Math.Max(0, s.LitsArmes + litsSupp);
        var decomp = new List<(string, int)>
        {
            ("Patients actuellement hospitalisés", s.Occupes),
            ("Lits bloqués pour motif non médical", s.Bloques),
            ("Admissions programmées connues", s.Programmes)
        };
        return new PrevisionService(s.Id, s.Nom, capacite, false, RaisonIndisponible,
            new List<PointPrevision>(), new Dictionary<int, double>(), decomp);
    }

    /// <summary>Risque de dépasser la capacité au jour donné ; null sans prévision.</summary>
    public static double? RisqueSaturation(List<PointPrevision> points, int jour)
    {
        var p = points.FirstOrDefault(x => x.Jour == jour) ?? points.LastOrDefault();
        if (p is null) return null;
        var sigma = Math.Max(0.4, (p.Haut - p.Bas) / 3.29);
        var z = (p.Capacite - p.Median) / sigma;
        var cdf = 1 / (1 + Math.Exp(-1.702 * z));
        return Math.Round(Math.Clamp(1 - cdf, 0, 1), 3);
    }

    /// <summary>
    /// Probabilité de sortie à J0/J1/J2 — emplacement du modèle de survie.
    /// Sans modèle entraîné, aucune probabilité n'est renvoyée.
    /// </summary>
    public static (double? J0, double? J1, double? J2) ProbaSortie(Sejour s) => (null, null, null);

    public static string Niveau(double taux) => taux > 0.9 ? "crit" : taux >= 0.7 ? "warn" : "ok";
}
