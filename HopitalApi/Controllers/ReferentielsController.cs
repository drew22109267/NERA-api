using HopitalApi.Data;
using HopitalApi.Dtos;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HopitalApi.Controllers;

/// <summary>
/// Source unique des référentiels de l'interface. Deux familles :
///   • les énumérations du domaine, propriété du serveur (statuts, catégories
///     de triage, bornes physiologiques) — l'interface ne les redéfinit jamais ;
///   • les listes propres à l'établissement (salles de bloc, motifs de blocage,
///     modes d'entrée…), saisies dans Administration et stockées en paramètres.
/// Aucune de ces valeurs n'est codée en dur côté navigateur.
/// </summary>
[ApiController]
[Route("api/referentiels")]
[Authorize]
public class ReferentielsController : BaseController
{
    readonly AppDbContext _db;
    public ReferentielsController(AppDbContext db) => _db = db;

    /// <summary>Valeurs par défaut proposées quand l'établissement n'a rien saisi.</summary>
    public static readonly Dictionary<string, string[]> ListesParDefaut = new()
    {
        ["liste.modesEntree"] = new[] { "À pied", "Ambulance", "Référé par un centre de santé", "Transfert d'un autre hôpital" },
        ["liste.motifsBlocage"] = new[] { "Attente de paiement", "Attente de transport", "Attente de transfert", "Attente de place en aval", "Attente d'accompagnant", "Autre" },
        ["liste.typesNotification"] = new[] { "Rappel RDV", "Alerte capacité", "Réévaluation", "Information", "Rapport" },
        ["liste.sallesBloc"] = Array.Empty<string>(),
        ["liste.categoriesDiagnostic"] = Array.Empty<string>(),
        ["liste.motifsRecours"] = Array.Empty<string>(),
        ["liste.antecedents"] = new[] { "HTA", "Diabète", "Drépanocytose", "VIH", "Asthme", "Insuffisance rénale", "Épilepsie", "Grossesse en cours", "Cardiopathie", "Autre" },
        ["liste.paiements"] = new[] { "Paiement direct", "Mutuelle", "Employeur", "Indigent", "Gratuité ciblée" },
        ["liste.canaux"] = new[] { "SMS", "USSD", "Application", "Affichage salle d'attente" }
    };

    // ── Énumérations du domaine : elles suivent le modèle, pas l'interface ──
    static readonly object[] Categories =
    {
        new { id = 1, label = "Immédiat", delaiMin = 0 },
        new { id = 2, label = "Très urgent", delaiMin = 10 },
        new { id = 3, label = "Urgent", delaiMin = 60 },
        new { id = 4, label = "Non urgent", delaiMin = 240 }
    };

    static readonly Dictionary<string, string> Roles = new()
    {
        ["accueil"] = "Agent d'accueil",
        ["infirmier"] = "Infirmier de triage",
        ["medecin"] = "Médecin",
        ["gestionnaire"] = "Gestionnaire de lits",
        ["direction"] = "Direction",
        ["data"] = "Data manager",
        ["admin"] = "Administrateur",
        ["patient"] = "Patient"
    };

    /// <summary>Bornes physiologiques — identiques aux attributs [Range] des DTO de triage.</summary>
    static readonly Dictionary<string, object> Bornes = new()
    {
        ["pas"] = new { min = 30, max = 300, unite = "mmHg", label = "PA systolique", pas = 1.0 },
        ["pad"] = new { min = 10, max = 200, unite = "mmHg", label = "PA diastolique", pas = 1.0 },
        ["fc"] = new { min = 20, max = 250, unite = "/min", label = "Fréquence cardiaque", pas = 1.0 },
        ["fr"] = new { min = 4, max = 80, unite = "/min", label = "Fréquence respiratoire", pas = 1.0 },
        ["temperature"] = new { min = 25, max = 45, unite = "°C", label = "Température", pas = 0.1 },
        ["spo2"] = new { min = 40, max = 100, unite = "%", label = "SpO₂", pas = 1.0 },
        ["glycemie"] = new { min = 0.1, max = 10, unite = "g/L", label = "Glycémie capillaire", pas = 0.1 },
        ["poids"] = new { min = 0.5, max = 300, unite = "kg", label = "Poids", pas = 0.1 },
        ["glasgow"] = new { min = 3, max = 15, unite = "/15", label = "Score de Glasgow", pas = 1.0 },
        ["eva"] = new { min = 0, max = 10, unite = "/10", label = "Douleur EVA", pas = 1.0 }
    };

