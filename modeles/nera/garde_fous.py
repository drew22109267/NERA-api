"""
Garde-fous de théorie des files d'attente (protocole, étapes 3.3 et 4.2).

Ils ne prédisent rien et ne reconstituent rien : ils VÉRIFIENT, indépendamment de tout
modèle appris, que les données (puis les prévisions) respectent les lois de base d'un
service hospitalier.

1. Loi de Little :  L = λ × W
     L : nombre moyen d'enfants présents (mesuré par le comptage jour par jour)
     λ : nombre moyen d'admissions par jour
     W : durée moyenne de séjour (en nuits)
   Si L ≠ λW de façon nette, les données ont un problème (page manquante, dates fausses,
   sorties non saisies) — ou la période est trop courte / non stationnaire.

2. Erlang B (système M/M/c/c, modèle « à perte ») :
     a = λ × W  la charge offerte (en lits),  c  le nombre de lits.
     B(c, a) = probabilité qu'un enfant arrive alors que tous les lits sont pris.
   Récurrence stable :  B(0) = 1,  B(k) = a·B(k−1) / (k + a·B(k−1)).
   Erlang B suppose qu'un patient refusé est perdu. Dans un service qui ajoute des lits en cas
   de besoin, la saturation observée peut dépasser B : l'écart mesure alors le débordement.
"""
from __future__ import annotations

import pandas as pd

from .occupation import sorties_possibles


def erlang_b(c: int, a: float) -> float:
    """Probabilité de blocage d'un système à c lits soumis à une charge a (en lits)."""
    if c < 0 or a < 0:
        raise ValueError("c et a doivent être positifs.")
    b = 1.0
    for k in range(1, c + 1):
        b = a * b / (k + a * b)
    return b


def verifier_little(occ: pd.DataFrame, sejours: pd.DataFrame, marge_bord_jours: int = 30,
                    scenario: str = "attendue", comptage: str = "minuit") -> dict:
    """
    Compare L (mesuré) à λW (calculé séparément), sur la période intérieure de la série.

    On retire `marge_bord_jours` au début et à la fin : au bord, des séjours commencés avant
    ou finis après la fenêtre faussent la comparaison (effet de bord).
    W est la durée moyenne des séjours admis dans la fenêtre et dont la sortie est connue,
    pondérée comme l'occupation (`scenario` doit être celui de `occ`, voir nera.occupation).
    """
    debut = occ.index.min() + pd.Timedelta(days=marge_bord_jours)
    fin = occ.index.max() - pd.Timedelta(days=marge_bord_jours)
    if fin <= debut:
        raise ValueError("Série trop courte pour appliquer la loi de Little hors effets de bord.")
    fenetre = occ.loc[debut:fin]
    L = fenetre["presents"].mean()
    lam = fenetre["admissions"].mean()
    admis = sejours[(sejours["entree"] >= debut) & (sejours["entree"] <= fin)
                    & sejours["statut"].isin(["observee", "calculee"])]
    ev = sorties_possibles(admis, occ.index.max() + pd.Timedelta(days=1), scenario)
    W = float((ev["poids"] * ev["duree_nuits"]).sum() / ev["poids"].sum()) if len(ev) else float("nan")
    W += 1.0 if comptage == "journee" else 0.0       # comptage journalier : un jour de présence de plus par séjour
    lw = lam * W
    ecart = (L - lw) / lw * 100 if lw else float("nan")
    return {
        "periode": f"{debut:%d/%m/%Y} → {fin:%d/%m/%Y}",
        "L_mesure": round(L, 2), "lambda_par_jour": round(lam, 3), "W_nuits": round(W, 2),
        "lambda_x_W": round(lw, 2), "ecart_pourcent": round(ecart, 1),
        "sejours_utilises_pour_W": len(admis),
        "verdict": "cohérent" if abs(ecart) <= 10 else "à examiner (écart > 10 %)",
    }


def comparer_erlang(occ: pd.DataFrame, lits: int, little: dict) -> dict:
    """Saturation prévue par Erlang B (charge a = λW) contre saturation observée."""
    a = little["lambda_x_W"]
    observe = (occ["presents"] >= lits).mean()
    return {
        "charge_offerte_a": round(a, 2), "lits": lits,
        "blocage_erlang_b_pourcent": round(erlang_b(lits, a) * 100, 2),
        "jours_satures_observes_pourcent": round(observe * 100, 2),
    }
