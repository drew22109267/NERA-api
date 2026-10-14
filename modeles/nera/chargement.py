"""
Lecture de l'export « dataset harmonisé » de l'application NERA et préparation des séjours.

L'export (Dataset de recherche › Imports & export › Registre d'hospitalisation) est un CSV
séparé par « ; », une ligne par séjour, dates au format aaaa-mm-jj. Les valeurs y sont déjà
harmonisées (issue, sexe, diagnostic…) ; le texte d'origine reste dans la base.

Statut de la sortie d'un séjour — rien n'est inventé :
  observee  : date de sortie écrite dans le registre ;
  calculee  : sortie absente du registre, déduite de « date d'entrée + nombre de jours »
              (calcul fait à l'import, marqué sortie_calculee = 1) ;
  censuree  : pas de sortie, admission récente par rapport à la date d'extraction :
              l'enfant est probablement encore hospitalisé, sa durée est « au moins … » ;
  inconnue  : pas de sortie, pas de nombre de jours, admission ancienne : la durée est
              réellement inconnue. Ces séjours sont exclus du comptage et dénombrés à part.

Deux façons de compter le « nombre de jours » coexistent dans les registres (selon le médecin) :
  - les NUITS          : entré le 02, « 3 jrs » → sorti le 05      sortie = e + n
  - jours INCLUSIFS    : entré le 02, « 3 jrs » → sorti le 04      sortie = e + n − 1
Pour une sortie calculée, on ne sait donc pas laquelle s'applique. On garde les deux sorties
possibles (sortie = e + n, borne haute ; sortie_basse = e + n − 1) et la probabilité p_inclusif
que la ligne soit inclusive, estimée sur les lignes où la sortie EST écrite
(voir convention_nombre_de_jours). nera.occupation en déduit l'occupation attendue et ses bornes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import imputation, verrou

COLONNES_DATES = ["date_enregistrement", "date_entree", "date_sortie"]
COLONNES_NOMBRES = ["duree_jours", "age", "age_mois", "temperature", "fc", "fr", "spo2", "poids",
                    "pas", "pad", "prix", "densite_parasitaire", "duree_sejour_jours"]

# Issues harmonisées (vocabulaire de l'application) : chacune est un événement concurrent.
ISSUES = ["Sortie", "Transfert interne", "Transfert externe", "Décès", "Sortie contre avis médical", "Évasion"]


def lire_export(chemin: str | Path, confirmation_coffre: str | None = None) -> pd.DataFrame:
    """
    Lit l'export CSV de l'application et convertit les dates et les nombres.

    Par défaut, le VERROU est appliqué (voir nera/verrou.py) : rien de ce qui suit DATE_VERROU
    n'est lu. Seule la validation finale passe la phrase de confirmation pour tout lire.
    """
    df = pd.read_csv(chemin, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df = df.replace({"": None})
    for c in COLONNES_DATES:
        if c in df:
            df[c] = pd.to_datetime(df[c], format="%Y-%m-%d", errors="raise")
    for c in COLONNES_NOMBRES:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="raise")
    if "sortie_calculee" in df:
        df["sortie_calculee"] = df["sortie_calculee"].eq("1")
    if confirmation_coffre is None:
        return verrou.appliquer(df)
    verrou.ouvrir_coffre(confirmation_coffre)
    return df


def lire_lits(chemin: str | Path) -> pd.Series:
    """
    Fichier des capacités successives d'un service (lits ajoutés, fermés…), séparé par « ; » :
        date_debut;lits
        2024-07-01;20
        2025-03-15;24
    Chaque capacité s'applique de sa date de début jusqu'à la suivante.
    """
    t = pd.read_csv(chemin, sep=";", encoding="utf-8-sig")
    return pd.Series(t["lits"].astype(int).to_numpy(), index=pd.to_datetime(t["date_debut"], format="%Y-%m-%d")).sort_index()


@dataclass
class RapportSejours:
    """Ce que la préparation a gardé, écarté ou signalé — à reporter dans le mémoire."""
    total: int = 0
    par_statut: dict[str, int] = field(default_factory=dict)
    sorties_avant_entree: int = 0
    durees_aberrantes: int = 0
    fenetre_censure_jours: int | None = None
    partis_sans_duree: int = 0
    premiere_entree: pd.Timestamp | None = None
    derniere_entree: pd.Timestamp | None = None

    def __str__(self) -> str:
        lignes = [f"{self.total} séjour(s) du service",
                  *(f"  - {k} : {v}" for k, v in self.par_statut.items())]
        if self.sorties_avant_entree:
            lignes.append(f"  ! {self.sorties_avant_entree} séjour(s) avec sortie avant l'entrée (exclus)")
        if self.durees_aberrantes:
            lignes.append(f"  ! {self.durees_aberrantes} durée(s) aberrante(s) (plus de 90 nuits) traitée(s) comme absente(s)")
        if self.premiere_entree is not None:
            lignes.append(f"Admissions du {self.premiere_entree:%d/%m/%Y} au {self.derniere_entree:%d/%m/%Y}")
        return "\n".join(lignes)


# Poids a priori (en « lignes fictives ») qui rapproche la part inclusive d'un mois de la part globale.
PSEUDO_LIGNES = 10


def convention_nombre_de_jours(df: pd.DataFrame, service: str, pseudo_lignes: int = PSEUDO_LIGNES) -> dict:
    r"""
    Comment le registre compte-t-il les jours ? Mesure sur les lignes qui ont À LA FOIS une sortie
    écrite et un nombre de jours :
        écart = (sortie − entrée) − nombre de jours
        écart = 0  → la ligne compte les nuits ;   écart = −1 → la ligne est inclusive.
    Les autres écarts sont des erreurs d'écriture : dénombrés à part, ignorés pour p.

    Part inclusive globale :   p̂ = k / (k + m)      (k lignes inclusives, m lignes « nuits »)
    Sans aucune ligne mesurable, p̂ = 0,5 : ignorance complète, les deux conventions à égalité.

    Part inclusive du mois d'admission M (la pratique change avec les médecins) :
        p_M = (k_M + a·p̂) / (k_M + m_M + a)
    C'est la moyenne a posteriori d'une loi Bêta de moyenne p̂ et de « taille » a (pseudo_lignes),
    mise à jour par les k_M + m_M lignes du mois : un mois avec peu de lignes reste proche de p̂,
    un mois bien renseigné suit ses propres lignes. Un mois sans ligne mesurable reçoit p̂.
    """
    if "duree_jours" not in df:                              # registre sans nombre de jours
        df = df.assign(duree_jours=float("nan"))
    s = df[(df["service_code"] == service) & df["date_sortie"].notna() & df["duree_jours"].notna()]
    if "sortie_calculee" in s:
        s = s[~s["sortie_calculee"].fillna(False)]          # seulement les sorties réellement écrites
    ecart = ((s["date_sortie"] - s["date_entree"]).dt.days - s["duree_jours"]).astype(int)
    incl, nuits = ecart == -1, ecart == 0
    k, m = int(incl.sum()), int(nuits.sum())
    p_global = k / (k + m) if k + m else None
    p0 = p_global if p_global is not None else 0.5
    mois = s["date_entree"].dt.to_period("M")
    k_mois = incl.groupby(mois).sum()
    n_mois = (incl | nuits).groupby(mois).sum()
    par_mois = ((k_mois + pseudo_lignes * p0) / (n_mois + pseudo_lignes)).sort_index()
    if p_global is None:
        conclusion = ("aucune ligne mesurable (sortie écrite + nombre de jours) : part inclusive prise à 50 % ; "
                      "la fourchette « tout inclusif » – « tout en nuits » reste valable")
    else:
        conclusion = (f"{round(100 * p_global, 1)} % des {k + m} lignes mesurables sont inclusives : chaque sortie "
                      "calculée est pondérée par cette part (occupation attendue), entre « tout inclusif » "
                      "(borne basse) et « tout en nuits » (borne haute)")
    return {"lignes": len(s), "inclusives": k, "nuits": m, "autres_ecarts": len(s) - k - m,
            "part_inclusive_%": None if p_global is None else round(100 * p_global, 1),
            "p_global": p0, "par_mois": par_mois,
            "repartition_des_ecarts": ecart.value_counts().sort_index().to_dict(), "conclusion": conclusion}


def preparer_sejours(df: pd.DataFrame, service: str, date_extraction: str | pd.Timestamp,
                     fenetre_censure_jours: int | str = 30, inconnues: str = "exclure",
                     max_nuits: int = 90) -> tuple[pd.DataFrame, RapportSejours]:
    """
    Sélectionne les séjours d'un service et donne à chacun un statut de sortie.

    date_extraction : jour où le registre a été relevé (photographié) — fin de l'observation.
    fenetre_censure_jours : un séjour sans sortie n'est considéré « encore hospitalisé »
        (censuré) que si l'admission date de moins de ce nombre de jours avant l'extraction.
        Au-delà, sa sortie est « inconnue » : on ne suppose pas qu'il est resté des mois.
        'p95' : le 95e centile des durées connues (au moins 7 jours), adapté aux séjours courts.
    inconnues : 'exclure' (défaut), 'mediane' ou 'estimee' (prix, puis issue) : voir nera.imputation.
        Les séjours estimés reçoivent le statut « imputee » et les colonnes sortie_estimee, nuits_source.
    max_nuits : une durée plus longue est une erreur d'écriture (prix recopié dans « nombre de jours »,
        année fausse…) : la sortie est alors traitée comme absente, et le séjour compté dans le rapport.

    Renvoie les séjours (colonnes entree, sortie, sortie_basse, p_inclusif, statut, issue,
    duree_nuits…) et un rapport. `sortie` et `duree_nuits` suivent l'export : pour une sortie
    calculée, c'est la borne haute e + n. Le scénario de comptage est choisi dans nera.occupation.
    """
    extraction = pd.Timestamp(date_extraction).normalize()
    s = df[df["service_code"] == service].copy()
    rapport = RapportSejours(total=len(s))

    s["entree"] = s["date_entree"]
    s["sortie"] = s["date_sortie"]
    incoherents = s["sortie"].notna() & (s["sortie"] < s["entree"])
    rapport.sorties_avant_entree = int(incoherents.sum())
    s = s[~incoherents]
    aberrantes = (s["sortie"] - s["entree"]).dt.days > max_nuits
    rapport.durees_aberrantes = int(aberrantes.sum())
    s.loc[aberrantes, "sortie"] = pd.NaT

    sans_sortie = s["sortie"].isna()
    if fenetre_censure_jours == "p95":
        connues = (s.loc[~sans_sortie, "sortie"] - s.loc[~sans_sortie, "entree"]).dt.days
        fenetre_censure_jours = max(7, int(connues.quantile(0.95))) if len(connues) else 30
    recente = s["entree"] >= extraction - pd.Timedelta(days=fenetre_censure_jours)
    s["statut"] = "observee"
    if "sortie_calculee" in s:
        s.loc[s["sortie_calculee"].fillna(False) & ~sans_sortie, "statut"] = "calculee"
    # Un départ écrit (sortie, SCAM, décès, transfert, évasion) exclut « encore hospitalisé » : sans date,
    # la durée est inconnue (puis estimée si demandé), même pour une admission récente.
    parti = s["issue"].notna() & (s["issue"].astype(str).str.strip() != "") if "issue" in s else pd.Series(False, index=s.index)
    s.loc[sans_sortie & recente & ~parti, "statut"] = "censuree"
    s.loc[sans_sortie & (~recente | parti), "statut"] = "inconnue"
    rapport.partis_sans_duree = int((sans_sortie & parti).sum())

    # Sortie calculée : deux sorties possibles. Borne haute (nuits) = e + n, telle qu'exportée ;
    # borne basse (inclusif) = e + n − 1, jamais avant l'entrée. Autres séjours : une seule sortie.
    calc = s["statut"] == "calculee"
    s["sortie_basse"] = s["sortie"]
    veille = s.loc[calc, "sortie"] - pd.Timedelta(days=1)
    s.loc[calc, "sortie_basse"] = veille.where(veille >= s.loc[calc, "entree"], s.loc[calc, "entree"])
    conv = convention_nombre_de_jours(df, service)
    p_mois = s["entree"].dt.to_period("M").map(conv["par_mois"])
    s["p_inclusif"] = pd.to_numeric(p_mois, errors="coerce").fillna(conv["p_global"]).astype(float)
    s.loc[~calc, "p_inclusif"] = 0.0          # sans objet : la sortie est écrite, ou absente

    # Durée observée en nuits : jusqu'à la sortie, ou jusqu'à l'extraction si censuré.
    fin = s["sortie"].where(~sans_sortie, extraction)
    s["duree_nuits"] = (fin - s["entree"]).dt.days
    s.loc[s["statut"] == "inconnue", "duree_nuits"] = pd.NA

    # Durées inconnues estimées (nera.imputation) : la médiane de la classe donne la sortie attendue,
    # q1 et q3 les bornes (sortie_basse, sortie) utilisées par les scénarios « basse » et « haute ».
    s["sortie_estimee"] = pd.NaT
    s["nuits_source"] = None
    inc = s["statut"] == "inconnue"
    if inconnues != "exclure" and inc.any():
        connus = s[s["statut"].isin(["observee", "calculee"])]
        est = imputation.estimer(s[inc], imputation.tables_durees(connus), inconnues)
        jours = lambda col: pd.to_timedelta(est[col], unit="D")
        s.loc[inc, "sortie_estimee"] = s.loc[inc, "entree"] + jours("nuits")
        s.loc[inc, "sortie_basse"] = s.loc[inc, "entree"] + jours("nuits_q1")
        s.loc[inc, "sortie"] = s.loc[inc, "entree"] + jours("nuits_q3")
        s.loc[inc, "duree_nuits"] = est["nuits"]
        s.loc[inc, "nuits_source"] = est["source"]
        s.loc[inc, "statut"] = "imputee"

    rapport.par_statut = s["statut"].value_counts().reindex(
        ["observee", "calculee", "censuree", *(["imputee"] if inconnues != "exclure" else []), "inconnue"],
        fill_value=0).to_dict()
    rapport.fenetre_censure_jours = int(fenetre_censure_jours)
    if len(s):
        rapport.premiere_entree, rapport.derniere_entree = s["entree"].min(), s["entree"].max()
    return s.reset_index(drop=True), rapport


def periode_exploitable(sejours: pd.DataFrame, seuil: float = 0.9, rodage_jours: int | None = None,
                        rodage_au_debut: bool = False) -> dict:
    """
    Début de la période où l'occupation peut être reconstituée sans biais.

    Certains services n'ont commencé à écrire la durée d'hospitalisation qu'en cours de route :
    avant, ni sortie ni nombre de jours → durée inconnue → l'occupation serait sous-comptée.

    1. Pour chaque mois d'admission, part des séjours dont la durée est connue ou censurée
       (statut ≠ « inconnue »).
    2. Premier mois à partir duquel CHAQUE mois atteint `seuil` (90 %) : le registre est
       désormais complet.
    3. On y ajoute un rodage : les enfants admis juste avant ce mois, à durée inconnue, sont
       peut-être encore là au début. On attend qu'ils soient partis : par défaut le 95e centile
       des durées connues (au moins 14 jours).
    Les mois antérieurs restent utiles pour d'autres analyses (nombre d'admissions, diagnostics).

    Saisie commencée en cours de route (`rodage_au_debut=True`) : quand on n'a saisi qu'une
    fenêtre (par exemple mai → octobre 2026 pour un service de transfert), les enfants admis
    AVANT le premier jour saisi sont absents des données mais présents dans le service. Si le
    premier mois est complet, le rodage s'applique quand même : on n'utilise l'occupation qu'une
    fois ces enfants probablement sortis. Par défaut (False), le premier mois des données est
    supposé être le début réel du registre — comportement identique à l'application NERA.
    """
    mois = sejours["entree"].dt.to_period("M")
    part = (sejours["statut"] != "inconnue").groupby(mois).mean().sort_index()
    ok = part >= seuil
    debut_mois = None
    for i in range(len(part)):
        if ok.iloc[i:].all():
            debut_mois = part.index[i]
            break
    if debut_mois is None:
        raise ValueError("Aucune période où la durée de séjour est renseignée de façon complète.")
    if rodage_jours is None:
        connues = sejours.loc[sejours["statut"].isin(["observee", "calculee"]), "duree_nuits"].dropna()
        rodage_jours = max(14, int(connues.quantile(0.95))) if len(connues) else 30
    # Rien d'inconnu avant le tout premier mois… sauf si la saisie a commencé en cours de route.
    rodage = 0 if debut_mois == part.index[0] and not rodage_au_debut else rodage_jours
    # Point de départ du rodage : début du premier mois complet, mais jamais avant le premier jour
    # d'ENREGISTREMENT (comme l'outil de saisie) : quelques enfants entrés les jours précédents
    # (29-30 juin, inscrits le 1er juillet) ne doivent pas avancer le début du registre.
    base = debut_mois.to_timestamp()
    if "date_enregistrement" in sejours and sejours["date_enregistrement"].notna().any():
        base = max(base, pd.Timestamp(sejours["date_enregistrement"].min()).normalize())
    debut = base + pd.Timedelta(days=rodage)
    return {"debut": debut, "premier_mois_complet": str(debut_mois), "rodage_jours": rodage,
            "part_duree_connue_par_mois": (part * 100).round(1)}
