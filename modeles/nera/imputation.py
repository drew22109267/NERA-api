r"""
Durées de séjour manquantes : les exclure, ou les ESTIMER à partir de ce qui est écrit sur la ligne.

Le problème : certaines lignes n'ont ni date de sortie ni nombre de jours (octobre 2024 en pédiatrie :
près d'une ligne sur deux). Les exclure sous-estime l'occupation des mois concernés ; les garder
« encore hospitalisés » la surestime. Mais la ligne contient souvent d'autres traces de la durée :

  le PRIX payé      il suit la durée : en pédiatrie (juillet 2024 à mars 2025),
                    4 000 F → 1 nuit (MEO), 7 500 F → 3, 15 000 F → 5, 22 500 F → 8 à 9 (médianes) ;
  l'ISSUE           une mise en observation (MEO) dure 1 nuit, une sortie contre avis est plus courte ;
  les médicaments   leur nombre n'apporte presque rien (vérifié par validation croisée).

Méthodes (paramètre `inconnues` de nera.chargement.preparer_sejours) :
  'exclure'  la ligne n'entre pas dans l'occupation (comportement historique de NERA) ;
  'mediane'  durée médiane des séjours connus du service ;
  'estimee'  durée médiane des séjours connus AYANT LE MÊME PRIX (au moins `min_lignes` séjours) ;
             à défaut, même issue ; à défaut, médiane du service.
Rien n'est codé en dur : les tables sont recalculées sur les séjours connus de chaque service.

Incertitude : pour chaque séjour estimé on garde aussi le 1er et le 3e quartile de sa classe.
nera.occupation les utilise comme bornes (scénario « basse » : q1, « haute » : q3, « attendue » :
médiane) ; sensibilite.py propage donc cette incertitude jusqu'aux conclusions du modèle.
Les durées estimées n'entrent ni dans la DMS ni dans les sorties par issue (dates inventées).

Validation (valider_estimation) : validation croisée en k plis sur les séjours connus ; on cache la
durée, on la prédit, on mesure l'erreur absolue moyenne. Sur la pédiatrie : médiane 1,46 nuit
d'erreur, prix 1,13 nuit ; ±1 nuit dans 60 % des cas pour la médiane, 77 % pour le prix.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

METHODES = ("exclure", "mediane", "estimee")
MIN_LIGNES = 5


def _resume(d: pd.Series) -> tuple[float, float, float]:
    return float(d.median()), float(d.quantile(0.25)), float(d.quantile(0.75))


def tables_durees(connus: pd.DataFrame, min_lignes: int = MIN_LIGNES) -> dict:
    """
    `connus` : séjours de durée connue (colonnes duree_nuits, et si possible prix, issue).
    Renvoie {'global': (med, q1, q3), 'prix': {prix: (…)}, 'issue': {issue: (…)}} ; une classe
    n'est retenue que si elle compte au moins `min_lignes` séjours.
    """
    d = connus["duree_nuits"].astype(float)
    t = {"global": _resume(d) if len(d) else (np.nan,) * 3, "prix": {}, "issue": {}}
    for col in ("prix", "issue"):
        if col in connus:
            for k, g in d.groupby(connus[col]):
                if pd.notna(k) and len(g) >= min_lignes:
                    t[col][k] = _resume(g)
    return t


def estimer(lignes: pd.DataFrame, tables: dict, methode: str = "estimee") -> pd.DataFrame:
    """Pour chaque ligne : nuits (médiane de sa classe), nuits_q1, nuits_q3 et la source de l'estimation."""
    if methode not in METHODES[1:]:
        raise ValueError(f"Méthode d'estimation inconnue : {methode} (attendues : {', '.join(METHODES[1:])}).")
    res = []
    for _, l in lignes.iterrows():
        source, v = "mediane", tables["global"]
        if methode == "estimee":
            if "prix" in l and pd.notna(l["prix"]) and l["prix"] in tables["prix"]:
                source, v = "prix", tables["prix"][l["prix"]]
            elif "issue" in l and pd.notna(l["issue"]) and l["issue"] in tables["issue"]:
                source, v = "issue", tables["issue"][l["issue"]]
        res.append({"nuits": round(v[0]), "nuits_q1": int(np.floor(v[1])), "nuits_q3": int(np.ceil(v[2])), "source": source})
    return pd.DataFrame(res, index=lignes.index)


def valider_estimation(connus: pd.DataFrame, plis: int = 5, graine: int = 1, min_lignes: int = MIN_LIGNES) -> pd.DataFrame:
    """
    Validation croisée : chaque séjour connu est prédit par des tables construites SANS lui.
      erreur_moyenne_nuits   moyenne de |prédit − vrai|
      a_1_nuit_pres_%        part des séjours prédits à ±1 nuit
    Une ligne par méthode (mediane, estimee). À citer dans le mémoire pour justifier le choix.
    """
    connus = connus[connus["duree_nuits"].notna()]
    ordre = np.random.default_rng(graine).permutation(len(connus))
    erreurs = {m: [] for m in METHODES[1:]}
    for k in range(plis):
        test = connus.iloc[ordre[k::plis]]
        entrainement = connus.iloc[np.setdiff1d(ordre, ordre[k::plis])]
        tables = tables_durees(entrainement, min_lignes)
        for m in erreurs:
            erreurs[m].append((estimer(test, tables, m)["nuits"] - test["duree_nuits"].astype(float)).abs())
    lignes = []
    for m, e in erreurs.items():
        e = pd.concat(e)
        lignes.append({"methode": m, "sejours": len(e), "erreur_moyenne_nuits": round(float(e.mean()), 2),
                       "a_1_nuit_pres_%": round(100 * float((e <= 1).mean()), 1)})
    return pd.DataFrame(lignes).set_index("methode")
