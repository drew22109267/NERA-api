namespace HopitalApi.Models;

// ── Dataset de recherche : registres historiques importés, anonymisés ─────────
//
// Chaque hôpital tient ses registres à sa manière. Les lignes importées gardent
// le texte d'origine (« …Brut ») et, à côté, la valeur harmonisée selon le
// dictionnaire commun aux hôpitaux. Une valeur qui n'a pas de correspondance
// reste nulle : elle n'est jamais devinée. Aucun nom, prénom ni téléphone n'est
// stocké — seulement un identifiant anonyme.

/// <summary>Lot d'import : un fichier d'un registre d'un hôpital, avec son rapport.</summary>
public class LotImport
{
    public int Id { get; set; }
    public int EtablissementId { get; set; }
    public Etablissement? Etablissement { get; set; }
    /// <summary>hospitalisation · consultation</summary>
    public string Registre { get; set; } = "";
    public int? ServiceParDefautId { get; set; }
    public string NomFichier { get; set; } = "";
    public DateTime ImporteLe { get; set; } = DateTime.UtcNow;
    public string? ImportePar { get; set; }
    public int LignesLues { get; set; }
    public int LignesImportees { get; set; }
    public int LignesRejetees { get; set; }
    public int Doublons { get; set; }
    public string RapportJson { get; set; } = "{}";
}

/// <summary>Une ligne du registre d'hospitalisation (module lits, gravité à l'admission).</summary>
public class EnregistrementHospitalisation
{
    public int Id { get; set; }
    public int EtablissementId { get; set; }
    public Etablissement? Etablissement { get; set; }
    public int? ServiceId { get; set; }
    public Service? Service { get; set; }
    public int LotImportId { get; set; }
    public LotImport? LotImport { get; set; }
    public int NumeroLigne { get; set; }

    public string? IdAnonyme { get; set; }
    public string? ServiceBrut { get; set; }
    /// <summary>Date à laquelle la ligne a été écrite dans le registre (peut suivre l'admission).</summary>
    public DateOnly? DateEnregistrement { get; set; }
    /// <summary>Date d'admission effective à l'hôpital : c'est elle qui compte pour l'occupation.</summary>
    public DateOnly DateEntree { get; set; }
    /// <summary>Null = sortie non renseignée et durée inconnue.</summary>
    public DateOnly? DateSortie { get; set; }
    /// <summary>Vrai quand la sortie n'est pas écrite et vaut date d'entrée + nombre de jours.</summary>
    public bool DateSortieCalculee { get; set; }
    public int? DureeJoursDeclaree { get; set; }
    public string? AncienNouveauBrut { get; set; }
    /// <summary>Nouveau · Ancien (déjà hospitalisé auparavant).</summary>
    public string? AncienNouveau { get; set; }

    public double? AgeValeur { get; set; }
    public string? AgeUnite { get; set; }
    public double? AgeMois { get; set; }
    public string? SexeBrut { get; set; }
    public string? Sexe { get; set; }
    public string? Quartier { get; set; }

    public string? DiagnosticEntreeBrut { get; set; }
    public string? DiagnosticEntree { get; set; }
    public string? Bilan { get; set; }
    public string? TraitementInitial { get; set; }
    public string? GeTdrBrut { get; set; }
    /// <summary>Positif · Négatif — goutte épaisse ou TDR du paludisme.</summary>
    public string? GeTdr { get; set; }
    /// <summary>Densité parasitaire écrite avec le résultat (trophozoïtes/µL).</summary>
    public double? DensiteParasitaire { get; set; }

    // Paramètres à l'admission, relevés dans le dossier médical (base du score de gravité).
    public double? Temperature { get; set; }
    public int? Fc { get; set; }
    public int? Fr { get; set; }
    public int? Spo2 { get; set; }
    public double? Poids { get; set; }
    public int? Pas { get; set; }
    public int? Pad { get; set; }

    // Connues seulement après la sortie : jamais utilisables comme prédicteurs.
    public string? DiagnosticSortieBrut { get; set; }
    public string? DiagnosticSortie { get; set; }
    public string? TraitementSortie { get; set; }
    public string? IssueBrute { get; set; }
    public string? Issue { get; set; }
    public decimal? Prix { get; set; }
}

/// <summary>Une ligne du registre de consultation (module triage).</summary>
public class EnregistrementConsultation
{
    public int Id { get; set; }
    public int EtablissementId { get; set; }
    public Etablissement? Etablissement { get; set; }
    public int? ServiceId { get; set; }
    public Service? Service { get; set; }
    public int LotImportId { get; set; }
    public LotImport? LotImport { get; set; }
    public int NumeroLigne { get; set; }

    public string? IdAnonyme { get; set; }
    public string? ServiceBrut { get; set; }
    public DateOnly Date { get; set; }

    public double? AgeValeur { get; set; }
    public string? AgeUnite { get; set; }
    public double? AgeMois { get; set; }
    public string? SexeBrut { get; set; }
    public string? Sexe { get; set; }
    public string? Quartier { get; set; }

    public string? SymptomesBrut { get; set; }
    public string? Motif { get; set; }
    public int? Fc { get; set; }
    public int? Pas { get; set; }
    public int? Pad { get; set; }
    public int? Fr { get; set; }
    public double? Temperature { get; set; }
    public int? Spo2 { get; set; }
    public double? Poids { get; set; }

    public string? OrientationBrute { get; set; }
    public string? Orientation { get; set; }
}

/// <summary>
/// Déclaration, par hôpital, de la colonne de son registre qui porte une variable
/// harmonisée. NomColonne null = l'hôpital n'enregistre pas cette variable.
/// </summary>
public class ColonneSource
{
    public int Id { get; set; }
    public int EtablissementId { get; set; }
    public Etablissement? Etablissement { get; set; }
    public string Registre { get; set; } = "";
    public string VariableCode { get; set; } = "";
    public string? NomColonne { get; set; }
    /// <summary>Unité d'âge déclarée par l'hôpital quand son registre ne la précise pas.</summary>
    public string? ValeurFixe { get; set; }
    public string? Note { get; set; }
}

/// <summary>Correspondance, par hôpital, d'une valeur brute vers la valeur harmonisée.</summary>
public class Correspondance
{
    public int Id { get; set; }
    public int EtablissementId { get; set; }
    public Etablissement? Etablissement { get; set; }
    public string VariableCode { get; set; } = "";
    /// <summary>Clé de comparaison : minuscules, sans accents ni espaces superflus.</summary>
    public string Cle { get; set; } = "";
    public string ValeurBrute { get; set; } = "";
    public string ValeurNormalisee { get; set; } = "";
}
