r"""
Jours fériés au Cameroun, calculés à la main (aucune bibliothèque de calendrier).

Pourquoi : un jour férié change le fonctionnement d'un service (moins de sorties signées, moins
d'admissions programmées, personnel réduit). Ces jours sont CONNUS À L'AVANCE : on peut donc
utiliser « le jour cible est férié » comme variable d'entrée sans fuite d'information.

Trois sortes de fêtes :
  1. À date fixe : 1er janvier, 11 février (fête de la Jeunesse), 1er mai, 20 mai (fête
     nationale), 15 août (Assomption), 25 décembre.
  2. Liées à Pâques (calendrier grégorien) : Vendredi saint (Pâques − 2 j), Ascension (Pâques + 39 j).
  3. Musulmanes (Aïd el-Fitr, Aïd el-Kébir…) : elles suivent le calendrier lunaire et sont fixées
     chaque année par annonce officielle. On ne les invente pas : elles se donnent dans un fichier
     (donnees/feries_supplementaires.csv, une colonne « date » au format aaaa-mm-jj).

Date de Pâques — algorithme « anonyme grégorien » (Meeus/Jones/Butcher, 1876), exact pour
toute année du calendrier grégorien. Pour une année Y (toutes les divisions sont entières) :
    a = Y mod 19                       (position dans le cycle lunaire de Méton, 19 ans)
    b = Y div 100,   c = Y mod 100     (siècle, année dans le siècle)
    d = b div 4,     e = b mod 4       (corrections des années bissextiles séculaires)
    f = (b + 8) div 25,  g = (b − f + 1) div 3      (correction lunaire)
    h = (19a + b − d − g + 15) mod 30  (âge de la lune : épacte)
    i = c div 4,     k = c mod 4
    l = (32 + 2e + 2i − h − k) mod 7   (jour de la semaine : on avance au dimanche)
    m = (a + 11h + 22l) div 451        (correction des cas limites)
    mois = (h + l − 7m + 114) div 31,  jour = ((h + l − 7m + 114) mod 31) + 1
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

FIXES = [(1, 1), (2, 11), (5, 1), (5, 20), (8, 15), (12, 25)]     # (mois, jour)


def paques(annee: int) -> date:
    """Dimanche de Pâques de l'année (calendrier grégorien), par l'algorithme de Meeus/Butcher."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(annee, mois, jour + 1)


def feries(annees, supplementaires: str | Path | None = None) -> set[date]:
    """Ensemble des jours fériés des années demandées (+ ceux du fichier, s'il existe)."""
    jours = set()
    for an in annees:
        jours |= {date(an, m, j) for m, j in FIXES}
        p = paques(an)
        jours |= {p - timedelta(days=2), p + timedelta(days=39)}   # Vendredi saint, Ascension
    if supplementaires is not None and Path(supplementaires).exists():
        autres = pd.read_csv(supplementaires, sep=";", encoding="utf-8-sig")
        jours |= {d.date() for d in pd.to_datetime(autres["date"], format="%Y-%m-%d")}
    return jours


def vacances(fichier: str | Path) -> set[date]:
    """
    Jours de vacances scolaires (bornes comprises), lus dans donnees/vacances_scolaires.csv
    (colonnes « debut » et « fin », aaaa-mm-jj, d'après les arrêtés MINEDUB/MINESEC).
    En pédiatrie, les vacances changent le rythme des familles (voyages, soins reportés) : comme
    les fériés, elles sont connues à l'avance, donc utilisables sans fuite d'information.
    Fichier absent : ensemble vide.
    """
    if not Path(fichier).exists():
        return set()
    periodes = pd.read_csv(fichier, sep=";", encoding="utf-8-sig")
    jours = set()
    for debut, fin in zip(pd.to_datetime(periodes["debut"], format="%Y-%m-%d"),
                          pd.to_datetime(periodes["fin"], format="%Y-%m-%d")):
        if fin < debut:
            raise ValueError(f"Période de vacances inversée : {debut:%Y-%m-%d} → {fin:%Y-%m-%d}")
        jours |= {d.date() for d in pd.date_range(debut, fin, freq="D")}
    return jours
