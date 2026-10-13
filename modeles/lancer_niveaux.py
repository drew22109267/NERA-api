"""
Analyse d'ablation du module lits : niveaux 0 à 5 en validation glissante (rolling origin),
sur les données VERROUILLÉES (la période de test final n'est jamais lue ici).

Entrée : resultats/occupation_<SERVICE>.csv, produit par rapport_occupation.py.

Exemple :
    ~/memoire-env/bin/python lancer_niveaux.py --service PED --horizons 1 3 7 --tau 0.8
    ~/memoire-env/bin/python lancer_niveaux.py --service PED --recherche pso      (plus long)

Sorties dans resultats/ :
    ablation_<SERVICE>_h<h>.csv      une ligne par niveau, toutes les métriques
    ablation_<SERVICE>_tests.csv     tests de Diebold-Mariano (chaque niveau contre le précédent
                                     et contre la persistance)
    hyperparametres_<SERVICE>_h<h>.json  configuration retenue, relue par la validation finale
"""
import argparse
import copy
import json
from pathlib import Path

import pandas as pd
import torch

from nera.verrou import DATE_VERROU
from svr import metriques as M
from svr import references as R
from svr.caracteristiques import construire
from svr.empilement import Empilement
from svr.modeles import Entrainement, Perte
from svr.niveaux import Hyperparametres, fabrique
from svr.recherche import Dimension, essaim_particulaire, recherche_grille
from svr.validation import evaluer, origines_glissantes


def lire_occupation(service: str, scenario: str = "attendue") -> pd.DataFrame:
    """Série produite par rapport_occupation.py : « attendue » (référence), ou une borne « basse » / « haute »."""
    nom = f"occupation_{service}.csv" if scenario == "attendue" else f"occupation_{service}_{scenario}.csv"
    occ = pd.read_csv(Path("resultats") / nom, sep=";", encoding="utf-8-sig", index_col="jour", parse_dates=["jour"])
    if occ.index.max() >= DATE_VERROU:
        raise RuntimeError("La série contient des jours de la période verrouillée : refaites rapport_occupation.py.")
    return occ


def mesures(y, prevision, tau: float) -> dict:
    """Métriques d'un niveau : ponctuelles (médiane) et, pour les quantiles, intervalle + τ décisionnel."""
    if isinstance(prevision, dict):
        taus = sorted(prevision)
        r = M.resume_intervalle(y, prevision[taus[0]], prevision[0.5], prevision[taus[-1]],
                                (taus[0], 0.5, taus[-1]))
        r[f"pinball_tau_{tau}"] = round(M.pinball_moyenne(y, prevision[tau], tau), 4)
        r[f"jours_au_dessus_q{tau}_%"] = round(100 * float((y > prevision[tau]).double().mean()), 1)
        return r
    return M.resume_ponctuel(y, prevision)


def point(prevision):
    return prevision[0.5] if isinstance(prevision, dict) else prevision


def empiler_sequentiel(previsions: dict[str, dict], y: torch.Tensor, plis: torch.Tensor, taus) -> tuple[dict, torch.Tensor]:
    """
    Niveau 5. Pour chaque pli k, le méta-modèle apprend sur les prévisions hors échantillon des plis
    précédents (< k) et prédit le pli k : aucune information du futur.
    `previsions` : {nom du modèle de base: {τ: tenseur}}.  Renvoie {τ: prévision} et le masque des
    jours prédits (les premiers plis servent seulement à apprendre).
    """
    sortie = {t: torch.full_like(y, float("nan")) for t in taus}
    for k in plis.unique().tolist():
        appr, cible = plis < k, plis == k
        if appr.sum() < 28:
            continue
        for t in taus:
            Pm = torch.stack([previsions[nom][t] for nom in previsions], dim=1)
            meta = Empilement(lambda_=1e-3, C=1.0, perte=Perte("pinball", tau=t),
                              entrainement=Entrainement(taux=0.02, iterations=2000))
            meta.entrainer(Pm[appr], y[appr])
            sortie[t][cible] = meta.predire(Pm[cible])
    masque = ~torch.isnan(sortie[taus[0]])
    trie, _ = torch.sort(torch.stack([sortie[t] for t in taus]), dim=0)
    return {t: trie[i] for i, t in enumerate(taus)}, masque


