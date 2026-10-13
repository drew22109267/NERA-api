"""Calendrier camerounais : mêmes dates dans la chaîne Python et dans l'outil de saisie (calendrier.js)."""
import re
from datetime import date
from pathlib import Path

import pandas as pd

from svr.calendrier import feries, vacances
from svr.caracteristiques import construire

RACINE = Path(__file__).resolve().parents[1]
JS = (RACINE / "outil-saisie" / "calendrier.js").read_text(encoding="utf-8")


def _bloc(nom: str) -> str:
    return re.search(rf"const {nom} = \[(.*?)\n  \]", JS, re.S).group(1)


def test_feries_identiques_dans_l_outil():
    csv = pd.read_csv(RACINE / "donnees" / "feries_supplementaires.csv", sep=";", encoding="utf-8-sig")
    assert re.findall(r"\['(\d{4}-\d\d-\d\d)'", _bloc("FERIES_ANNONCES")) == list(csv["date"])


def test_vacances_identiques_dans_l_outil():
    csv = pd.read_csv(RACINE / "donnees" / "vacances_scolaires.csv", sep=";", encoding="utf-8-sig")
    js = re.findall(r"\['(\d{4}-\d\d-\d\d)', '(\d{4}-\d\d-\d\d)'", _bloc("VACANCES"))
    assert js == list(zip(csv["debut"], csv["fin"]))


def test_feries_annonces_et_vacances():
    f = feries([2024, 2025], RACINE / "donnees" / "feries_supplementaires.csv")
    assert {date(2024, 4, 10), date(2024, 6, 17), date(2025, 3, 31), date(2025, 6, 6)} <= f
    v = vacances(RACINE / "donnees" / "vacances_scolaires.csv")
    assert date(2024, 12, 25) in v and date(2025, 4, 21) in v and date(2025, 4, 22) not in v
    assert date(2025, 10, 1) not in v and vacances(RACINE / "absent.csv") == set()


def test_variable_vacances_dans_le_tableau():
    jours = pd.date_range("2024-12-01", periods=40, freq="D")
    occ = pd.DataFrame({"presents": range(40), "admissions": 1, "sorties_sortie": 1}, index=jours)
    t = construire(occ, 1, vacances={date(2024, 12, 25)})
    i = list(t.dates_cible).index(pd.Timestamp("2024-12-25"))
    col = t.noms.index("cible_vacances")
    assert t.X[i, col] == 1 and t.X[:, col].sum() == 1 and col not in t.continues
