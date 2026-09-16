using System.ComponentModel.DataAnnotations;

namespace HopitalApi.Dtos;

public record PageResult<T>(IReadOnlyList<T> Items, int Total, int Page, int PageSize)
{
    public int Pages => PageSize > 0 ? (int)Math.Ceiling((double)Total / PageSize) : 0;
}

// ── Authentification ───────────────────────────────────────
public record LoginDto([Required, EmailAddress] string Email, [Required] string MotDePasse);

public record SignupDto(
    [Required, MinLength(2)] string Nom,
    [Required, EmailAddress] string Email,
    [Required, MinLength(8, ErrorMessage = "Le mot de passe doit faire au moins 8 caractères.")] string MotDePasse,
    [Required] string Role);

public record UtilisateurDto(int Id, string Nom, string Email, string Role, int? PatientId, bool Actif,
    DateTime? DerniereConnexion, int? ServiceId = null, DateTime? CreeLe = null);

/// <summary>Création d'un compte par un administrateur (mot de passe imposé).</summary>
public record CreerCompteDto(
    [Required, MinLength(2)] string Nom,
    [Required, EmailAddress] string Email,
    [Required, MinLength(8)] string MotDePasse,
    [Required] string Role,
    int? ServiceId = null);

/// <summary>Modification d'un compte — chaque champ est facultatif.</summary>
public record MajCompteDto(string? Nom, string? Email, string? Role, bool? Actif,
    string? MotDePasse, int? ServiceId);
public record SessionDto(string Token, DateTime Expire, UtilisateurDto Utilisateur);

// ── Patient ────────────────────────────────────────────────
public record PatientDto(
    int Id, string Reference, string Nom, string Prenom, string Sexe, int Age,
    string? Telephone, string? Email, string? Quartier, string? Arrondissement,
    string Milieu, string ModePaiement, string? ContactUrgence,
    List<string> Antecedents, string? Allergies, bool Consentement, DateTime CreeLe);

public class PatientUpsertDto
{
    [Required, MinLength(2)] public string Nom { get; set; } = "";
    [Required, MinLength(2)] public string Prenom { get; set; } = "";
    [Required, RegularExpression("^[FM]$")] public string Sexe { get; set; } = "F";
    [Range(0, 120)] public int Age { get; set; }
    public string? Telephone { get; set; }
    [EmailAddress] public string? Email { get; set; }
    public string? Quartier { get; set; }
    public string? Arrondissement { get; set; }
    public string Milieu { get; set; } = "Urbain";
    public string ModePaiement { get; set; } = "Paiement direct";
    public string? ContactUrgence { get; set; }
    public List<string> Antecedents { get; set; } = new();
    public string? Allergies { get; set; }
    public bool Consentement { get; set; }
}

// ── Passage & triage ───────────────────────────────────────
public record PassageDto(
    int Id, string Reference, int PatientId, string PatientNom, int PatientAge, string PatientSexe,
    DateTime Arrivee, int AttenteMinutes, string ModeEntree, string Motif, string? MotifLibre,
    int? ServiceViseId, string? ServiceViseNom, string Statut,
    int? Categorie, int? CategorieModele, string? ValideePar, bool DelaiDepasse,
    CorrectionDto? Correction, DecisionDto? Decision, TriageDto? Triage);

public record CorrectionDto(int? Ancienne, int? Nouvelle, string? Motif, string? Auteur, DateTime? Date);
public record DecisionDto(string? Action, int? ServiceId, string? ServiceNom, string? Motif, string? Recommandation, bool Divergence, DateTime? Date);

public class PassageCreateDto
{
    [Required] public int PatientId { get; set; }
    [Required] public string ModeEntree { get; set; } = "À pied";
    [Required] public string Motif { get; set; } = "";
    public string? MotifLibre { get; set; }
    public int? ServiceViseId { get; set; }
}