def chercher(niveau: int, tab, decoupages, hp: Hyperparametres, methode: str) -> Hyperparametres:
    """Hyperparamètres du niveau par grille ou PSO ; score = pinball au τ décisionnel (ou MAE)."""
    def objectif(config: dict) -> float:
        h2 = copy.deepcopy(hp)
        for k, v in config.items():
            setattr(h2, k, v)
        r = evaluer(tab, decoupages, fabrique(niveau, h2, tab.blocs))
        p = r["prevision"]
        return M.pinball_moyenne(r["y"], p[h2.tau], h2.tau) if isinstance(p, dict) else M.mae(r["y"], p)

    nom_eps = "epsilon_quantile" if niveau in (3, 4) else "epsilon"
    if methode == "grille":
        espace = {"C": [0.3, 1.0, 3.0], nom_eps: [0.0, 0.25] if niveau in (3, 4) else [0.5, 1.0]}
        if niveau in (2, 3):
            espace["gamma"] = [0.02, 0.05, 0.2]
        if niveau == 4:
            espace |= {"gamma1": [0.02, 0.1], "gamma2": [0.05, 0.2]}
        meilleur = recherche_grille(espace, objectif)["meilleur"]
    else:
        espace = {"C": Dimension(0.1, 10, "log"), nom_eps: Dimension(0.0, 1.0 if niveau in (3, 4) else 2.0)}
        if niveau in (2, 3):
            espace["gamma"] = Dimension(0.005, 1.0, "log")
        if niveau == 4:
            espace |= {"gamma1": Dimension(0.005, 1.0, "log"), "gamma2": Dimension(0.005, 1.0, "log")}
        meilleur = essaim_particulaire(espace, objectif, particules=8, iterations=10)["meilleur"]
    retenu = copy.deepcopy(hp)
    for k, v in meilleur.items():
        if k != "score":
            setattr(retenu, k, v)
    print(f"    niveau {niveau} : {', '.join(f'{k}={v:.4g}' for k, v in meilleur.items())}")
    return retenu


