using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace HopitalApi.Services.Recherche;

/// <summary>
/// Variable du dataset harmonisé, commune à tous les hôpitaux.
/// Usage : identifiant · contrôle · prédicteur · cible · post-sortie (connue
/// seulement après la sortie, donc exclue des prédicteurs pour éviter la fuite).
/// Valeurs : vocabulaire fixe du protocole ; ListeParametre : liste saisie dans
/// Administration (catégories de diagnostic, motifs) ; aucun des deux = texte libre.
/// </summary>
public record VariableHarmonisee(
    string Code, string Libelle, string Registre, string Type, string Usage,
    bool Requise = false, string[]? Valeurs = null, string? ListeParametre = null, string? Aide = null)
{
    public bool Categorielle => Valeurs is not null || ListeParametre is not null;
}

public static class Dictionnaire
{
    public const string Hospitalisation = "hospitalisation";
    public const string Consultation = "consultation";
    public static readonly string[] Registres = { Hospitalisation, Consultation };

    public static readonly string[] Roles = { "Développement", "Validation externe" };

    public static readonly string[] Sexes = { "M", "F" };
    public static readonly string[] UnitesAge = { "jours", "mois", "ans" };
    /// <summary>
    /// Transfert interne = vers un autre service du même hôpital (le patient reste hospitalisé) ;
    /// transfert externe = vers un autre hôpital. Le vocabulaire des registres (« référé », « déféré »…)
    /// s'y rattache par les correspondances de chaque hôpital.
    /// </summary>
    public static readonly string[] Issues = { "Sortie", "Transfert interne", "Transfert externe", "Décès", "Sortie contre avis médical", "Évasion" };
    public static readonly string[] Orientations = { "Domicile", "Hospitalisé", "Transfert externe", "Décédé" };
    public static readonly string[] AncienNouveau = { "Nouveau", "Ancien" };
    public static readonly string[] ResultatsGe = { "Positif", "Négatif" };

    public const string ListeDiagnostics = "liste.categoriesDiagnostic";
    public const string ListeMotifs = "liste.motifsRecours";

