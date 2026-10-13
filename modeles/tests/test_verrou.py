"""Le coffre-fort et la période exploitable (cas construits pour le test)."""
import pandas as pd
import pytest

from nera import verrou
from nera.chargement import periode_exploitable, preparer_sejours


def table(lignes):
    df = pd.DataFrame(lignes, columns=["service_code", "date_entree", "date_sortie", "issue", "duree_jours"])
    df["date_entree"] = pd.to_datetime(df["date_entree"])
    df["date_sortie"] = pd.to_datetime(df["date_sortie"])
    return df


def test_le_verrou_cache_le_futur():
    df = table([("PED", "2026-08-20", "2026-08-25", "Sortie", 5),     # avant : gardé tel quel
                ("PED", "2026-08-28", "2026-09-04", "Décès", 7),      # sort après le verrou : issue cachée
                ("PED", "2026-09-10", "2026-09-12", "Sortie", 2)])    # admis après : invisible
    v = verrou.appliquer(df)
    assert len(v) == 2
    assert v.iloc[0]["issue"] == "Sortie"
    assert pd.isna(v.iloc[1]["date_sortie"]) and pd.isna(v.iloc[1]["issue"]) and pd.isna(v.iloc[1]["duree_jours"])
    s, _ = preparer_sejours(v.assign(sortie_calculee=False), "PED", verrou.DATE_VERROU)
    assert s.iloc[1]["statut"] == "censuree"                           # encore hospitalisé au verrou


def test_le_coffre_refuse_une_mauvaise_phrase():
    with pytest.raises(PermissionError):
        verrou.ouvrir_coffre("ouvre")


def test_periode_exploitable_detecte_le_debut_des_durees():
    # Janvier-février : ni sortie ni durée (le service ne les notait pas) ; à partir de mars : complet.
    lignes = [("MED", f"2025-0{m}-{j:02d}", None, None, None) for m in (1, 2) for j in range(1, 21)]
    lignes += [("MED", f"2025-0{m}-{j:02d}", f"2025-0{m}-{j + 3:02d}", "Sortie", 3) for m in (3, 4, 5) for j in range(1, 21)]
    s, _ = preparer_sejours(table(lignes).assign(sortie_calculee=False), "MED", "2025-06-15")
    p = periode_exploitable(s, rodage_jours=14)
    assert p["premier_mois_complet"] == "2025-03"
    assert p["debut"] == pd.Timestamp("2025-03-15")
