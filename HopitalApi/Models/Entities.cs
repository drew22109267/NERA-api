namespace HopitalApi.Models;

/// <summary>Établissement — prévu pour un déploiement multi-sites.</summary>
public class Etablissement
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Nom { get; set; } = "";
    public string Categorie { get; set; } = "1re catégorie";
    public string Ville { get; set; } = "";
    public string Region { get; set; } = "";
    public bool Actif { get; set; } = true;
    /// <summary>Rôle dans l'étude : « Développement » (hôpital A) · « Validation externe » (hôpital B) · vide.</summary>
    public string RoleRecherche { get; set; } = "";

    public List<Service> Services { get; set; } = new();
}

/// <summary>Service / unité clinique. `Pole` regroupe les services pour la redistribution.</summary>
public class Service
{
    public int Id { get; set; }
    public int EtablissementId { get; set; }
    public Etablissement? Etablissement { get; set; }

    public string Code { get; set; } = "";
    public string Nom { get; set; } = "";
    public string Pole { get; set; } = "";
    public bool Hospitalisation { get; set; } = true;
    public bool UrgencesCompatible { get; set; }
    public int AgeMin { get; set; }
    public int AgeMax { get; set; } = 120;

    public int LitsInstalles { get; set; }
    public int LitsArmes { get; set; }
    public int Occupes { get; set; }
    public int Bloques { get; set; }
    public int Programmes { get; set; }
    public double Tendance { get; set; }

    public int Ordre { get; set; }
    public bool Actif { get; set; } = true;

    public List<Lit> Lits { get; set; } = new();
}

public class Lit
{
    public int Id { get; set; }
    public int ServiceId { get; set; }
    public Service? Service { get; set; }
    public string Code { get; set; } = "";
    /// <summary>Libre · Occupé · Bloqué · Hors service</summary>
    public string Statut { get; set; } = "Libre";
    public string? MotifBlocage { get; set; }
}

public class Utilisateur
{
    public int Id { get; set; }
    public string Nom { get; set; } = "";
    public string Email { get; set; } = "";
    public string MotDePasseHash { get; set; } = "";
    /// <summary>accueil · infirmier · medecin · gestionnaire · direction · data · admin · patient</summary>
    public string Role { get; set; } = "infirmier";
    public int? ServiceId { get; set; }
    public int? PatientId { get; set; }
    public bool Actif { get; set; } = true;
    public DateTime CreeLe { get; set; } = DateTime.UtcNow;
    public DateTime? DerniereConnexion { get; set; }
}

public class Patient
{
    public int Id { get; set; }
    public string Reference { get; set; } = "";
    public string Nom { get; set; } = "";
    public string Prenom { get; set; } = "";
    public string Sexe { get; set; } = "F";
    public int Age { get; set; }
    public DateOnly? DateNaissance { get; set; }
    public string? Telephone { get; set; }
    public string? Email { get; set; }
    public string? Quartier { get; set; }
    public string? Arrondissement { get; set; }
    public string Milieu { get; set; } = "Urbain";
    public string ModePaiement { get; set; } = "Paiement direct";
    public string? ContactUrgence { get; set; }
    public List<string> Antecedents { get; set; } = new();
    public string? Allergies { get; set; }
    public bool Consentement { get; set; }
    public DateTime CreeLe { get; set; } = DateTime.UtcNow;

    public List<Passage> Passages { get; set; } = new();
    public List<Sejour> Sejours { get; set; } = new();
    public List<RendezVous> RendezVous { get; set; } = new();
    public List<PieceJointe> PiecesJointes { get; set; } = new();
}

public class Passage
{
    public int Id { get; set; }
    public string Reference { get; set; } = "";
    public int PatientId { get; set; }
    public Patient? Patient { get; set; }

    public DateTime Arrivee { get; set; } = DateTime.UtcNow;
    public string ModeEntree { get; set; } = "À pied";
    public string Motif { get; set; } = "";
    public string? MotifLibre { get; set; }
    public int? ServiceViseId { get; set; }
    public Service? ServiceVise { get; set; }

    /// <summary>À trier · En attente · En cours · Vu · Sorti</summary>
    public string Statut { get; set; } = "À trier";

    public int? Categorie { get; set; }
    public int? CategorieModele { get; set; }
    public string? ValideePar { get; set; }
    public DateTime? TriageLe { get; set; }

    public int? CorrectionAncienne { get; set; }
    public int? CorrectionNouvelle { get; set; }
    public string? CorrectionMotif { get; set; }
    public string? CorrectionAuteur { get; set; }
    public DateTime? CorrectionLe { get; set; }

    public string? DecisionAction { get; set; }
    public int? DecisionServiceId { get; set; }
    public string? DecisionMotif { get; set; }
    public string? DecisionRecommandation { get; set; }
    public bool DecisionDivergence { get; set; }
    public DateTime? DecisionLe { get; set; }

    public Triage? Triage { get; set; }
}

/// <summary>Constantes relevées au poste de triage. Toute valeur non mesurée reste nulle.</summary>
public class Triage
{
    public int Id { get; set; }
    public int PassageId { get; set; }
    public Passage? Passage { get; set; }

    public int? Pas { get; set; }
    public int? Pad { get; set; }
    public int? Fc { get; set; }
    public int? Fr { get; set; }
    public double? Temperature { get; set; }
    public int? Spo2 { get; set; }
    public double? Glycemie { get; set; }
    public double? Poids { get; set; }
    public string? Avpu { get; set; }
    public int? Glasgow { get; set; }
    public int? Eva { get; set; }
    public int? CategorieManuelle { get; set; }
    public DateTime EnregistreLe { get; set; } = DateTime.UtcNow;
    public string? EnregistrePar { get; set; }
}

