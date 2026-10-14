"""
Tests de la chaîne de données sur de petits cas calculés à la main.
Ces quelques séjours ne servent qu'à vérifier le code : ce ne sont pas des données de l'étude.

Lancer :  ~/memoire-env/bin/python -m pytest tests -q
"""
import pandas as pd
import pytest

from nera.chargement import preparer_sejours
from nera.garde_fous import erlang_b, verifier_little
from nera.occupation import reconstituer_occupation, resume_occupation, sorties_possibles


def table(lignes):
    df = pd.DataFrame(lignes, columns=["service_code", "date_entree", "date_sortie", "issue", "sortie_calculee"])
    df["date_entree"] = pd.to_datetime(df["date_entree"])
    df["date_sortie"] = pd.to_datetime(df["date_sortie"])
    return df


def test_recensement_de_minuit():
    # A : 3 nuits (1er → 4), B : 0 nuit (entre et sort le 2), C : encore là à l'extraction (6).
    df = table([("PED", "2026-01-01", "2026-01-04", "Sortie", False),
                ("PED", "2026-01-02", "2026-01-02", "Sortie", False),
                ("PED", "2026-01-03", None, None, False)])
    s, rapport = preparer_sejours(df, "PED", "2026-01-06")
    assert rapport.par_statut == {"observee": 2, "calculee": 0, "censuree": 1, "inconnue": 0}
    occ = reconstituer_occupation(s, "2026-01-06", lits=1)
    assert occ["presents"].tolist() == [1, 1, 2, 1, 1]          # du 1er au 5
    assert occ["admissions"].tolist() == [1, 1, 1, 0, 0]
    assert occ["dont_censures"].tolist() == [0, 0, 1, 1, 1]
    assert occ["sorties_sortie"].tolist() == [0, 1, 0, 1, 0]
    assert occ["sureffectif"].max() == 1                         # 2 enfants pour 1 lit le 3


def test_comptage_journalier_jour_de_sortie_compris():
    # Mêmes séjours que ci-dessus, comptés chaque jour de présence (entrée ≤ d ≤ sortie) :
    # A compte du 1er au 4 (4 jours), B compte le 2 (1 jour), C du 3 au 5.
    df = table([("PED", "2026-01-01", "2026-01-04", "Sortie", False),
                ("PED", "2026-01-02", "2026-01-02", "Sortie", False),
                ("PED", "2026-01-03", None, None, False)])
    s, _ = preparer_sejours(df, "PED", "2026-01-06")
    minuit = reconstituer_occupation(s, "2026-01-06", lits=1)
    jour = reconstituer_occupation(s, "2026-01-06", lits=1, comptage="journee")
    assert jour["presents"].tolist() == [1, 2, 2, 2, 1]
    assert jour["sorties_sortie"].tolist() == minuit["sorties_sortie"].tolist()     # les sorties ne bougent pas
    assert jour["admissions"].tolist() == minuit["admissions"].tolist()
    # Chaque séjour terminé dans la fenêtre ajoute exactement un jour de présence (A et B : + 2).
    assert jour["presents"].sum() - minuit["presents"].sum() == 2
    with pytest.raises(ValueError):
        reconstituer_occupation(s, "2026-01-06", comptage="midi")


def test_sortie_inconnue_exclue_et_autre_service_ignore():
    df = table([("PED", "2025-06-01", None, None, False),          # ancien, sans sortie → inconnue
                ("MED", "2026-01-01", "2026-01-03", "Sortie", False),
                ("PED", "2026-01-01", "2026-01-03", "Décès", False)])
    s, rapport = preparer_sejours(df, "PED", "2026-01-05")
    assert rapport.total == 2 and rapport.par_statut["inconnue"] == 1
    occ = reconstituer_occupation(s, "2026-01-05")
    assert occ["presents"].tolist() == [1, 1, 0, 0]
    assert occ["sorties_deces"].sum() == 1


def test_sortie_avant_entree_rejetee():
    df = table([("PED", "2026-01-05", "2026-01-01", "Sortie", False)])
    s, rapport = preparer_sejours(df, "PED", "2026-02-01")
    assert rapport.sorties_avant_entree == 1 and s.empty