    public static readonly VariableHarmonisee[] Variables =
    {
        // ── Registre d'hospitalisation ──
        new("id_anonyme", "Identifiant anonyme", Hospitalisation, "texte", "identifiant",
            Aide: "Jamais le nom ni le téléphone : un code attribué sur place (ex. PED-0001)."),
        new("service", "Service", Hospitalisation, "service", "contrôle",
            Aide: "Code ou nom du service ; sinon le service choisi à l'import."),
        new("date_enregistrement", "Date d'enregistrement", Hospitalisation, "date", "contrôle",
            Aide: "Jour où la ligne est écrite dans le registre (2ᵉ colonne en pédiatrie)."),
        new("date_entree", "Date d'entrée (admission effective)", Hospitalisation, "date", "contrôle", Requise: true,
            Aide: "Jour où l'enfant est réellement admis : c'est elle qui compte pour l'occupation des lits."),
        new("date_sortie", "Date de sortie", Hospitalisation, "date", "cible",
            Aide: "Si elle n'est pas écrite, elle est calculée avec le nombre de jours, et marquée comme calculée."),
        new("duree_jours", "Nombre de jours d'hospitalisation", Hospitalisation, "entier", "contrôle",
            Aide: "Sert à calculer la sortie manquante ; comparé à l'écart entre les dates quand les deux existent."),
        new("ancien_nouveau", "Ancien / nouveau patient", Hospitalisation, "categorie", "prédicteur", Valeurs: AncienNouveau,
            Aide: "« N » = nouveau, « A » = ancien (déjà hospitalisé)."),
        new("age", "Âge", Hospitalisation, "age", "prédicteur",
            Aide: "Peut contenir l'unité (« 3 mois », « 5 j », « 2 ans »)."),
        new("age_unite", "Unité de l'âge", Hospitalisation, "unite_age", "contrôle", Valeurs: UnitesAge),
        new("sexe", "Sexe", Hospitalisation, "categorie", "prédicteur", Valeurs: Sexes),
        new("quartier", "Quartier de résidence", Hospitalisation, "texte", "prédicteur"),
        new("diagnostic_entree", "Diagnostic à l'arrivée", Hospitalisation, "categorie", "prédicteur",
            ListeParametre: ListeDiagnostics),
        new("bilan", "Bilan demandé", Hospitalisation, "texte", "prédicteur"),
        new("traitement_initial", "Traitement reçu", Hospitalisation, "texte", "prédicteur",
            Aide: "Prédicteur seulement s'il est donné dans les premières heures."),
        new("ge_tdr", "GE / TDR paludisme", Hospitalisation, "categorie", "prédicteur", Valeurs: ResultatsGe,
            Aide: "« GE+ », « GE (−) », « TDR + »… La densité écrite à côté (ex. 72 000 Tpf/µl) est gardée."),
        new("temperature", "Température à l'admission", Hospitalisation, "decimal", "prédicteur",
            Aide: "Relevée dans le dossier médical."),
        new("fc", "Pouls à l'admission", Hospitalisation, "entier", "prédicteur", Aide: "Relevé dans le dossier médical."),
        new("fr", "Fréquence respiratoire à l'admission", Hospitalisation, "entier", "prédicteur", Aide: "Relevée dans le dossier médical."),
        new("spo2", "SpO₂ à l'admission", Hospitalisation, "entier", "prédicteur", Aide: "Relevée dans le dossier médical."),
        new("poids", "Poids à l'admission", Hospitalisation, "decimal", "prédicteur", Aide: "Relevé dans le dossier médical."),
        new("pas", "Tension à l'admission", Hospitalisation, "entier", "prédicteur",
            Aide: "Relevée dans le dossier médical ; « 12/8 » est lu comme 120/80."),
        new("pad", "Tension diastolique à l'admission", Hospitalisation, "entier", "prédicteur"),
        new("diagnostic_sortie", "Diagnostic de sortie", Hospitalisation, "categorie", "post-sortie",
            ListeParametre: ListeDiagnostics),
        new("traitement_sortie", "Traitement de sortie", Hospitalisation, "texte", "post-sortie"),
        new("issue", "Issue (observation)", Hospitalisation, "categorie", "cible", Valeurs: Issues),
        new("prix", "Prix à la sortie", Hospitalisation, "decimal", "post-sortie"),

        // ── Registre de consultation ──
        new("id_anonyme", "Identifiant anonyme", Consultation, "texte", "identifiant",
            Aide: "Le même que dans le registre d'hospitalisation pour relier les deux."),
        new("service", "Service", Consultation, "service", "contrôle"),
        new("date", "Date de consultation", Consultation, "date", "contrôle", Requise: true),
        new("age", "Âge", Consultation, "age", "prédicteur"),
        new("age_unite", "Unité de l'âge", Consultation, "unite_age", "contrôle", Valeurs: UnitesAge),
        new("sexe", "Sexe", Consultation, "categorie", "prédicteur", Valeurs: Sexes),
        new("quartier", "Quartier de résidence", Consultation, "texte", "prédicteur"),
        new("symptomes", "Symptômes / motif", Consultation, "categorie", "prédicteur", ListeParametre: ListeMotifs),
        new("fc", "Pouls (FC)", Consultation, "entier", "prédicteur"),
        new("pas", "Tension systolique", Consultation, "entier", "prédicteur",
            Aide: "Une tension notée « 120/80 » remplit aussi la diastolique."),
        new("pad", "Tension diastolique", Consultation, "entier", "prédicteur"),
        new("fr", "Fréquence respiratoire", Consultation, "entier", "prédicteur"),
        new("temperature", "Température", Consultation, "decimal", "prédicteur"),
        new("spo2", "SpO₂", Consultation, "entier", "prédicteur"),
        new("poids", "Poids", Consultation, "decimal", "prédicteur"),
        new("orientation", "Orientation / conduite à tenir", Consultation, "categorie", "cible", Valeurs: Orientations,
            Aide: "Si le registre ne la note pas, elle se déduit du croisement avec le registre d'hospitalisation.")
    };

