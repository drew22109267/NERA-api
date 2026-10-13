"""Indicateurs hospitaliers et convention du nombre de jours (cas calculés à la main)."""
import pandas as pd
import pytest

from nera.chargement import convention_nombre_de_jours, preparer_sejours
from nera.indicateurs import indicateurs, indicateurs_avec_fourchette
from nera.occupation import reconstituer_occupation, trois_scenarios


def table(lignes):
    df = pd.DataFrame(lignes, columns=["service_code", "date_entree", "date_sortie", "duree_jours", "issue", "sortie_calculee"])
    df["date_entree"] = pd.to_datetime(df["date_entree"])
    df["date_sortie"] = pd.to_datetime(df["date_sortie"])
    return df


def test_indicateurs_a_la_main():
    # 2 lits, du 1er au 10 janvier (10 jours) :
    #   A : 1 → 5  (4 nuits, sortie)    B : 3 → 6  (3 nuits, décès)    C : 8 → encore là (censuré)
    df = table([("PED", "2026-01-01", "2026-01-05", 4, "Sortie", False),
                ("PED", "2026-01-03", "2026-01-06", 3, "Décès", False),
                ("PED", "2026-01-08", None, None, None, False)])
    s, _ = preparer_sejours(df, "PED", "2026-01-11")
    occ = reconstituer_occupation(s, "2026-01-11", lits=2)
    t = indicateurs(occ, s, lits=2).loc["Total"]
    # Présents à minuit : 1,1,2,2,1,0,0,1,1,1 → JH = 10 ; TOM = 10 / (2 × 10) = 50 %
    assert t["journees_hospitalisation"] == 10 and t["TOM_%"] == 50.0
    assert t["sorties"] == 2 and t["DMS_nuits"] == pytest.approx(3.5)            # (4 + 3) / 2
    assert t["rotation_lits"] == 1.0                                              # 2 sorties / 2 lits
    assert t["intervalle_rotation_jours"] == pytest.approx((2 * 10 - 10) / 2)     # 5 jours de lit vide par patient
    assert t["mortalite_%"] == 50.0 and t["deces"] == 1


def test_part_inclusive_globale_et_par_mois():
    # Janvier : 6 lignes inclusives, 2 en nuits ; février : 1 ligne en nuits ; 1 écart aberrant (ignoré).
    lignes = [("PED", "2026-01-05", "2026-01-07", 3, "Sortie", False)] * 6 \
        + [("PED", "2026-01-05", "2026-01-08", 3, "Sortie", False)] * 2 \
        + [("PED", "2026-02-03", "2026-02-06", 3, "Sortie", False),
           ("PED", "2026-02-03", "2026-02-20", 3, "Sortie", False)]
    c = convention_nombre_de_jours(table(lignes), "PED", pseudo_lignes=10)
    assert (c["inclusives"], c["nuits"], c["autres_ecarts"]) == (6, 3, 1)
    p = 6 / 9                                                        # p̂ = k / (k + m)
    assert c["p_global"] == pytest.approx(p)
    assert c["par_mois"][pd.Period("2026-01")] == pytest.approx((6 + 10 * p) / (8 + 10))   # (k_M + a p̂)/(n_M + a)
    assert c["par_mois"][pd.Period("2026-02")] == pytest.approx((0 + 10 * p) / (1 + 10))


def test_sans_ligne_mesurable_la_part_vaut_un_demi():
    c = convention_nombre_de_jours(table([("PED", "2026-01-01", None, 3, "Sortie", False)]), "PED")
    assert c["p_global"] == 0.5 and c["part_inclusive_%"] is None


def test_trois_scenarios_a_la_main():
    # A : sortie écrite 1 → 3 (2 nuits, sans nombre de jours : pas mesurable).  B : sortie calculée, entrée le 2, « 3 jrs » → 4 (inclusif) ou 5 (nuits).
    # Une ligne mesurable inclusive (C, 10 → 12, « 3 jrs ») et une en nuits (D, 10 → 13) : p̂ = 1/2 ;
    # janvier a 2 lignes mesurables → p_jan = (1 + 10·½) / (2 + 10) = ½.
    df = table([("PED", "2026-01-01", "2026-01-03", None, "Sortie", False),
                ("PED", "2026-01-02", "2026-01-05", 3, "Décès", True),
                ("PED", "2026-01-10", "2026-01-12", 3, "Sortie", False),
                ("PED", "2026-01-10", "2026-01-13", 3, "Sortie", False)])
    s, _ = preparer_sejours(df, "PED", "2026-01-20")
    assert s.loc[1, "sortie_basse"] == pd.Timestamp("2026-01-04") and s.loc[1, "p_inclusif"] == pytest.approx(0.5)
    occs = trois_scenarios(s, "2026-01-08", lits=2, debut="2026-01-01")
    # Présents à minuit du 1er au 7 : A les 1, 2 ; B les 2, 3 sûrement, le 4 avec probabilité 1 − p.
    assert occs["basse"]["presents"].tolist() == [1, 2, 1, 0, 0, 0, 0]
    assert occs["haute"]["presents"].tolist() == [1, 2, 1, 1, 0, 0, 0]
    assert occs["attendue"]["presents"].tolist() == [1, 2, 1, 0.5, 0, 0, 0]
    # Sortie de B (décès) : ½ le 4, ½ le 5 → DMS attendue = (2 + ½·2 + ½·3) / 2 = 2,25.
    t = indicateurs_avec_fourchette(occs, s, lits=2).loc["Total"]
    assert t["sorties"] == 2 and t["deces"] == 1 and t["DMS_nuits"] == pytest.approx(2.25)
    assert (t["TOM_bas_%"], t["TOM_%"], t["TOM_haut_%"]) == (round(100 * 4 / 14, 1), round(100 * 4.5 / 14, 1), round(100 * 5 / 14, 1))
    assert occs["attendue"]["sorties_deces"].tolist() == [0, 0, 0, 0.5, 0.5, 0, 0]


def test_scenario_attendu_toujours_entre_les_bornes():
    import numpy as np
    rng = np.random.default_rng(0)
    entrees = pd.Timestamp("2026-01-01") + pd.to_timedelta(rng.integers(0, 60, 200), unit="D")
    n = rng.integers(0, 10, 200)
    ecrite = rng.random(200) < 0.3
    inclusif = rng.random(200) < 0.6
    sorties = entrees + pd.to_timedelta(n - (ecrite & inclusif), unit="D")
    df = pd.DataFrame({"service_code": "PED", "date_entree": entrees, "date_sortie": sorties,
                       "duree_jours": n, "issue": "Sortie", "sortie_calculee": ~ecrite})
    s, _ = preparer_sejours(df, "PED", "2026-04-01")
    o = trois_scenarios(s, "2026-04-01")
    assert (o["basse"]["presents"] <= o["attendue"]["presents"] + 1e-9).all()
    assert (o["attendue"]["presents"] <= o["haute"]["presents"] + 1e-9).all()
