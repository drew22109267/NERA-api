r"""
Banc de sensibilité de TOUS les paramètres des modèles (données verrouillées).

Principe (analyse de sensibilité « un paramètre à la fois ») : on part des réglages retenus ; pour chaque
paramètre, on fait varier sa seule valeur sur une grille, tout le reste étant fixé, et l'on refait la même
validation glissante sur les mêmes jours. Pour chaque valeur : MAE, perte pinball au τ décisionnel,
couverture de l'intervalle à 90 %, temps de calcul, et test de Diebold-Mariano contre la valeur retenue.

Lecture
-------
  - Aucune valeur significativement meilleure que la valeur retenue : le réglage est défendable.
  - Une valeur significativement meilleure : le réglage retenu doit être revu (la recherche d'hyperparamètres
    de lancer_niveaux.py ne l'a pas trouvée, ou la grille de recherche était trop étroite).
  - Amplitude = (MAE max − MAE min) / MAE retenue : petite amplitude = modèle peu sensible à ce paramètre
    (rassurant : le résultat ne tient pas à un réglage fin) ; grande amplitude = paramètre critique, à citer.

Paramètres couverts
-------------------
  SVR quantile composite (niveau 4) : C, ε (tube), γ₁ (bloc occupation), γ₂ (bloc flux et saison), τ,
      taux d'apprentissage η₀, nombre d'itérations, échelle T de la décroissance η_t = η₀/√(1 + t/T),
      part des pas moyennée (Polyak), tolérance d'arrêt, direction préconditionnée, optimiseur.
  SVR RBF (niveau 2) : C, ε, γ.
  Forêt aléatoire quantile : nombre d'arbres, profondeur, taille minimale des feuilles, part des variables par nœud.
  Gradient boosting quantile : étapes, taux ν, profondeur, part du sous-échantillon.
  Perceptron multicouche : architecture, taux, pénalité λ, époques, patience, nombre de graines.
  LSTM : taille de l'état caché, taux, pénalité λ.
  Variables d'entrée : nombre de jours de retard (3 à 21).

Exemple :
    ~/memoire-env/bin/python benchmark_parametres.py --service PED --horizons 1 7 --familles svr4 svr2 foret
Sorties : resultats/parametres_<SERVICE>_<famille>_<paramètre>_h<h>.csv, figure .png par paramètre,
          resultats/parametres_<SERVICE>.md (tous les tableaux et une synthèse par famille).
"""
from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from benchmark_choix import DEBUT_COMMUN, Dimension, chrono, en_markdown
from lancer_niveaux import _Identite, lire_occupation, etiquette, option_comptage
from nera.verrou import DATE_VERROU
from svr.caracteristiques import construire
from svr.concurrents import HyperConcurrents, fabrique_concurrent
from svr.niveaux import Hyperparametres, fabrique
from svr.reproductibilite import ecrire_environnement
from svr.validation import evaluer, origines_glissantes
from validation_finale import hyperparametres