/// <summary>Bornes physiologiques : une valeur hors plage est refusée, jamais corrigée en silence.</summary>
public class TriageDto
{
    [Range(30, 300, ErrorMessage = "PA systolique attendue entre 30 et 300 mmHg.")] public int? Pas { get; set; }
    [Range(10, 200, ErrorMessage = "PA diastolique attendue entre 10 et 200 mmHg.")] public int? Pad { get; set; }
    [Range(20, 250, ErrorMessage = "Fréquence cardiaque attendue entre 20 et 250 /min.")] public int? Fc { get; set; }
    [Range(4, 80, ErrorMessage = "Fréquence respiratoire attendue entre 4 et 80 /min.")] public int? Fr { get; set; }
    [Range(25, 45, ErrorMessage = "Température attendue entre 25 et 45 °C.")] public double? Temperature { get; set; }
    [Range(40, 100, ErrorMessage = "SpO₂ attendue entre 40 et 100 %.")] public int? Spo2 { get; set; }
    [Range(0.1, 10, ErrorMessage = "Glycémie attendue entre 0,1 et 10 g/L.")] public double? Glycemie { get; set; }
    [Range(0.5, 300, ErrorMessage = "Poids attendu entre 0,5 et 300 kg.")] public double? Poids { get; set; }
    public string? Avpu { get; set; }
    [Range(3, 15, ErrorMessage = "Score de Glasgow attendu entre 3 et 15.")] public int? Glasgow { get; set; }
    [Range(0, 10, ErrorMessage = "EVA attendue entre 0 et 10.")] public int? Eva { get; set; }
    [Range(1, 4)] public int? CategorieManuelle { get; set; }
}

public class TriageSubmitDto
{
    [Required] public TriageDto Constantes { get; set; } = new();
    [Range(1, 4)] public int? CategorieRetenue { get; set; }
    public string? MotifCorrection { get; set; }
}

public record ContributionDto(string Label, double Poids);
public record ScoresDerivesDto(double? IndexChoc, int? Pam, int QSofa, int QSofaConnus, int Mews);
public record EvaluationTriageDto(
    double Score, int Categorie, double Confiance, bool Incertain,
    List<string> Manquants, List<ContributionDto> Contributions,
    ScoresDerivesDto Derives, string Modele);

public class DecisionCreateDto
{
    [Required] public string Action { get; set; } = "";
    public int? ServiceId { get; set; }
    public string? Motif { get; set; }
    [Required] public string Recommandation { get; set; } = "";
}

// ── Capacité ───────────────────────────────────────────────
public record ServiceDto(
    int Id, string Code, string Nom, string Pole, bool Hospitalisation, bool UrgencesCompatible,
    int AgeMin, int AgeMax, int LitsInstalles, int LitsArmes, int Occupes, int Bloques,
    int Programmes, int Libres, double TauxOccupation, string Niveau);

public class ServiceUpdateDto
{
    [Range(0, 2000)] public int LitsInstalles { get; set; }
    [Range(0, 2000)] public int LitsArmes { get; set; }
    [Range(0, 2000)] public int Occupes { get; set; }
    [Range(0, 2000)] public int Bloques { get; set; }
    [Range(0, 2000)] public int Programmes { get; set; }
    public double Tendance { get; set; }
    public bool Actif { get; set; } = true;
}

public record PrevisionPointDto(int Jour, double Bas, double Median, double Haut, int Capacite);
public record PrevisionDto(int ServiceId, string Nom, int Capacite, List<PrevisionPointDto> Points,
    Dictionary<int, double> Risques, List<DecompositionDto> Decomposition, string Modele);
public record DecompositionDto(string Label, int Valeur);

public record SejourDto(int Id, string Reference, int PatientId, string PatientNom, int ServiceId,
    string ServiceNom, string? Lit, DateTime Entree, int Jours, string? MotifBlocage,
    double ProbaJ0, double ProbaJ1, double ProbaJ2);

public class SejourCreateDto
{
    [Required] public int PatientId { get; set; }
    [Required] public int ServiceId { get; set; }
    public int? LitId { get; set; }
    public string? MotifBlocage { get; set; }
}

