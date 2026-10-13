r"""
Reconstitution de l'occupation journalière d'un service (protocole, étape 2.3).

Convention de comptage — le « recensement de minuit » :
    un enfant compte dans l'occupation du jour d si   entree ≤ d < sortie.
Il occupe donc un lit la nuit de son admission, mais plus la nuit de sa sortie.
Un séjour de 3 nuits (entrée le 1er, sortie le 4) compte les 1er, 2 et 3.
Un enfant entré et sorti le même jour (0 nuit) n'apparaît pas dans l'occupation de minuit,
mais il est compté dans les admissions du jour.

Les séjours censurés (encore hospitalisés) comptent jusqu'à la date d'extraction.
Les séjours à sortie inconnue sont exclus, sauf si l'on choisit de les estimer (nera.imputation :
statut « imputee ») ; leur part parmi les présents est donnée chaque jour (dont_estimes).

L'occupation n'est PAS plafonnée au nombre de lits : un dépassement est un sureffectif
réel (lits ajoutés, deux enfants par lit…), et c'est une information à garder.

Sorties calculées et convention du nombre de jours — trois scénarios
--------------------------------------------------------------------
Quand la sortie n'est pas écrite, elle vaut  S = e + n − 1  (ligne inclusive, probabilité p)
ou  S = e + n  (ligne en nuits, probabilité 1 − p) ; p = p_inclusif du séjour (nera.chargement).
Les deux sorties ne diffèrent que d'une nuit, celle du jour  d* = e + n − 1 :

    P(e ≤ d < S) = 1        pour e ≤ d < d*
                 = 1 − p    pour d = d*
                 = 0        pour d > d*

  « attendue » : E[présents_d] = Σ_i P(e_i ≤ d < S_i)  — linéarité de l'espérance, aucune
                 hypothèse d'indépendance entre séjours. La nuit incertaine compte pour 1 − p.
  « basse »    : tous les séjours inclusifs (p = 1).
  « haute »    : tous les séjours en nuits (p = 0).

Comme présents_d est croissant en chaque S_i, toute répartition réelle des deux conventions
donne une série comprise entre « basse » et « haute » : c'est un encadrement exact (si les deux
conventions sont les seules pratiquées), pas un intervalle de confiance. L'écart entre les bornes
vaut, chaque jour, le nombre de séjours calculés dont d est la nuit incertaine.

Les sorties sont pondérées de même : la sortie d'un séjour calculé compte pour p le jour e + n − 1
et pour 1 − p le jour e + n. Les indicateurs (nera.indicateurs) se calculent avec ces poids.
"""
from __future__ import annotations

import pandas as pd

from .chargement import ISSUES

SCENARIOS = ("attendue", "basse", "haute")


def _poids_inclusif(sejours: pd.DataFrame, scenario: str) -> pd.Series:
    if scenario not in SCENARIOS:
        raise ValueError(f"Scénario inconnu : {scenario} (attendus : {', '.join(SCENARIOS)}).")
    if scenario == "basse":
        return pd.Series(1.0, index=sejours.index)
    if scenario == "haute":
        return pd.Series(0.0, index=sejours.index)
    return sejours["p_inclusif"].astype(float)


def sorties_possibles(sejours: pd.DataFrame, date_extraction: str | pd.Timestamp,
                      scenario: str = "attendue") -> pd.DataFrame:
    """
    Un événement de fin par séjour exploitable — deux pour une sortie calculée ambiguë :
      sejour, entree, fin, poids (somme 1 par séjour), reelle (False : censuré, fin = extraction),
      issue, duree_nuits = fin − entree.
    """
    extraction = pd.Timestamp(date_extraction).normalize()
    s = sejours[sejours["statut"] != "inconnue"]
    w = _poids_inclusif(s, scenario)
    imputee = s["statut"] == "imputee"
    base = pd.DataFrame({"sejour": s.index, "entree": s["entree"],
                         "issue": s["issue"] if "issue" in s else None, "reelle": s["sortie"].notna() & ~imputee})
    haute = base.assign(fin=s["sortie"].fillna(extraction), poids=1.0)
    # Séjour à durée estimée (nera.imputation) : une seule fin, médiane de sa classe dans le scénario
    # « attendue », 1er quartile dans « basse », 3e quartile dans « haute ». Jamais une sortie « réelle ».
    if imputee.any():
        fin_estimee = {"attendue": s.loc[imputee, "sortie_estimee"], "basse": s.loc[imputee, "sortie_basse"],
                       "haute": s.loc[imputee, "sortie"]}[scenario]
        haute.loc[imputee.to_numpy(), "fin"] = fin_estimee.to_numpy()
    ambigu = (s["statut"] == "calculee") & (s["sortie_basse"] < s["sortie"])
    haute.loc[ambigu, "poids"] = 1.0 - w[ambigu]
    basse = base[ambigu].assign(fin=s.loc[ambigu, "sortie_basse"], poids=w[ambigu])
    ev = pd.concat([haute, basse], ignore_index=True)
    ev = ev[ev["poids"] > 0].copy()
    ev["duree_nuits"] = (ev["fin"] - ev["entree"]).dt.days
    return ev.sort_values(["sejour", "fin"]).reset_index(drop=True)


