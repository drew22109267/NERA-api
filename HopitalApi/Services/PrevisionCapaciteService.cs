using HopitalApi.Models;

namespace HopitalApi.Services;

public record PointPrevision(int Jour, double Bas, double Median, double Haut, int Capacite);
public record PrevisionService(int ServiceId, string Nom, int Capacite, List<PointPrevision> Points,
    Dictionary<int, double> RisqueSaturation, List<(string Label, int Valeur)> Decomposition);

/// <summary>
/// Prévision d'occupation avec intervalle. Implémentation déterministe par
/// tendance + saisonnalité hebdomadaire.
///
/// ⚠ Le modèle quantile (SVR) n'est PAS implémenté ici. Remplacer le corps de
/// <see cref="Prevoir"/> par l'appel au microservice de modèles, en conservant
/// la forme de sortie (médiane + bande).
/// </summary>
public class PrevisionCapaciteService
{
    public const string Version = "regles-v1";

    static double Bruit(int graine, int j)
    {
        unchecked
        {
            var h = (uint)(graine * 1664525 + j * 1013904223 + 12345);
            h ^= h >> 13; h *= 2246822519; h ^= h >> 16;
            return h / 4294967296.0 - 0.5;
        }
    }

    public PrevisionService Prevoir(Service s, int horizon = 30,
        double hausseAdmissions = 0, double reductionBlocage = 0, int litsSupp = 0)
    {
        var capacite = Math.Max(1, s.LitsArmes + litsSupp);
        var points = new List<PointPrevision>();
        double baseOcc = s.Occupes;

        for (var j = 1; j <= horizon; j++)
        {
            var saison = Math.Sin(j / 7.0 * Math.PI) * s.LitsArmes * 0.05;
            var bruit = Bruit(s.Id, j) * s.LitsArmes * 0.08;
            baseOcc += s.Tendance * j * 0.35 + saison * 0.3 + bruit;
            var attendu = baseOcc * (1 + hausseAdmissions / 100) - s.Bloques * (reductionBlocage / 100)
                          + s.Programmes * (j <= 7 ? 0.1 : 0.04);
            var largeur = Math.Max(1.2, Math.Sqrt(j) * s.LitsArmes * 0.055);
            points.Add(new PointPrevision(j,
                Math.Round(Math.Max(0, attendu - largeur), 1),
                Math.Round(Math.Max(0, attendu), 1),
                Math.Round(attendu + largeur, 1), capacite));
        }

        var risques = new Dictionary<int, double>();
        foreach (var h in new[] { 1, 3, 7, 14, 30, 60 })
            if (h <= horizon) risques[h] = RisqueSaturation(points, h);

        var urgences = (int)Math.Round(s.Occupes * 0.46);
        var programmes = (int)Math.Round(s.Occupes * 0.19);
        var presents = Math.Max(0, s.Occupes - urgences - programmes);
        var decomp = new List<(string, int)>
        {
            ("Patients déjà présents (séjour restant estimé)", presents),
            ("Admissions programmées connues", programmes),
            ("Urgences imprévues (estimation)", urgences)
        };

        return new PrevisionService(s.Id, s.Nom, capacite, points, risques, decomp);
    }

    public static double RisqueSaturation(List<PointPrevision> points, int jour)
    {
        var p = points.FirstOrDefault(x => x.Jour == jour) ?? points.LastOrDefault();
        if (p is null) return 0;
        var sigma = Math.Max(0.4, (p.Haut - p.Bas) / 3.29);
        var z = (p.Capacite - p.Median) / sigma;
        var cdf = 1 / (1 + Math.Exp(-1.702 * z));
        return Math.Round(Math.Clamp(1 - cdf, 0, 1), 3);
    }

    /// <summary>Probabilité de sortie à J0/J1/J2 — emplacement du modèle de survie.</summary>
    public static (double J0, double J1, double J2) ProbaSortie(int sejourId, int jours)
    {
        var b = Math.Min(0.92, 0.12 + jours * 0.09 + Math.Abs(Bruit(sejourId, 7)) * 0.5);
        return (Math.Round(b * 0.55, 2), Math.Round(b * 0.8, 2), Math.Round(Math.Min(0.97, b), 2));
    }

    public static string Niveau(double taux) => taux > 0.9 ? "crit" : taux >= 0.7 ? "warn" : "ok";
}