    public static IEnumerable<VariableHarmonisee> DuRegistre(string registre) => Variables.Where(v => v.Registre == registre);

    /// <summary>
    /// Variables qui partagent leurs correspondances : le diagnostic d'entrée et celui
    /// de sortie utilisent la même liste, une abréviation s'harmonise donc une seule fois.
    /// </summary>
    public static string GroupeCorrespondance(string code) => code == "diagnostic_sortie" ? "diagnostic_entree" : code;

    /// <summary>
    /// Une déclaration couvre-t-elle la variable ? Le service est toujours connu (sa colonne
    /// ou le service choisi à l'import), la diastolique se lit dans « 120/80 », l'unité dans « 3 mois ».
    /// </summary>
    public static bool Couverte(string variable, string declaration) => variable switch
    {
        "service" => true,
        "pad" => declaration is "pad" or "pas",
        "age_unite" => declaration is "age_unite" or "age",
        _ => declaration == variable
    };

    public static VariableHarmonisee? Trouver(string registre, string code) =>
        Variables.FirstOrDefault(v => v.Registre == registre && v.Code == code);

    /// <summary>Bornes physiologiques — identiques à celles de la fiche de triage.</summary>
    public static readonly Dictionary<string, (double Min, double Max)> Bornes = new()
    {
        ["fc"] = (20, 250), ["pas"] = (30, 300), ["pad"] = (10, 200), ["fr"] = (4, 80),
        ["temperature"] = (25, 45), ["spo2"] = (40, 100), ["poids"] = (0.3, 300)
    };

    /// <summary>Intitulés de colonne qui désignent une donnée identifiante : jamais importés.</summary>
    static readonly string[] Identifiants = { "nom", "prenom", "prenoms", "nom et prenom", "nom prenom", "noms",
        "telephone", "tel", "tel.", "contact", "numero de telephone", "portable", "cni" };

    /// <summary>
    /// « Noms et prénoms », « Nom », « Prénom(s) », « Contact », « Téléphone »… mais pas
    /// « Nombre de jours » : le mot « nom » doit être un mot entier.
    /// </summary>
    public static bool EstIdentifiant(string colonne)
    {
        var k = Cle(colonne);
        return Identifiants.Contains(k) || Regex.IsMatch(k, @"\bnoms?\b|\bprenoms?\b|telephone|\bcontacts?\b|\btel\b");
    }

    // ── Lecture des valeurs ────────────────────────────────────────────────

    /// <summary>Clé de comparaison : minuscules, sans accents, espaces réduits.</summary>
    public static string Cle(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return "";
        var d = s.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder(d.Length);
        foreach (var c in d)
            if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(c);
        return Regex.Replace(sb.ToString().Normalize(NormalizationForm.FormC), @"\s+", " ");
    }

    static readonly string[] FormatsDate =
    {
        "dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy", "dd.MM.yyyy", "yyyy-MM-dd", "yyyy/MM/dd",
        "dd/MM/yy", "d/M/yy", "dd-MM-yy", "d-M-yy",
        "dd/MM/yyyy HH:mm", "dd/MM/yyyy H:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-ddTHH:mm:ss"
    };