// ── Programmation ──────────────────────────────────────────
public record RendezVousDto(int Id, string Reference, int PatientId, string PatientNom, string? PatientTel,
    int ServiceId, string ServiceNom, DateOnly Date, string Heure, string Motif, string Statut,
    string? Rappel, bool DemandeParPatient, bool EstChirurgie, int? DureeMinutes,
    int? LitAvalServiceId, int? DureeSejourJours, string? PerteDeChance, string? SalleBloc);

public class RendezVousCreateDto
{
    [Required] public int PatientId { get; set; }
    [Required] public int ServiceId { get; set; }
    [Required] public DateOnly Date { get; set; }
    [Required] public string Heure { get; set; } = "08:00";
    [Required, MinLength(3)] public string Motif { get; set; } = "";
    public bool EstChirurgie { get; set; }
    [Range(10, 720)] public int? DureeMinutes { get; set; }
    public int? LitAvalServiceId { get; set; }
    [Range(0, 90)] public int? DureeSejourJours { get; set; }
    public string? PerteDeChance { get; set; }
    public string? SalleBloc { get; set; }
}

// ── Divers ─────────────────────────────────────────────────
public record DemandeDto(int Id, string Reference, DateTime Date, int ServiceId, string ServiceNom,
    int? PatientId, string Motif, string Gravite, string Devenir);

public class DemandeCreateDto
{
    [Required] public int ServiceId { get; set; }
    public int? PatientId { get; set; }
    [Required, MinLength(3)] public string Motif { get; set; } = "";
    [Required] public string Gravite { get; set; } = "Modéré";
    [Required] public string Devenir { get; set; } = "Inconnu";
}

public record NotificationDto(int Id, DateTime Date, string Destinataire, string Type, string Texte,
    string Niveau, string Canal, bool Lue);

public class NotificationCreateDto
{
    [Required] public string Destinataire { get; set; } = "";
    [Required] public string Type { get; set; } = "Information";
    [Required, MaxLength(320)] public string Texte { get; set; } = "";
    public string Niveau { get; set; } = "info";
    public string Canal { get; set; } = "Application";
    public int? PatientId { get; set; }
}

public record AuditDto(int Id, DateTime Date, string Utilisateur, string Role, string Type,
    string Action, string? Cible, string? Detail);

public record PredictionDto(int Id, DateTime Date, int? PassageId, string Modele, string TypeModele,
    double Score, int Sortie, double Confiance, int? DecisionHumaine, bool Ecart, string ExplicationJson);

public record ParametreDto(string Cle, string Valeur, string? Libelle);

public record PieceJointeDto(int Id, int PatientId, int? PassageId, string NomFichier, string TypeMime,
    long Taille, string Categorie, DateTime DeposeLe, string? DeposePar);

public record RechercheResultatDto(string Type, int Id, string Titre, string SousTitre, string Lien);

public record TableauBordDto(
    int PatientsTotal, int PassagesAujourdhui, int EnAttente, int ATrier, int DelaisDepasses,
    int LitsArmes, int LitsOccupes, int LitsBloques, int LitsLibres, double TauxOccupation,
    int AttenteMoyenneMinutes, int SejoursEnCours, int RendezVousAVenir, int DemandesNonSatisfaites,
    List<ServiceRisqueDto> Risques, List<int> FluxHoraire, List<string> LabelsHoraire);

public record ServiceRisqueDto(int ServiceId, string Nom, double TauxOccupation, double Risque, string Niveau);

public record QualiteDto(
    int PredictionsTotal, int Ecarts, double TauxCorrection,
    List<CompletudeDto> Completude, List<EquiteDto> Equite, string Avertissement);
public record CompletudeDto(string Champ, int Renseignes, int Total, double Taux);
public record EquiteDto(string Groupe, int Effectif, double TauxCorrection, double CategorieMoyenne);
