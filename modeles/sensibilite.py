r"""
Analyse de sensibilité à la convention du nombre de jours (données verrouillées).

Pourquoi : quand la date de sortie n'est pas écrite, on ne sait pas si « n jours » veut dire
n nuits ou n − 1 nuits (jour d'entrée et jour de sortie comptés). L'occupation de référence
(« attendue ») pondère la nuit incertaine par 1 − p ; les deux bornes supposent toutes les lignes
inclusives (« basse ») ou toutes en nuits (« haute »). Voir nera.occupation.

Question posée : les CONCLUSIONS du module lits dépendent-elles de ce choix ?
Pour chaque scénario, la même validation glissante que lancer_niveaux.py (mêmes origines, mêmes
hyperparamètres : ceux retenus sur la série attendue) est refaite ; chaque modèle est entraîné
et évalué sur la série du scénario (la « vérité » change avec le scénario).

Tous les niveaux sont notés sur les DEUX MÊMES critères (sinon les pertes ne se comparent pas :
la pinball est à une autre échelle que la MAE) :
  MAE      erreur absolue moyenne de la prévision centrale  ŷ  (la médiane q̂_0,5 pour un modèle
           quantile, la prévision elle-même pour un modèle ponctuel) ;
  pinball  perte pinball au τ décisionnel du quantile q̂_τ ; pour un modèle ponctuel, q̂_τ = ŷ :
           c'est la décision qu'on prendrait en lisant sa prévision comme un nombre de lits à prévoir.
Pour chaque critère :   gain = 1 − perte(modèle) / perte(persistance).

La conclusion est ROBUSTE si, pour chacun des deux critères :
  - le meilleur niveau est le même dans les trois scénarios ;
  - aucun gain ne change de signe de façon notable : un changement de signe ne compte que si le gain
    atteint au moins `seuil_gain` points (3 par défaut) en valeur absolue dans un des scénarios.
    Un gain qui reste sous le seuil partout signifie « équivalent à la persistance » : qu'il soit
    −1 % ou +0,4 % ne change pas la conclusion. Ces niveaux sont listés à part.
Sinon, la conclusion est SENSIBLE, et on le dit dans le mémoire (niveaux et critères concernés).

Prérequis : rapport_occupation.py (séries des trois scénarios) ; lancer_niveaux.py sur la série
attendue (hyperparamètres retenus — à défaut, valeurs par défaut, signalé à l'écran).

Exemple :
    ~/memoire-env/bin/python sensibilite.py --service PED --horizons 1 3 7

Sorties dans resultats/ :
    sensibilite_<SERVICE>.csv          une ligne par (horizon, niveau, scénario) : MAE, pinball, gains, métriques
    sensibilite_<SERVICE>_synthese.csv une ligne par horizon : meilleur niveau par critère et scénario, robustesse
"""
import argparse
from pathlib import Path

import pandas as pd
import torch

from lancer_niveaux import _Identite, empiler_sequentiel, lire_occupation, mesures, point
from nera.verrou import DATE_VERROU
from svr import metriques as M
from svr import references as R
from svr.caracteristiques import construire
from svr.niveaux import Hyperparametres, fabrique
from svr.validation import evaluer, origines_glissantes
from validation_finale import NOMS, hyperparametres

SCENARIOS = ("basse", "attendue", "haute")
CRITERES = ("MAE", "pinball")


def pertes(y: torch.Tensor, prevision, tau: float) -> dict[str, float]:
    """Les deux critères communs à tous les niveaux (voir l'en-tête)."""
    q_tau = prevision[tau] if isinstance(prevision, dict) else prevision
    return {"MAE": M.mae(y, point(prevision)), "pinball": M.pinball_moyenne(y, q_tau, tau)}