public class Sejour
{
    public int Id { get; set; }
    public string Reference { get; set; } = "";
    public int PatientId { get; set; }
    public Patient? Patient { get; set; }
    public int ServiceId { get; set; }
    public Service? Service { get; set; }
    public int? LitId { get; set; }
    public Lit? Lit { get; set; }
    public DateTime Entree { get; set; } = DateTime.UtcNow;
    public DateTime? Sortie { get; set; }
    public string? MotifBlocage { get; set; }
    public string Statut { get; set; } = "En cours";
    /// <summary>Catégorie de diagnostic d'entrée, même liste que le dataset harmonisé.</summary>
    public string? DiagnosticEntree { get; set; }
    /// <summary>Issue à la sortie, même vocabulaire que le dataset harmonisé.</summary>
    public string? Issue { get; set; }
}

public class RendezVous
{
    public int Id { get; set; }
    public string Reference { get; set; } = "";
    public int PatientId { get; set; }
    public Patient? Patient { get; set; }
    public int ServiceId { get; set; }
    public Service? Service { get; set; }
    public DateOnly Date { get; set; }
    public string Heure { get; set; } = "08:00";
    public string Motif { get; set; } = "";
    /// <summary>Demandé · Confirmé · Honoré · Manqué · Annulé · Reprogrammé</summary>
    public string Statut { get; set; } = "Confirmé";
    public string? Rappel { get; set; }
    public bool DemandeParPatient { get; set; }

    public bool EstChirurgie { get; set; }
    public int? DureeMinutes { get; set; }
    public int? LitAvalServiceId { get; set; }
    public int? DureeSejourJours { get; set; }
    public string? PerteDeChance { get; set; }
    public string? SalleBloc { get; set; }
}

public class DemandeNonSatisfaite
{
    public int Id { get; set; }
    public string Reference { get; set; } = "";
    public DateTime Date { get; set; } = DateTime.UtcNow;
    public int ServiceId { get; set; }
    public Service? Service { get; set; }
    public int? PatientId { get; set; }
    public string Motif { get; set; } = "";
    public string Gravite { get; set; } = "Modéré";
    public string Devenir { get; set; } = "Inconnu";
}

public class Notification
{
    public int Id { get; set; }
    public DateTime Date { get; set; } = DateTime.UtcNow;
    public string Destinataire { get; set; } = "";
    public int? UtilisateurId { get; set; }
    public int? PatientId { get; set; }
    public string Type { get; set; } = "Information";
    public string Texte { get; set; } = "";
    /// <summary>crit · warn · info</summary>
    public string Niveau { get; set; } = "info";
    public string Canal { get; set; } = "Application";
    public bool Lue { get; set; }
}

/// <summary>Journal de toute sortie de modèle, avec la décision humaine correspondante.</summary>
public class PredictionLog
{
    public int Id { get; set; }
    public DateTime Date { get; set; } = DateTime.UtcNow;
    public int? PassageId { get; set; }
    public string Modele { get; set; } = "";
    public string TypeModele { get; set; } = "triage";
    public double Score { get; set; }
    public int Sortie { get; set; }
    public double Confiance { get; set; }
    public string ExplicationJson { get; set; } = "[]";
    public string EntreeJson { get; set; } = "{}";
    public int? DecisionHumaine { get; set; }
    public bool Ecart { get; set; }
}

/// <summary>Journal d'audit : actions ET simples consultations de dossier.</summary>
public class AuditLog
{
    public int Id { get; set; }
    public DateTime Date { get; set; } = DateTime.UtcNow;
    public int? UtilisateurId { get; set; }
    public string Utilisateur { get; set; } = "";
    public string Role { get; set; } = "";
    /// <summary>consultation · creation · modification · suppression · connexion</summary>
    public string Type { get; set; } = "consultation";
    public string Action { get; set; } = "";
    public string? Cible { get; set; }
    public string? Detail { get; set; }
    public string? AdresseIp { get; set; }
}

public class PieceJointe
{
    public int Id { get; set; }
    public int PatientId { get; set; }
    public Patient? Patient { get; set; }
    public int? PassageId { get; set; }
    public string NomFichier { get; set; } = "";
    public string TypeMime { get; set; } = "";
    public long Taille { get; set; }
    /// <summary>Photo de plaie · Résultat de laboratoire · Imagerie · Compte rendu · Autre</summary>
    public string Categorie { get; set; } = "Autre";
    public string CheminStockage { get; set; } = "";
    public DateTime DeposeLe { get; set; } = DateTime.UtcNow;
    public string? DeposePar { get; set; }
}

/// <summary>Règle d'orientation : motif clinique → service d'accueil, avec contraintes.</summary>
public class RegleOrientation
{
    public int Id { get; set; }
    public string Motif { get; set; } = "";
    public string ServiceCode { get; set; } = "";
    public string? ServiceAlternatifCode { get; set; }
    public int Priorite { get; set; } = 1;
    public int AgeMin { get; set; }
    public int AgeMax { get; set; } = 120;
    public string? SexeRequis { get; set; }
    public int? CategorieMax { get; set; }
    public string? Commentaire { get; set; }
}

public class Parametre
{
    public int Id { get; set; }
    public string Cle { get; set; } = "";
    public string Valeur { get; set; } = "";
    public string? Libelle { get; set; }
}