def test_erlang_b_valeurs_connues():
    assert erlang_b(1, 1.0) == pytest.approx(0.5)                  # a/(1+a)
    assert erlang_b(2, 1.0) == pytest.approx(0.2)                  # (a²/2)/(1+a+a²/2)
    assert erlang_b(0, 3.0) == 1.0


def test_little_regime_stable():
    # Une admission par jour, chaque séjour dure exactement 2 nuits : L doit valoir λW = 1 × 2.
    jours = pd.date_range("2026-01-01", periods=120, freq="D")
    df = table([("PED", j, j + pd.Timedelta(days=2), "Sortie", False) for j in jours])
    s, _ = preparer_sejours(df, "PED", "2026-05-15")
    occ = reconstituer_occupation(s, "2026-05-15")
    r = verifier_little(occ, s)
    assert r["L_mesure"] == pytest.approx(2.0) and r["lambda_x_W"] == pytest.approx(2.0)
    assert resume_occupation(occ)["occupation_max"] == 2


def test_durees_inconnues_estimees_par_le_prix():
    # 6 séjours connus à 7 500 F (3 nuits) et 6 à 15 000 F (5 nuits) ; deux séjours sans durée.
    lignes = [("PED", f"2026-01-{j:02d}", f"2026-01-{j + 3:02d}", "Sortie", 7500.0) for j in range(1, 7)]
    lignes += [("PED", f"2026-01-{j:02d}", f"2026-01-{j + 5:02d}", "Sortie", 15000.0) for j in range(1, 7)]
    lignes += [("PED", "2026-01-02", None, "Sortie", 15000.0), ("PED", "2026-01-03", None, "Sortie", None)]
    df = pd.DataFrame(lignes, columns=["service_code", "date_entree", "date_sortie", "issue", "prix"])
    for c in ("date_entree", "date_sortie"):
        df[c] = pd.to_datetime(df[c])
    exclues, _ = preparer_sejours(df, "PED", "2026-03-01")
    assert (exclues["statut"] == "inconnue").sum() == 2
    s, rapport = preparer_sejours(df, "PED", "2026-03-01", inconnues="estimee")
    est = s[s["statut"] == "imputee"]
    assert rapport.par_statut["imputee"] == 2
    assert est["duree_nuits"].tolist() == [5, 4]                 # prix 15 000 → 5 ; sans prix → issue « Sortie » → 4
    assert est["nuits_source"].tolist() == ["prix", "issue"]
    occ = reconstituer_occupation(s, "2026-03-01", debut="2026-01-01")
    assert occ.loc["2026-01-06", "dont_estimes"] == 2            # les deux enfants estimés sont encore là
    assert occ.loc["2026-01-07", "dont_estimes"] == 0            # 02/01 + 5 nuits et 03/01 + 4 nuits : sortis le 07
    assert not sorties_possibles(s, "2026-03-01").query("sejour in @est.index")["reelle"].any()   # hors DMS


def test_duree_aberrante_traitee_comme_absente():
    df = pd.DataFrame([("PED", "2026-01-01", "2026-09-01", "Sortie")], columns=["service_code", "date_entree", "date_sortie", "issue"])
    for c in ("date_entree", "date_sortie"):
        df[c] = pd.to_datetime(df[c])
    s, rapport = preparer_sejours(df, "PED", "2026-10-01")
    assert rapport.durees_aberrantes == 1 and s["statut"].tolist() == ["inconnue"]


def test_depart_ecrit_sans_date_jamais_encore_hospitalise():
    # Un enfant parti (SCAM, sortie…) sans date ni nombre de jours n'est pas « encore là » à l'extraction,
    # même admis récemment : sa durée est inconnue. Sans issue écrite, il reste « encore hospitalisé ».
    df = table([("PED", "2026-01-03", None, "Sortie contre avis médical", False),
                ("PED", "2026-01-03", None, None, False)])
    s, rapport = preparer_sejours(df, "PED", "2026-01-06")
    assert s["statut"].tolist() == ["inconnue", "censuree"]
    assert rapport.partis_sans_duree == 1
    occ = reconstituer_occupation(s, "2026-01-06", lits=1)
    assert occ["presents"].max() == 1                            # seul l'enfant sans issue est compté