# famille → [(paramètre, libellé, valeurs, où : "hp" | "entrainement" | "concurrent" | "retards")]
GRILLES = {
    "svr4": [("C", "C (poids des erreurs)", [0.1, 0.3, 1.0, 3.0, 10.0, 30.0], "hp"),
             ("epsilon_quantile", "ε (tube, niveaux quantiles)", [0.0, 0.25, 0.5, 1.0], "hp"),
             ("gamma1", "γ₁ (portée, bloc occupation)", [0.01, 0.02, 0.05, 0.1, 0.2, 0.5], "hp"),
             ("gamma2", "γ₂ (portée, bloc flux et saison)", [0.02, 0.05, 0.1, 0.2, 0.5], "hp"),
             ("tau", "τ (quantile décisionnel)", [0.5, 0.6, 0.7, 0.8, 0.9], "hp"),
             ("taux", "η₀ (taux d'apprentissage d'Adam)", [0.005, 0.01, 0.02, 0.05, 0.1, 0.2], "entrainement"),
             ("iterations", "nombre maximal d'itérations", [300, 1000, 3000, 6000], "entrainement"),
             ("decroissance", "T (décroissance du pas ; aucune = pas constant)", [None, 100.0, 500.0, 2000.0], "entrainement"),
             ("moyenne_polyak", "part des pas moyennée (Polyak ; 0 = aucune)", [0.0, 0.25, 0.5, 0.75], "entrainement"),
             ("tolerance", "tolérance d'arrêt anticipé", [1e-5, 1e-7, 1e-9], "entrainement"),
             ("preconditionne", "direction préconditionnée α + Cg", [True, False], "entrainement"),
             ("optimiseur", "optimiseur", ["adam", "momentum", "sgd"], "entrainement")],
    "svr2": [("C", "C", [0.1, 0.3, 1.0, 3.0, 10.0, 30.0], "hp"),
             ("epsilon", "ε (tube ε-insensible, en lits)", [0.0, 0.25, 0.5, 1.0, 2.0], "hp"),
             ("gamma", "γ (portée du noyau RBF)", [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5], "hp")],
    "foret": [("arbres", "nombre d'arbres", [25, 50, 100, 300, 500], "concurrent"),
              ("profondeur_foret", "profondeur maximale", [3, 5, 8, 12, 20], "concurrent"),
              ("min_feuille", "taille minimale d'une feuille", [2, 5, 10, 20], "concurrent"),
              ("part_variables", "part des variables tirées par nœud", [0.15, 1 / 3, 0.5, 1.0], "concurrent")],
    "boosting": [("etapes", "nombre d'étapes", [50, 100, 300, 600], "concurrent"),
                 ("taux_boosting", "taux ν (shrinkage)", [0.01, 0.05, 0.1, 0.2], "concurrent"),
                 ("profondeur_boosting", "profondeur des arbres", [1, 2, 3, 5], "concurrent"),
                 ("sous_echantillon", "part du sous-échantillon", [0.5, 0.8, 1.0], "concurrent")],
    "mlp": [("couches", "architecture (neurones par couche)", [(8,), (32,), (32, 16), (64, 32), (32, 16, 8)], "concurrent"),
            ("taux_reseau", "taux d'apprentissage", [0.001, 0.003, 0.01, 0.03], "concurrent"),
            ("lambda_", "pénalité L2 λ", [0.0, 1e-4, 1e-3, 1e-2, 1e-1], "concurrent"),
            ("epoques", "époques maximales", [300, 800, 1500, 3000], "concurrent"),
            ("patience", "patience de l'arrêt anticipé", [50, 150, 300], "concurrent"),
            ("graines", "nombre d'initialisations moyennées", [1, 3, 5], "concurrent")],
    "lstm": [("cache_lstm", "taille de l'état caché H", [4, 8, 16, 32], "concurrent"),
             ("taux_reseau", "taux d'apprentissage", [0.003, 0.01, 0.03], "concurrent"),
             ("lambda_", "pénalité L2 λ", [0.0, 1e-3, 1e-2], "concurrent")],
    "variables": [("retards", "jours d'occupation passée en entrée", [3, 5, 7, 10, 14, 21], "retards")],
}
CONCURRENT_DE = {"foret": "foret", "boosting": "boosting", "mlp": "mlp", "lstm": "lstm"}


def remplacer_hp(hp: Hyperparametres, param: str, valeur, ou: str) -> Hyperparametres:
    if ou == "entrainement":
        return dataclasses.replace(hp, entrainement=dataclasses.replace(hp.entrainement, **{param: valeur}))
    return dataclasses.replace(hp, **{param: valeur})


def libelle_valeur(v) -> str:
    if v is None:
        return "aucune"
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    if isinstance(v, tuple):
        return "×".join(map(str, v))
    return str(v)


