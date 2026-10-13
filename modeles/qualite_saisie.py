r"""
Contrôle de la qualité de la saisie par DOUBLE SAISIE.

Protocole (à décrire dans le mémoire) : une seconde personne ressaisit, sans voir la première
saisie, un échantillon de photos tirées au hasard (par exemple 5 % des pages). Chacune exporte
son CSV depuis l'outil de saisie (« Exporter le CSV »). Ce script compare les deux fichiers
case par case et mesure l'accord. Un désaccord ne dit pas QUI s'est trompé : on revient alors
à la photo pour trancher, et le taux de désaccord donne une estimation du taux d'erreur.

Appariement des lignes : même photo et même N° d'ordre (une page ne contient pas deux fois le
même numéro). Les lignes présentes dans un seul fichier sont comptées à part (oubli ou ligne
en trop).

Mesures, colonne par colonne (calculées à la main, voir svr/analyse.py) :
  accord %   part des cases identiques après normalisation (minuscules, espaces multiples
             réduits, espaces en début et fin retirés) ;
  kappa      kappa de Cohen pour les colonnes à peu de valeurs possibles (sexe, ancien/nouveau,
             observation…) : l'accord corrigé de ce qui serait obtenu par hasard ;
  écart moyen   pour les colonnes numériques (nombre de jours, prix) : moyenne de |a − b|.

Exemple :
    ~/memoire-env/bin/python qualite_saisie.py donnees/saisie_A.csv donnees/saisie_B.csv
Écrit resultats/qualite_saisie.csv (une ligne par colonne) et resultats/qualite_saisie_desaccords.csv
(chaque case en désaccord, avec la photo et le N° d'ordre, pour aller vérifier).
"""
import argparse
import re
from pathlib import Path

import pandas as pd

from svr.analyse import kappa_cohen

CLE = ["Photo", "N° d'ordre"]
CATEGORIELLES = {"Sexe", "Ancien / Nouveau", "Observation"}
NUMERIQUES = {"Nbre de jours", "Prix"}


def normaliser(v) -> str:
    """Forme comparable d'une case : minuscules, espaces simples, sans espaces aux bords."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def nombre(v) -> float | None:
    """Premier nombre d'une case (« 3 jrs » → 3), ou None."""
    m = re.search(r"\d+(?:[.,]\d+)?", normaliser(v))
    return float(m.group().replace(",", ".")) if m else None


def main() -> None:
    p = argparse.ArgumentParser(description="Accord entre deux saisies des mêmes photos.")
    p.add_argument("saisie_a"); p.add_argument("saisie_b")
    a = p.parse_args()

    A = pd.read_csv(a.saisie_a, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    B = pd.read_csv(a.saisie_b, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    for df in (A, B):
        df["_cle"] = df["Photo"].map(normaliser) + " | " + df["N° d'ordre"].map(normaliser)
    communes = sorted(set(A["_cle"]) & set(B["_cle"]))
    print(f"Lignes appariées : {len(communes)} · seulement dans A : {len(set(A['_cle']) - set(B['_cle']))} · "
          f"seulement dans B : {len(set(B['_cle']) - set(A['_cle']))}")
    A, B = A.drop_duplicates("_cle").set_index("_cle").loc[communes], B.drop_duplicates("_cle").set_index("_cle").loc[communes]

    colonnes = [c for c in A.columns if c in B.columns and c not in ("Identifiant ligne", "Photo", "N° d'ordre", "Remarque de saisie")]
    lignes, desaccords = [], []
    for c in colonnes:
        va, vb = [normaliser(v) for v in A[c]], [normaliser(v) for v in B[c]]
        remplies = [i for i in range(len(va)) if va[i] or vb[i]]          # on ignore les cases vides des deux côtés
        if not remplies:
            continue
        a_r, b_r = [va[i] for i in remplies], [vb[i] for i in remplies]
        ligne = {"colonne": c, "cases comparées": len(remplies),
                 "accord %": round(100 * sum(x == y for x, y in zip(a_r, b_r)) / len(remplies), 1)}
        if c in CATEGORIELLES:
            ligne["kappa de Cohen"] = round(kappa_cohen(a_r, b_r), 3)
        if c in NUMERIQUES:
            paires = [(nombre(x), nombre(y)) for x, y in zip(a_r, b_r)]
            ecarts = [abs(x - y) for x, y in paires if x is not None and y is not None]
            ligne["écart moyen"] = round(sum(ecarts) / len(ecarts), 2) if ecarts else None
        lignes.append(ligne)
        for i in remplies:
            if va[i] != vb[i]:
                desaccords.append({"photo": A["Photo"].iloc[i], "n_ordre": A["N° d'ordre"].iloc[i], "colonne": c,
                                   "saisie A": A[c].iloc[i], "saisie B": B[c].iloc[i]})

    tableau = pd.DataFrame(lignes).set_index("colonne")
    total = sum(l["cases comparées"] for l in lignes)
    accord = sum(l["cases comparées"] * l["accord %"] / 100 for l in lignes) / total if total else float("nan")
    print(tableau.to_string())
    print(f"\nAccord global : {100 * accord:.1f} % des {total} cases remplies · désaccords : {len(desaccords)}")
    sortie = Path("resultats"); sortie.mkdir(exist_ok=True)
    tableau.to_csv(sortie / "qualite_saisie.csv", sep=";", encoding="utf-8-sig")
    pd.DataFrame(desaccords).to_csv(sortie / "qualite_saisie_desaccords.csv", sep=";", encoding="utf-8-sig", index=False)
    print(f"Écrit dans {sortie.resolve()}")


if __name__ == "__main__":
    main()