    public static DateOnly? LireDate(string? brut)
    {
        if (string.IsNullOrWhiteSpace(brut)) return null;
        var s = brut.Trim();
        if (DateTime.TryParseExact(s, FormatsDate, CultureInfo.InvariantCulture, DateTimeStyles.None, out var d))
            return DateOnly.FromDateTime(d);
        // Date restée au format numérique d'Excel (jours depuis 1899-12-30).
        if (double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var serie) && serie is > 20000 and < 80000)
            return DateOnly.FromDateTime(DateTime.FromOADate(serie));
        return null;
    }

    public static double? LireNombre(string? brut)
    {
        if (string.IsNullOrWhiteSpace(brut)) return null;
        var s = Regex.Replace(brut.Trim(), @"[\s ]", "").Replace(',', '.');
        var m = Regex.Match(s, @"^-?\d+(\.\d+)?");
        return m.Success && double.TryParse(m.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : null;
    }

    /// <summary>Unité d'âge écrite en toutes lettres ou abrégée. Null si absente ou inconnue.</summary>
    public static string? LireUnite(string? brut)
    {
        var k = Cle(brut).Trim('.', ' ');
        return k switch
        {
            "j" or "jr" or "jrs" or "jour" or "jours" or "nj" => "jours",
            "m" or "mo" or "mois" => "mois",
            "a" or "an" or "ans" or "annee" or "annees" => "ans",
            _ => null
        };
    }

    /// <summary>« 3 mois », « 5j », « 2 ans » → (valeur, unité). L'unité reste nulle si elle n'est pas écrite.</summary>
    public static (double? Valeur, string? Unite) LireAge(string? brut)
    {
        if (string.IsNullOrWhiteSpace(brut)) return (null, null);
        var m = Regex.Match(Cle(brut).Replace(',', '.'), @"^(\d+(\.\d+)?)\s*([a-z.]*)$");
        if (!m.Success) return (null, null);
        var v = double.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
        return (v, LireUnite(m.Groups[3].Value));
    }

    public static double? AgeEnMois(double? valeur, string? unite) => valeur is null || unite is null ? null : unite switch
    {
        "jours" => Math.Round(valeur.Value / 30.4375, 2),
        "mois" => valeur.Value,
        "ans" => valeur.Value * 12,
        _ => null
    };

    /// <summary>« N » / « nouveau » → Nouveau ; « A » / « ancien » → Ancien. Null sinon.</summary>
    public static string? LireAncienNouveau(string? brut) => Cle(brut).Trim('.', ' ') switch
    {
        "n" or "nouveau" or "nouvelle" => "Nouveau",
        "a" or "ancien" or "ancienne" => "Ancien",
        _ => null
    };

    /// <summary>
    /// Résultat de GE/TDR tel qu'écrit dans le registre : un signe + ou − (ou positif/négatif)
    /// sans ambiguïté donne le résultat ; la densité parasitaire écrite à côté est extraite.
    /// Un résultat ambigu (les deux signes, ou aucun) reste nul.
    /// </summary>
    public static (string? Resultat, double? Densite) LireGe(string? brut)
    {
        if (string.IsNullOrWhiteSpace(brut)) return (null, null);
        var k = Cle(brut).Replace('−', '-').Replace('–', '-');
        var pos = k.Contains('+') || k.Contains("positi");
        var neg = Regex.IsMatch(k, @"(^|[\s(])-|\(-\)|negati");
        var resultat = pos && !neg ? "Positif" : neg && !pos ? "Négatif" : null;
        var m = Regex.Match(k, @"\d[\d\s.]*\d|\d");
        double? densite = null;
        if (m.Success && double.TryParse(Regex.Replace(m.Value, @"[\s.]", ""), NumberStyles.Float, CultureInfo.InvariantCulture, out var d) && d >= 10)
            densite = d;
        return (resultat, densite);
    }

    /// <summary>
    /// Tension « 120/80 » → (120, 80). Une tension notée en cmHg (« 12/8 »,
    /// usage courant) est convertie en mmHg et signalée par <c>Cmhg = true</c>.
    /// </summary>
    public static (int? Pas, int? Pad, bool Cmhg) LireTension(string? brut)
    {
        if (string.IsNullOrWhiteSpace(brut)) return (null, null, false);
        var m = Regex.Match(brut.Replace(',', '.'), @"(\d{1,3}(\.\d)?)\s*/\s*(\d{1,3}(\.\d)?)");
        if (m.Success)
        {
            var pas = double.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
            var pad = double.Parse(m.Groups[3].Value, CultureInfo.InvariantCulture);
            if (pas < 30 && pad < 20) return ((int)Math.Round(pas * 10), (int)Math.Round(pad * 10), true);
            return ((int)Math.Round(pas), (int)Math.Round(pad), false);
        }
        var n = LireNombre(brut);
        return (n is null ? null : (int)Math.Round(n.Value), null, false);
    }
}