def main() -> None:
    p = argparse.ArgumentParser(description="Ablation du module lits (niveaux 0 à 5).")
    p.add_argument("--service", required=True)
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 7])
    p.add_argument("--tau", type=float, default=0.8, help="quantile décisionnel τ = c(pénurie)/(c(pénurie)+c(surcapacité))")
    p.add_argument("--debut-validation", help="première origine de la validation glissante (défaut : 6 mois avant le verrou)")
    p.add_argument("--pas", type=int, default=14, help="jours entre deux origines (14)")
    p.add_argument("--recherche", choices=["aucune", "grille", "pso"], default="aucune")
    p.add_argument("--scenario", choices=["attendue", "basse", "haute"], default="attendue",
                   help="série d'occupation : attendue (référence) ou une borne de la convention des jours")
    a = p.parse_args()

    occ = lire_occupation(a.service, a.scenario)
    # Les résultats d'une borne sont écrits à part : seuls ceux du scénario « attendue » sont relus
    # par la validation finale.
    suffixe = "" if a.scenario == "attendue" else f"_{a.scenario}"
    debut_val = pd.Timestamp(a.debut_validation) if a.debut_validation else DATE_VERROU - pd.DateOffset(months=6)
    print(f"Série : {occ.index.min():%d/%m/%Y} → {occ.index.max():%d/%m/%Y} · validation glissante "
          f"du {debut_val:%d/%m/%Y} au verrou ({DATE_VERROU:%d/%m/%Y}), pas de {a.pas} j\n")
    sortie, tests = Path("resultats"), []

    for h in a.horizons:
        print(f"══ Horizon J+{h}")
        tab = construire(occ, h)
        decoupages = origines_glissantes(tab, debut_val, DATE_VERROU, pas=a.pas)
        plis = torch.cat([torch.full((len(d.evaluation),), i) for i, d in enumerate(decoupages)])
        hp = Hyperparametres(tau=a.tau)
        previsions = {}

        # Niveau 0 — références, sur exactement les mêmes jours que les modèles
        ref = evaluer(tab, decoupages, lambda: _Identite())   # ne sert qu'à aligner y et les origines
        y, orig = ref["y"], ref["origines"]
        previsions["0 · persistance"] = R.persistance(tab.serie, orig, h)
        previsions["0 · saisonnière"] = R.saisonniere(tab.serie, orig, h)
        previsions["0 · moyenne mobile 7 j"] = R.moyenne_mobile(tab.serie, orig, h)

        # Niveaux 1 à 4
        noms = {1: "1 · SVR linéaire", 2: "2 · SVR RBF", 3: "3 · SVR quantile RBF", 4: "4 · SVR quantile composite"}
        retenus = {}
        for niveau, nom in noms.items():
            hp_n = chercher(niveau, tab, decoupages, hp, a.recherche) if a.recherche != "aucune" else hp
            retenus[niveau] = hp_n
            print(f"  {nom}…")
            r = evaluer(tab, decoupages, fabrique(niveau, hp_n, tab.blocs))
            previsions[nom] = r["prevision"]

        # Niveau 5 — empilement des niveaux 3 et 4 et de la persistance, appris pli après pli
        taus = sorted(previsions[noms[3]])
        bases = {"persistance": {t: previsions["0 · persistance"] for t in taus},
                 "niv3": previsions[noms[3]], "niv4": previsions[noms[4]]}
        empile, masque = empiler_sequentiel(bases, y, plis, taus)

        lignes = []
        for nom, prev in previsions.items():
            lignes.append({"niveau": nom, **mesures(y, prev, a.tau)})
        # Le niveau 5 n'a pas de prévision sur les premiers plis : on le compare au niveau 4 sur les mêmes jours.
        if masque.any():
            lignes.append({"niveau": "5 · empilement", **mesures(y[masque], {t: v[masque] for t, v in empile.items()}, a.tau)})
            lignes.append({"niveau": "4 · (mêmes jours que 5)",
                           **mesures(y[masque], {t: v[masque] for t, v in previsions[noms[4]].items()}, a.tau)})
        tableau = pd.DataFrame(lignes).set_index("niveau")
        print(tableau.to_string(), "\n")
        tableau.to_csv(sortie / f"ablation_{a.service}{suffixe}_h{h}.csv", sep=";", encoding="utf-8-sig")

        # Tests de Diebold-Mariano : chaque niveau contre la persistance et contre le niveau précédent
        ordre = list(previsions)
        for i, nom in enumerate(ordre[1:], start=1):
            for contre in {"0 · persistance", ordre[i - 1]}:
                if contre == nom:
                    continue
                t = M.diebold_mariano(y, point(previsions[nom]), point(previsions[contre]), h=h)
                tests.append({"horizon": h, "modele_A": nom, "modele_B": contre, **t})

        with open(sortie / f"hyperparametres_{a.service}{suffixe}_h{h}.json", "w", encoding="utf-8") as f:
            json.dump({str(n): hp_n.vers_dict() | {"entrainement": vars(hp_n.entrainement)} for n, hp_n in retenus.items()},
                      f, ensure_ascii=False, indent=2)

    pd.DataFrame(tests).to_csv(sortie / f"ablation_{a.service}{suffixe}_tests.csv", sep=";", encoding="utf-8-sig", index=False)
    print(f"Résultats écrits dans {sortie.resolve()}")


class _Identite:
    """Modèle vide : permet de récupérer y et les origines alignés avec les autres niveaux."""
    def entrainer(self, X, y):
        return self

    def predire(self, X):
        return torch.zeros(X.shape[0], dtype=torch.float64)


if __name__ == "__main__":
    main()
