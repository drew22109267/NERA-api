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

from dataclasses import dataclass

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


@dataclass(frozen=True)
class HeuresPresence:
    """
    Heures typiques (le registre n'en donne aucune), pour le comptage « pondere » : chaque enfant compte la
    fraction de chaque jour où il est réellement là.
      entree      heure moyenne d'admission (12 h : admissions réparties sur la journée)
      sortie      heure moyenne de sortie (11 h : sorties après la visite du matin)
      meme_jour   durée moyenne d'un séjour entré et sorti le même jour (MEO, SCAM précoce), en heures
    """
    entree: float = 12.0
    sortie: float = 11.0
    meme_jour: float = 8.0


def reconstituer_occupation(sejours: pd.DataFrame, date_extraction: str | pd.Timestamp,
                            lits: int | pd.Series | None = None, debut: str | None = None,
                            scenario: str = "attendue", comptage: str = "minuit",
                            heures: HeuresPresence = HeuresPresence()) -> pd.DataFrame:
    """
    Une ligne par jour, de la première admission (ou `debut`) à la veille de l'extraction :
      presents          enfants hospitalisés (espérance pour le scénario « attendue ») selon `comptage` :
                          « minuit »  : recensement de minuit, présent si entrée ≤ d < sortie (nuits passées) ;
                          « journee » : présent dans la journée, entrée ≤ d ≤ sortie (jour de sortie compris ;
                                        un enfant entré et sorti le même jour compte 1)
                          « pondere » : présence moyenne pondérée par le temps (fraction de chaque jour où
                                        l'enfant est là, avec les heures typiques `heures`) :
                                        jour d'entrée 1 − h_e/24, jours pleins 1, jour de sortie h_s/24,
                                        séjour du même jour durée/24
      pic_bas, pic_haut encadrement EXACT du plus grand nombre d'enfants présents en même temps dans la
                        journée d (sans hypothèse d'heure) : max(minuit de d − 1, minuit de d) ≤ pic ≤
                        comptage journalier de d
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
    if comptage not in ("minuit", "journee", "pondere"):
        raise ValueError("comptage : « minuit », « journee » ou « pondere ».")
    # Comptage journalier : chaque fin de séjour est décalée d'un jour pour la présence (pas pour les sorties).
    ev_presence = ev.assign(fin=ev["fin"] + pd.Timedelta(days=1)) if comptage in ("journee", "pondere") else ev
    ev_jour = ev.assign(fin=ev["fin"] + pd.Timedelta(days=1))

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
    occ["presents"] = cumul(s["entree"], ev_presence)
    if comptage == "pondere":
        # Comptage journalier, puis on retire la part du jour où l'enfant n'est pas encore arrivé (jour
        # d'entrée : h_e/24) ou déjà parti (jour de sortie : 1 − h_s/24) ; un séjour du même jour ne garde que
        # sa durée m : 1 − a − (1 − m − a) = m. Les sorties sont pondérées comme l'occupation (poids p, 1 − p).
        a, b, m = heures.entree / 24, heures.sortie / 24, heures.meme_jour / 24
        corr = s["entree"].value_counts().astype(float) * a
        reelles_ou_estimees = ev[ev["fin"] < extraction]
        meme = reelles_ou_estimees["fin"] == reelles_ou_estimees["entree"]
        part = reelles_ou_estimees["poids"] * (1 - b)
        part[meme] = reelles_ou_estimees.loc[meme, "poids"] * (1 - m - a)
        corr = corr.add(part.groupby(reelles_ou_estimees["fin"]).sum(), fill_value=0.0)
        occ["presents"] = (occ["presents"] - corr.reindex(jours, fill_value=0.0)).round(10)
    # Encadrement exact du pic de la journée (indépendant de la méthode choisie).
    minuit = cumul(s["entree"], ev)
    occ["pic_bas"] = pd.concat([minuit, minuit.shift(1)], axis=1).max(axis=1)
    occ["pic_haut"] = cumul(s["entree"], ev_jour)
    cens = s["statut"] == "censuree"
    occ["dont_censures"] = (cumul(s.loc[cens, "entree"], ev_presence[ev_presence["sejour"].isin(s.index[cens])]).astype(int)
                            if cens.any() else 0)
    # Parmi les présents, ceux dont la durée est estimée : mesure de la fiabilité de chaque jour,
    # utilisable par le modèle (variable, ou poids d'apprentissage plus faible quand la part est forte).
    imp = s["statut"] == "imputee"
    occ["dont_estimes"] = cumul(s.loc[imp, "entree"], ev_presence[ev_presence["sejour"].isin(s.index[imp])]) if imp.any() else 0.0
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
                    debut: str | None = None, comptage: str = "minuit",
                    heures: HeuresPresence = HeuresPresence()) -> dict[str, pd.DataFrame]:
    """Les trois séries (attendue, basse, haute), sur les mêmes jours."""
    return {sc: reconstituer_occupation(sejours, date_extraction, lits, debut, sc, comptage, heures) for sc in SCENARIOS}


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
