r"""
Le « coffre-fort » : la période de test final, jamais vue pendant le développement.

Données disponibles : juillet 2024 → octobre 2026. Les DEUX DERNIERS MOIS (à partir de
DATE_VERROU) sont réservés à la validation finale. Pendant tout le développement (choix des
variables, des modèles, des hyperparamètres, validation glissante), le code ne doit rien en
connaître — sinon on choisit, sans le vouloir, ce qui marche sur la période de test, et la
performance annoncée est optimiste.

Comment c'est garanti :
  1. nera.chargement.lire_export applique le verrou PAR DÉFAUT, dès la lecture du fichier :
       - les séjours admis à partir de DATE_VERROU sont retirés ;
       - pour les séjours admis avant mais sortis après, la sortie et l'issue sont effacées :
         au jour du verrou, on ne les connaissait pas encore (séjour censuré au verrou).
     La date d'extraction utilisée pendant le développement est donc DATE_VERROU.
  2. Seul le script de validation finale lit les données complètes, et seulement avec
     ouvrir_coffre(confirmation=…), qui écrit dans resultats/coffre_ouvertures.log la date
     de chaque ouverture : une trace de plus pour le mémoire.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

DATE_VERROU = pd.Timestamp("2026-09-01")       # septembre et octobre 2026 : test final
PHRASE = "J'ouvre le coffre pour la validation finale"
JOURNAL = Path("resultats") / "coffre_ouvertures.log"      # dans le dossier de travail, comme les autres sorties


def appliquer(df: pd.DataFrame, verrou: pd.Timestamp = DATE_VERROU) -> pd.DataFrame:
    """Retire tout ce qui n'était pas connu au jour du verrou."""
    garde = df[df["date_entree"] < verrou].copy()
    futur = garde["date_sortie"].notna() & (garde["date_sortie"] >= verrou)
    for c in ["date_sortie", "issue", "diagnostic_sortie", "traitement_sortie", "prix", "duree_sejour_jours"]:
        if c in garde:
            garde.loc[futur, c] = None
    if "sortie_calculee" in garde:
        garde.loc[futur, "sortie_calculee"] = False
    # Le nombre de jours, écrit à la sortie, n'était pas connu non plus.
    if "duree_jours" in garde:
        garde.loc[futur, "duree_jours"] = None
    return garde


def ouvrir_coffre(confirmation: str) -> None:
    """Autorise la lecture complète. À n'appeler QUE dans le script de validation finale."""
    if confirmation != PHRASE:
        raise PermissionError(f"Coffre fermé. Pour la validation finale uniquement, confirmez avec : « {PHRASE} ».")
    JOURNAL.parent.mkdir(exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} — coffre ouvert (données après le {DATE_VERROU:%d/%m/%Y})\n")
