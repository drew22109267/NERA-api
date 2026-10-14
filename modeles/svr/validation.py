"""
Découpages temporels et validation glissante (protocole, étape 3.5).

Règle d'or : on n'entraîne jamais sur une information que l'on n'aurait pas eue le jour de la
prévision. Une ligne (origine t, cible t + h) n'est utilisable pour entraîner un modèle à
l'origine O que si sa cible est déjà connue :  t + h ≤ O.

1. Test final (une seule fois, à la toute fin)
   Entraînement : lignes dont la cible est antérieure au début du test.
   Test        : lignes dont l'origine est dans la période de test.
   Les lignes à cheval (origine avant le test, cible dedans) sont écartées.

2. Validation glissante « rolling origin » (pour choisir modèles et hyperparamètres)
   Sur la période d'entraînement, on avance l'origine O par pas de `pas` jours :
      à chaque O : entraînement sur toutes les lignes de cible ≤ O (fenêtre qui s'agrandit),
                   validation sur les lignes d'origine dans [O, O + pas[.
   On simule ainsi ce que le modèle aurait fait, semaine après semaine, en conditions réelles.
   La standardisation est réapprise à chaque pas, sur l'entraînement du pas.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import torch

from .caracteristiques import Standardiseur, Tableau


@dataclass
class Decoupage:
    entrainement: torch.Tensor      # indices des lignes du tableau
    evaluation: torch.Tensor
    origine: pd.Timestamp


def decoupage_final(tab: Tableau, debut_test: str | pd.Timestamp) -> Decoupage:
    d = pd.Timestamp(debut_test)
    entr = torch.nonzero(torch.tensor(tab.dates_cible < d)).flatten()
    test = torch.nonzero(torch.tensor(tab.dates_origine >= d)).flatten()
    if len(entr) == 0 or len(test) == 0:
        raise ValueError("Découpage vide : vérifiez la date de début du test.")
    return Decoupage(entr, test, d)


def decoupages_test_mensuels(tab: Tableau, debut_test: str | pd.Timestamp) -> list[Decoupage]:
    """
    Test final découpé en blocs d'un mois, avec réentraînement au début de chaque mois.

    Bloc m (origines du mois m) : entraînement sur toutes les lignes dont la cible précède le 1er du
    mois m, donc y compris les mois de test déjà écoulés ; c'est ce qui se passerait en service avec
    un réentraînement mensuel. Le premier bloc est identique à decoupage_final (rien du test n'est
    connu) ; les suivants montrent si réentraîner chaque mois améliore la prévision.
    """
    d = pd.Timestamp(debut_test).normalize().replace(day=1)
    fin = pd.Timestamp(tab.dates_origine.max())
    decoupages = []
    while d <= fin:
        suivant = d + pd.DateOffset(months=1)
        entr = torch.nonzero(torch.tensor(tab.dates_cible < d)).flatten()
        ev = torch.nonzero(torch.tensor((tab.dates_origine >= d) & (tab.dates_origine < suivant))).flatten()
        if len(entr) and len(ev):
            decoupages.append(Decoupage(entr, ev, d))
        d = suivant
    if not decoupages:
        raise ValueError("Découpage vide : vérifiez la date de début du test.")
    return decoupages


def origines_glissantes(tab: Tableau, debut: str | pd.Timestamp, fin: str | pd.Timestamp,
                        pas: int = 14, minimum_entrainement: int = 60) -> list[Decoupage]:
    """Découpages successifs entre `debut` et `fin` (fin exclue : typiquement le début du test)."""
    decoupages, O, fin = [], pd.Timestamp(debut), pd.Timestamp(fin)
    while O < fin:
        fin_pas = min(O + pd.Timedelta(days=pas), fin)
        entr = torch.nonzero(torch.tensor(tab.dates_cible <= O)).flatten()
        ev = torch.nonzero(torch.tensor((tab.dates_origine >= O) & (tab.dates_origine < fin_pas))).flatten()
        if len(entr) >= minimum_entrainement and len(ev):
            decoupages.append(Decoupage(entr, ev, O))
        O = fin_pas
    if not decoupages:
        raise ValueError("Aucun découpage glissant possible : période trop courte.")
    return decoupages


def evaluer(tab: Tableau, decoupages: list[Decoupage], fabrique) -> dict:
    """
    Pour chaque découpage : standardise, entraîne `fabrique()` sur l'entraînement, prédit l'évaluation.
    Le modèle renvoie soit un tenseur (prévision ponctuelle), soit un dict {τ: tenseur} (quantiles).
    Renvoie les prévisions concaténées, alignées sur les vraies valeurs et les dates.
    """
    y_vrai, prev, dates, origines = [], [], [], []
    for dec in decoupages:
        std = Standardiseur(tab.continues).ajuster(tab.X[dec.entrainement])
        modele = fabrique().entrainer(std.transformer(tab.X[dec.entrainement]), tab.y[dec.entrainement])
        prev.append(modele.predire(std.transformer(tab.X[dec.evaluation])))
        y_vrai.append(tab.y[dec.evaluation])
        dates.extend(tab.dates_cible[dec.evaluation.numpy()])
        origines.append(tab.origines[dec.evaluation])
    if isinstance(prev[0], dict):
        prev = {tau: torch.cat([p[tau] for p in prev]) for tau in prev[0]}
    else:
        prev = torch.cat(prev)
    return {"y": torch.cat(y_vrai), "prevision": prev, "dates": pd.DatetimeIndex(dates),
            "origines": torch.cat(origines)}