    /// <summary>Constantes suivies dans l'espace patient, avec leurs bornes de normalité.</summary>
    static readonly object[] Mesures =
    {
        new { cle = "pas", label = "Tension (PA systolique)", unite = " mmHg", normalMin = 100.0, normalMax = 139.0 },
        new { cle = "fc", label = "Fréquence cardiaque", unite = "/min", normalMin = 60.0, normalMax = 100.0 },
        new { cle = "spo2", label = "SpO₂", unite = " %", normalMin = 95.0, normalMax = 100.0 },
        new { cle = "temperature", label = "Température", unite = " °C", normalMin = 36.0, normalMax = 37.8 },
        new { cle = "glycemie", label = "Glycémie capillaire", unite = " g/L", normalMin = 0.7, normalMax = 1.1 },
        new { cle = "poids", label = "Poids", unite = " kg", normalMin = (double?)null, normalMax = (double?)null }
    };

    /// <summary>Lit une liste d'établissement : valeur saisie, sinon valeur par défaut.</summary>
    internal static string[] Liste(IEnumerable<Models.Parametre> parametres, string cle)
    {
        var brut = parametres.FirstOrDefault(p => p.Cle == cle)?.Valeur;
        if (string.IsNullOrWhiteSpace(brut))
            return ListesParDefaut.TryGetValue(cle, out var d) ? d : Array.Empty<string>();
        return brut.Split('\n', StringSplitOptions.RemoveEmptyEntries)
            .Select(x => x.Trim()).Where(x => x.Length > 0).Distinct().ToArray();
    }

    [HttpGet, AllowAnonymous]
    public async Task<IActionResult> Get()
    {
        var parametres = await _db.Parametres.AsNoTracking().ToListAsync();
        var motifsRegles = await _db.ReglesOrientation.Select(r => r.Motif).Distinct().OrderBy(m => m).ToListAsync();
        var motifsSaisis = Liste(parametres, "liste.motifsRecours");
        var services = await _db.Services.AsNoTracking().Where(s => s.Actif)
            .OrderBy(s => s.Ordre).Select(s => new { s.Id, s.EtablissementId, s.Code, s.Nom, s.Pole }).ToListAsync();
        var etablissements = await _db.Etablissements.AsNoTracking().Where(e => e.Actif).OrderBy(e => e.Id)
            .Select(e => new { e.Id, e.Code, e.Nom, e.RoleRecherche }).ToListAsync();

        return Ok(new
        {
            roles = Roles,
            categories = Categories,
            bornes = Bornes,
            mesures = Mesures,

            // Statuts et vocabulaires portés par le modèle
            statutsPassage = new[] { "À trier", "En attente", "En cours", "Vu", "Sorti" },
            statutsRendezVous = new[] { "Demandé", "Confirmé", "Honoré", "Manqué", "Annulé", "Reprogrammé" },
            statutsLit = new[] { "Libre", "Occupé", "Bloqué" },
            avpu = new[] { "Alerte", "Réponse à la voix", "Réponse à la douleur", "Non évalué" },
            gravites = new[] { "Léger", "Modéré", "Sévère" },
            devenirs = new[] { "Réorienté (centre de santé)", "Transféré (autre hôpital)", "Reparti sans soins", "Admis plus tard", "Inconnu" },
            categoriesPiece = new[] { "Photo de plaie", "Résultat de laboratoire", "Imagerie", "Compte rendu", "Autre" },
            actionsDecision = new[]
            {
                "Admettre immédiatement dans le service", "Admettre en zone de débordement",
                "Orienter vers un autre établissement", "Différer avec nouvelle date", "Sortie après consultation"
            },
            typesAudit = new[] { "consultation", "creation", "modification", "suppression", "connexion" },
            niveauxNotification = new[] { "info", "warn", "crit" },

            // Listes propres à l'établissement
            modesEntree = Liste(parametres, "liste.modesEntree"),
            motifsBlocage = Liste(parametres, "liste.motifsBlocage"),
            typesNotification = Liste(parametres, "liste.typesNotification"),
            sallesBloc = Liste(parametres, "liste.sallesBloc"),
            antecedents = Liste(parametres, "liste.antecedents"),
            paiements = Liste(parametres, "liste.paiements"),
            canaux = Liste(parametres, "liste.canaux"),
            categoriesDiagnostic = Liste(parametres, "liste.categoriesDiagnostic"),

            // Vocabulaire harmonisé, commun au dataset et aux séjours saisis en direct
            issues = HopitalApi.Services.Recherche.Dictionnaire.Issues,
            etablissements,
            destinataires = Roles.Values.ToArray(),

            // Motifs de recours : ceux des règles d'orientation, complétés par la liste saisie
            motifsRecours = motifsRegles.Concat(motifsSaisis).Distinct().OrderBy(m => m).ToArray(),

            services,
            // Vrai tant que l'établissement n'a pas encore été configuré
            vierge = services.Count == 0
        });
    }
}