def main() -> None:
    p = argparse.ArgumentParser(description="Sensibilité des résultats à la convention du nombre de jours.")
    p.add_argument("--service", required=True)
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 7])
    p.add_argument("--tau", type=float, default=0.8)
    p.add_argument("--debut-validation", help="première origine (défaut : 6 mois avant le verrou)")
    p.add_argument("--pas", type=int, default=14)
    p.add_argument("--seuil-gain", type=float, default=3.0,
                   help="écart à la persistance (points de %%) en dessous duquel un gain est jugé nul (3)")
    a = p.parse_args()

    sortie = Path("resultats")
    debut_val = pd.Timestamp(a.debut_validation) if a.debut_validation else DATE_VERROU - pd.DateOffset(months=6)
    series = {sc: lire_occupation(a.service, sc) for sc in SCENARIOS}
    print("Occupation moyenne par scénario : "
          + " · ".join(f"{sc} {series[sc]['presents'].mean():.2f}" for sc in SCENARIOS) + "\n")
    lignes, synthese = [], []

    for h in a.horizons:
        print(f"══ Horizon J+{h}")
        chemin = sortie / f"hyperparametres_{a.service}_h{h}.json"
        if chemin.exists():
            hp = hyperparametres(chemin)
        else:
            print(f"  ({chemin.name} absent : hyperparamètres par défaut — lancez d'abord lancer_niveaux.py)")
            hp = {n: Hyperparametres(tau=a.tau) for n in NOMS}
        meilleurs = {c: {} for c in CRITERES}
        for sc in SCENARIOS:
            tab = construire(series[sc], h)
            decoupages = origines_glissantes(tab, debut_val, DATE_VERROU, pas=a.pas)
            plis = torch.cat([torch.full((len(d.evaluation),), i) for i, d in enumerate(decoupages)])
            ref = evaluer(tab, decoupages, lambda: _Identite())
            y, orig = ref["y"], ref["origines"]
            previsions = {"0 · persistance": R.persistance(tab.serie, orig, h)}
            for niveau, nom in NOMS.items():
                print(f"  [{sc}] {nom}…", flush=True)
                previsions[nom] = evaluer(tab, decoupages, fabrique(niveau, hp[niveau], tab.blocs))["prevision"]
            taus = sorted(previsions[NOMS[3]])
            bases = {"persistance": {t: previsions["0 · persistance"] for t in taus},
                     "niv3": previsions[NOMS[3]], "niv4": previsions[NOMS[4]]}
            empile, masque = empiler_sequentiel(bases, y, plis, taus)

            # Toutes les comparaisons sur les jours où l'empilement prédit (mêmes jours pour tous).
            jours = masque if masque.any() else torch.ones_like(y, dtype=torch.bool)
            sous = {n: ({t: v[jours] for t, v in pr.items()} if isinstance(pr, dict) else pr[jours])
                    for n, pr in previsions.items()}
            if masque.any():
                sous["5 · empilement"] = {t: v[jours] for t, v in empile.items()}
            y_j = y[jours]
            reference = pertes(y_j, sous["0 · persistance"], a.tau)
            par_niveau = {}
            for nom, pr in sous.items():
                pe = pertes(y_j, pr, a.tau)
                par_niveau[nom] = pe
                lignes.append({"horizon": h, "niveau": nom, "scenario": sc,
                               **{f"{c}": round(pe[c], 4) for c in CRITERES},
                               **{f"gain_{c}_%": round(100 * (1 - pe[c] / reference[c]), 1) if reference[c] else None
                                  for c in CRITERES},
                               **mesures(y_j, pr, a.tau)})
            for c in CRITERES:
                meilleurs[c][sc] = min(par_niveau, key=lambda n: par_niveau[n][c])
            print(f"  [{sc}] meilleur — MAE : {meilleurs['MAE'][sc]} · pinball τ={a.tau} : {meilleurs['pinball'][sc]}")

        tab_h = pd.DataFrame([l for l in lignes if l["horizon"] == h])
        robuste, ligne_synthese = True, {"horizon": h}
        for c in CRITERES:
            gains = tab_h.pivot(index="niveau", columns="scenario", values=f"gain_{c}_%")[list(SCENARIOS)]
            notable = gains.abs().max(axis=1) >= a.seuil_gain
            change = ~((gains > 0).all(axis=1) | (gains <= 0).all(axis=1))
            instables = list(gains.index[change & notable])
            equivalents = [n for n in gains.index[~notable] if n != "0 · persistance"]
            meme = len(set(meilleurs[c].values())) == 1
            robuste &= not instables and meme
            print(f"\n  Gain sur la persistance (%), critère {c} :\n" + gains.to_string())
            if equivalents:
                print(f"  équivalents à la persistance (|gain| < {a.seuil_gain} partout) : {', '.join(equivalents)}")
            if instables:
                print(f"  ! gain qui change de signe : {', '.join(instables)}")
            ligne_synthese |= {**{f"meilleur_{c}_{sc}": meilleurs[c][sc] for sc in SCENARIOS},
                               f"meme_meilleur_{c}": meme, f"signes_instables_{c}": " | ".join(instables),
                               f"equivalents_persistance_{c}": " | ".join(equivalents)}
        print(f"\n  → {'conclusion ROBUSTE' if robuste else 'conclusion SENSIBLE'} à la convention des jours\n")
        synthese.append(ligne_synthese | {"robuste": robuste})

    pd.DataFrame(lignes).to_csv(sortie / f"sensibilite_{a.service}.csv", sep=";", encoding="utf-8-sig", index=False)
    pd.DataFrame(synthese).to_csv(sortie / f"sensibilite_{a.service}_synthese.csv", sep=";", encoding="utf-8-sig",
                                  index=False)
    print(f"Résultats écrits dans {sortie.resolve()}")


if __name__ == "__main__":
    main()
