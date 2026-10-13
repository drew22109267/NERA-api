r"""
Patients « reportés » : un même séjour écrit deux fois dans le registre.

Le problème : dans beaucoup de registres, les malades encore hospitalisés au début d'un mois
(ou d'une nouvelle page) sont RÉÉCRITS avec la mention « A » (ancien). Le même séjour apparaît
alors deux fois : à l'admission, puis au report. Compter les deux lignes compterait l'enfant
deux fois chaque soir où les deux séjours se chevauchent → occupation gonflée.

Ce que fait ce module, sans aucun nom (les noms ne sont jamais saisis) :
  1. Repère les lignes SUSPECTES : marquées « Ancien » ET enregistrées plus de `ecart_jours`
     jours après leur date d'entrée (un simple retard d'écriture d'un ou deux jours n'est pas
     un report).
  2. Pour chacune, cherche une ligne d'ORIGINE plausible dans le même service : même date
     d'entrée, même sexe, même âge (à un mois près, en mois), même quartier quand il est
     renseigné, enregistrée AVANT la ligne suspecte.
  3. Classe chaque ligne suspecte :
       « report confirmé »   exactement une origine plausible → c'est très probablement le même
                             séjour ;
       « ambigu »            plusieurs origines possibles → à vérifier sur les photos ;
       « sans origine »      aucune → l'enfant est probablement entré AVANT le début de la
                             saisie : la ligne est le seul témoin du séjour, on la garde.
Le retrait n'est fait que si on le demande (option `retirer` du rapport d'occupation), et
seulement pour les reports confirmés, après avoir reporté sur la ligne d'origine la sortie,
la durée et l'issue écrites sur la ligne de report quand l'origine ne les a pas.
Tant que le sens exact de « A » n'est pas confirmé par le service, garder les deux lignes et
lire ce diagnostic est la position prudente.
"""
from __future__ import annotations

import pandas as pd

COLONNES_REPRISES = ["date_sortie", "duree_jours", "issue"]


def reperer_reports(df: pd.DataFrame, service: str, ecart_jours: int = 3) -> pd.DataFrame:
    """Une ligne par ligne suspecte : son index, celui de l'origine (si unique) et son classement."""
    s = df[df["service_code"] == service]
    if "ancien_nouveau" not in s or "date_enregistrement" not in s:
        return pd.DataFrame(columns=["ligne", "origine", "classement", "candidats"])
    retard = (s["date_enregistrement"] - s["date_entree"]).dt.days
    suspects = s[(s["ancien_nouveau"] == "Ancien") & (retard > ecart_jours)]
    resultats = []
    for i, ligne in suspects.iterrows():
        c = s[(s.index != i) & (s["date_entree"] == ligne["date_entree"])
              & (s["date_enregistrement"] < ligne["date_enregistrement"])]
        for col in ("sexe", "quartier"):                           # mêmes valeurs quand elles sont connues
            if col in c and pd.notna(ligne.get(col)):
                c = c[c[col].isna() | (c[col] == ligne[col])]
        if "age_mois" in c and pd.notna(ligne.get("age_mois")):
            c = c[c["age_mois"].isna() | ((c["age_mois"] - ligne["age_mois"]).abs() <= 1)]
        classement = "report confirmé" if len(c) == 1 else "ambigu" if len(c) > 1 else "sans origine"
        resultats.append({"ligne": i, "origine": c.index[0] if len(c) == 1 else None,
                          "classement": classement, "candidats": len(c)})
    return pd.DataFrame(resultats, columns=["ligne", "origine", "classement", "candidats"])


def retirer_reports_confirmes(df: pd.DataFrame, reports: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Fusionne chaque report confirmé dans sa ligne d'origine, puis supprime la ligne de report."""
    df = df.copy()
    confirmes = reports[reports["classement"] == "report confirmé"]
    for _, r in confirmes.iterrows():
        origine, report = r["origine"], r["ligne"]
        for col in COLONNES_REPRISES:                               # l'information de sortie vient souvent du report
            if col in df and pd.isna(df.at[origine, col]) and pd.notna(df.at[report, col]):
                df.at[origine, col] = df.at[report, col]
                if col == "date_sortie" and "sortie_calculee" in df:  # la sortie garde son statut (écrite ou calculée)
                    df.at[origine, "sortie_calculee"] = df.at[report, "sortie_calculee"]
    return df.drop(index=confirmes["ligne"]), len(confirmes)