def lits_par_jour(lits, jours: pd.DatetimeIndex) -> pd.Series:
    """
    Nombre de lits de chaque jour. `lits` est soit un entier (capacité fixe), soit une série
    indexée par la date à partir de laquelle chaque capacité s'applique (fichier lits_<SERVICE>.csv :
    colonnes date_debut;lits). Chaque jour reçoit la dernière capacité en vigueur.
    """
    if isinstance(lits, pd.Series):
        serie = lits.sort_index()
        if serie.index.min() > jours.min():
            raise ValueError(f"Le fichier des lits commence le {serie.index.min():%d/%m/%Y}, après le début "
                             f"de la série ({jours.min():%d/%m/%Y}) : ajoutez une ligne plus ancienne.")
        return serie.reindex(serie.index.union(jours)).ffill().reindex(jours).astype(float)
    return pd.Series(float(lits), index=jours)


def reconstituer_occupation(sejours: pd.DataFrame, date_extraction: str | pd.Timestamp,
                            lits: int | pd.Series | None = None, debut: str | None = None,
                            scenario: str = "attendue") -> pd.DataFrame:
    """
    Une ligne par jour, de la première admission (ou `debut`) à la veille de l'extraction :
      presents          enfants hospitalisés à minuit (espérance pour le scénario « attendue »)
      dont_censures     parmi eux, ceux dont la sortie n'est pas encore connue
      admissions        entrées du jour
      sorties_*         sorties du jour, par issue (pondérées pour les sorties calculées)
      lits, taux_occupation, sureffectif   si le nombre de lits est fourni
    """
    extraction = pd.Timestamp(date_extraction).normalize()
    s = sejours[sejours["statut"] != "inconnue"]
    if s.empty:
        raise ValueError("Aucun séjour exploitable pour reconstituer l'occupation.")
    ev = sorties_possibles(sejours, extraction, scenario)

    premier = pd.Timestamp(debut) if debut else s["entree"].min()
    jours = pd.date_range(premier, extraction - pd.Timedelta(days=1), freq="D")

    # Tableau de différences : +1 le jour d'entrée, −poids le jour de chaque fin possible,
    # puis somme cumulée. Les séjours commencés avant `debut` sont reportés au premier jour.
    def cumul(entrees: pd.Series, fins: pd.DataFrame) -> pd.Series:
        delta = entrees.value_counts().astype(float).sub(fins.groupby("fin")["poids"].sum(), fill_value=0)
        avant = delta[delta.index < premier].sum()
        delta = delta[delta.index >= premier].reindex(jours, fill_value=0.0)
        delta.iloc[0] += avant
        return delta.cumsum().round(10)          # supprime les résidus d'arrondi (1e-16)

    occ = pd.DataFrame(index=jours)
    occ.index.name = "jour"
    occ["presents"] = cumul(s["entree"], ev)
    cens = s["statut"] == "censuree"
    occ["dont_censures"] = (cumul(s.loc[cens, "entree"], ev[ev["sejour"].isin(s.index[cens])]).astype(int)
                            if cens.any() else 0)
    # Parmi les présents, ceux dont la durée est estimée : mesure de la fiabilité de chaque jour,
    # utilisable par le modèle (variable, ou poids d'apprentissage plus faible quand la part est forte).
    imp = s["statut"] == "imputee"
    occ["dont_estimes"] = cumul(s.loc[imp, "entree"], ev[ev["sejour"].isin(s.index[imp])]) if imp.any() else 0.0
    occ["admissions"] = s["entree"].value_counts().reindex(jours, fill_value=0).astype(int)
    reelles = ev[ev["reelle"]]
    for issue in ISSUES:
        nom = "sorties_" + issue.lower().replace(" ", "_").replace("é", "e").replace("è", "e")
        occ[nom] = reelles[reelles["issue"] == issue].groupby("fin")["poids"].sum().reindex(jours, fill_value=0.0)
    occ["sorties_issue_inconnue"] = reelles[~reelles["issue"].isin(ISSUES)].groupby("fin")["poids"].sum() \
        .reindex(jours, fill_value=0.0)

    if lits is not None and (isinstance(lits, pd.Series) or lits):
        occ["lits"] = lits_par_jour(lits, jours)                  # capacité du jour (fixe ou par période)
        occ["taux_occupation"] = occ["presents"] / occ["lits"]
        occ["sureffectif"] = (occ["presents"] - occ["lits"]).clip(lower=0)
    return occ


def trois_scenarios(sejours: pd.DataFrame, date_extraction, lits: int | pd.Series | None = None,
                    debut: str | None = None) -> dict[str, pd.DataFrame]:
    """Les trois séries (attendue, basse, haute), sur les mêmes jours."""
    return {sc: reconstituer_occupation(sejours, date_extraction, lits, debut, sc) for sc in SCENARIOS}


def resume_occupation(occ: pd.DataFrame) -> dict:
    """Chiffres descriptifs de la série — directement utilisables dans le mémoire."""
    r = {
        "jours": len(occ),
        "occupation_moyenne": round(occ["presents"].mean(), 2),
        "occupation_max": round(float(occ["presents"].max()), 2),
        "jour_max": occ["presents"].idxmax().strftime("%d/%m/%Y"),
        "admissions_par_jour": round(occ["admissions"].mean(), 2),
    }
    if "lits" in occ:
        sat = occ["presents"] >= occ["lits"]
        r |= {
            "taux_occupation_moyen": round(occ["taux_occupation"].mean() * 100, 1),
            "jours_satures": int(sat.sum()),
            "jours_en_sureffectif": int((occ["sureffectif"] > 0).sum()),
            "sureffectif_max": round(float(occ["sureffectif"].max()), 2),
        }
    return r