def figure(nom_fichier: Path, titre: str, valeurs: list, t: pd.DataFrame, retenu: str, tau: float) -> None:
    """Erreur selon la valeur du paramètre : MAE et pinball, valeur retenue cerclée."""
    x = list(range(len(valeurs)))
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(x, t["MAE"].to_numpy(), "o-", color="#0055f7", label="MAE")
    ax2 = ax.twinx()
    ax2.plot(x, t[f"pinball τ={tau}"].to_numpy(), "s--", color="#e07b00", label=f"pinball τ = {tau}")
    i = list(t.index).index(retenu)
    ax.plot([i], [t["MAE"].iloc[i]], "o", ms=14, mfc="none", mec="#17181a", label="valeur retenue")
    ax.set_xticks(x, [libelle_valeur(v) for v in valeurs], rotation=0)
    ax.set_title(titre, fontsize=10); ax.set_ylabel("MAE (lits)"); ax2.set_ylabel("perte pinball")
    lignes = ax.get_legend_handles_labels(); lignes2 = ax2.get_legend_handles_labels()
    ax.legend(lignes[0] + lignes2[0], lignes[1] + lignes2[1], fontsize=8, loc="best")
    fig.tight_layout(); fig.savefig(nom_fichier, dpi=150); plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="Sensibilité de tous les paramètres des modèles.")
    p.add_argument("--service", required=True)
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 7])
    p.add_argument("--tau", type=float, default=0.8)
    p.add_argument("--pas", type=int, default=28)
    p.add_argument("--familles", nargs="+", default=list(GRILLES), choices=list(GRILLES))
    p.add_argument("--rapide", action="store_true", help="800 itérations pour les SVR, modèles concurrents allégés")
    option_comptage(p)
    a = p.parse_args()
    a.service = etiquette(a.service, a.comptage)
    sortie = Path("resultats"); sortie.mkdir(exist_ok=True)
    ecrire_environnement(sortie / f"parametres_{a.service}_environnement.json", **vars(a))
    occ = lire_occupation(a.service)
    debut_val = DATE_VERROU - pd.DateOffset(months=6)
    rapport = [f"# Sensibilité de tous les paramètres — service {a.service}\n",
               "Un paramètre varie à la fois, tout le reste au réglage retenu (marqué « retenu »). Mêmes jours, même validation "
               "glissante. Diebold-Mariano (perte absolue, HLN) contre la valeur retenue. Amplitude = (MAE max − MAE min) / MAE retenue.\n"]
    synthese = []

    for h in a.horizons:
        chemin_hp = sortie / f"hyperparametres_{a.service}_h{h}.json"
        hps = hyperparametres(chemin_hp) if chemin_hp.exists() else {n: Hyperparametres(tau=a.tau) for n in (1, 2, 3, 4)}
        hpc = HyperConcurrents(tau=a.tau)
        if a.rapide:
            for n in hps:
                hps[n] = dataclasses.replace(hps[n], entrainement=dataclasses.replace(hps[n].entrainement, iterations=800))
            hpc = dataclasses.replace(hpc, arbres=60, etapes=80, epoques=300, graines=1)
        rapport.append(f"\n## Horizon J+{h}\n")
        tab_ref = construire(occ, h, debut_min=DEBUT_COMMUN)
        decs_ref = origines_glissantes(tab_ref, debut_val, DATE_VERROU, pas=a.pas)
        y_ref = evaluer(tab_ref, decs_ref, lambda: _Identite())["y"]

        for famille in a.familles:
            for param, libelle, valeurs, ou in GRILLES[famille]:
                if ou == "concurrent":
                    actuel = getattr(hpc, param)
                elif ou == "retards":
                    actuel = 7
                elif ou == "entrainement":
                    actuel = getattr(hps[4 if famille == "svr4" else 2].entrainement, param)
                else:
                    actuel = getattr(hps[4 if famille == "svr4" else 2], param)
                grille = list(valeurs) if actuel in valeurs else sorted([*valeurs, actuel], key=lambda v: (v is not None, v if not isinstance(v, (str, tuple, bool)) else 0))
                d = Dimension(f"{famille}·{param}", f"{famille} · {libelle}", f"Sensibilité à {libelle}", h, a.tau)
                print(f"\n── J+{h} · {famille} · {libelle}")
                for v in grille:
                    nom = f"{param} = {libelle_valeur(v)}"
                    if ou == "retards":
                        tab = construire(occ, h, retards=v, debut_min=DEBUT_COMMUN)
                        decs = origines_glissantes(tab, debut_val, DATE_VERROU, pas=a.pas)
                        fab = fabrique(4, hps[4], tab.blocs)
                    else:
                        tab, decs = tab_ref, decs_ref
                        if ou == "concurrent":
                            fab = fabrique_concurrent(CONCURRENT_DE[famille], dataclasses.replace(hpc, **{param: v}))
                        else:
                            niveau = 4 if famille == "svr4" else 2
                            fab = fabrique(niveau, remplacer_hp(hps[niveau], param, v, ou), tab.blocs)
                    r, s = chrono(lambda: evaluer(tab, decs, fab))
                    d.ajouter(nom, r["y"], r["prevision"], s, retenu=(v == actuel))
                t = d.tableau()
                print(t.to_string())
                fichier = f"parametres_{a.service}_{famille}_{param}_h{h}"
                t.to_csv(sortie / f"{fichier}.csv", sep=";", encoding="utf-8-sig")
                figure(sortie / f"{fichier}.png", f"{famille} · {libelle} (J+{h})", grille, t, d.retenu, a.tau)
                mae_ret = float(t.loc[d.retenu, "MAE"])
                amplitude = round(100 * (t["MAE"].max() - t["MAE"].min()) / mae_ret, 1)
                mieux = list(t.index[t.get("vs choix retenu", pd.Series(dtype=str)) == "meilleur"])
                synthese.append({"horizon": h, "famille": famille, "paramètre": libelle, "valeur retenue": libelle_valeur(actuel),
                                 "meilleure valeur (MAE)": t["MAE"].idxmin().split(" = ")[-1], "amplitude MAE %": amplitude,
                                 "verdict": ("à revoir : " + ", ".join(m.split(" = ")[-1] for m in mieux)) if mieux else "défendable"})
                rapport += [f"\n### {famille} · {libelle}\n", en_markdown(t), "\n",
                            f"![{libelle}]({fichier}.png)\n", f"Amplitude de la MAE : {amplitude} %. "
                            + (f"Valeur(s) significativement meilleure(s) : {', '.join(mieux)} — réglage à revoir." if mieux
                               else "Aucune valeur ne fait significativement mieux que la valeur retenue."), "\n"]
    s = pd.DataFrame(synthese)
    s.to_csv(sortie / f"parametres_{a.service}_synthese.csv", sep=";", encoding="utf-8-sig", index=False)
    rapport.insert(2, "\n## Synthèse\n\n" + en_markdown(s.set_index("paramètre")) + "\n")
    (sortie / f"parametres_{a.service}.md").write_text("\n".join(rapport), encoding="utf-8")
    print(f"\nRapport : {(sortie / f'parametres_{a.service}.md').resolve()}")


if __name__ == "__main__":
    main()
