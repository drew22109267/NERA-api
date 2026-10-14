"""
VALIDATION FINALE — le seul script qui ouvre le coffre (septembre-octobre 2026).

À lancer UNE FOIS, à la toute fin, quand tous les choix sont figés (niveaux, variables,
hyperparamètres retenus par lancer_niveaux.py). Chaque ouverture est journalisée dans
resultats/coffre_ouvertures.log.

Déroulé :
  1. lecture complète de l'export (coffre ouvert) et reconstitution de l'occupation jusqu'à
     la date d'extraction réelle ;
  2. chaque niveau est entraîné avec SES hyperparamètres retenus sur les lignes dont la cible
     précède le verrou, puis prévoit les jours du coffre — prévisions faites origine par origine,
     comme en conditions réelles ;
  3. le niveau 5 (empilement) apprend ses poids sur les prévisions hors échantillon de la
     validation glissante d'avant le verrou, puis combine les prévisions du coffre ;
  4. métriques et tests de Diebold-Mariano sur la période du coffre, au total et mois par mois.

Réentraînement (option --reentrainement) :
  mensuel (défaut)  le coffre est découpé en blocs d'un mois ; au début de chaque mois, chaque modèle
                    est réentraîné avec tout ce qui précède, mois de test déjà écoulés compris
                    (septembre : appris jusqu'au 31 août ; octobre : appris jusqu'au 30 septembre).
                    Le bloc de septembre est un test à 1 mois, l'ensemble un test à 2 mois avec mise à
                    jour mensuelle, comme en service ;
  aucun             un seul entraînement avant le verrou, puis deux mois de prévisions sans mise à jour.
Lancer les deux montre ce que rapporte le réentraînement mensuel.

Exemple :
    ~/memoire-env/bin/python validation_finale.py donnees/<export>.csv --service PED --lits 20 \
        --extraction 2026-10-31 --confirmation "J'ouvre le coffre pour la validation finale"
"""
import argparse
import json
from pathlib import Path

import pandas as pd
import torch

from lancer_niveaux import empiler_sequentiel, etiquette, mesures, option_comptage, point
from nera.chargement import lire_export, periode_exploitable, preparer_sejours
from nera.occupation import reconstituer_occupation
from nera.verrou import DATE_VERROU
from svr import metriques as M
from svr import references as R
from svr.caracteristiques import construire
from svr.modeles import Entrainement
from svr.niveaux import Hyperparametres, fabrique
from svr.validation import Decoupage, decoupage_final, decoupages_test_mensuels, evaluer, origines_glissantes

NOMS = {1: "1 · SVR linéaire", 2: "2 · SVR RBF", 3: "3 · SVR quantile RBF", 4: "4 · SVR quantile composite"}


def hyperparametres(chemin: Path) -> dict[int, Hyperparametres]:
    brut = json.loads(chemin.read_text(encoding="utf-8"))
    sortie = {}
    for niveau, d in brut.items():
        d = dict(d)
        d["entrainement"] = Entrainement(**d["entrainement"])
        d["taus_intervalle"] = tuple(d["taus_intervalle"])
        sortie[int(niveau)] = Hyperparametres(**d)
    return sortie


def main() -> None:
    p = argparse.ArgumentParser(description="Validation finale sur la période du coffre.")
    p.add_argument("export")
    p.add_argument("--service", required=True)
    p.add_argument("--lits", type=int)
    p.add_argument("--extraction", required=True, help="date du relevé du registre (aaaa-mm-jj)")
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 7])
    p.add_argument("--confirmation", required=True)
    p.add_argument("--reentrainement", choices=["mensuel", "aucun"], default="mensuel",
                   help="mensuel : réentraîner au début de chaque mois du coffre ; aucun : un seul entraînement")
    p.add_argument("--debut-validation", help="début de la validation glissante utilisée pour l'empilement")
    option_comptage(p)
    a = p.parse_args()
    nom = etiquette(a.service, a.comptage)

    df = lire_export(a.export, confirmation_coffre=a.confirmation)          # coffre ouvert (journalisé)
    sejours, _ = preparer_sejours(df, a.service, a.extraction)
    debut = periode_exploitable(sejours)["debut"]
    occ = reconstituer_occupation(sejours, a.extraction, lits=a.lits, debut=debut, comptage=a.comptage)
    debut_val = pd.Timestamp(a.debut_validation) if a.debut_validation else DATE_VERROU - pd.DateOffset(months=6)
    sortie, tests = Path("resultats"), []

    for h in a.horizons:
        print(f"══ Horizon J+{h} — test sur le coffre (origines à partir du {DATE_VERROU:%d/%m/%Y})")
        hp = hyperparametres(sortie / f"hyperparametres_{nom}_h{h}.json")
        tab = construire(occ, h)
        blocs = (decoupages_test_mensuels(tab, DATE_VERROU) if a.reentrainement == "mensuel"
                 else [decoupage_final(tab, DATE_VERROU)])
        idx = torch.cat([b.evaluation for b in blocs])           # même ordre que les prévisions d'evaluer
        y, orig = tab.y[idx], tab.origines[idx]
        mois = pd.DatetimeIndex(tab.dates_origine[idx.numpy()]).strftime("%Y-%m")

        previsions = {"0 · persistance": R.persistance(tab.serie, orig, h),
                      "0 · saisonnière": R.saisonniere(tab.serie, orig, h),
                      "0 · moyenne mobile 7 j": R.moyenne_mobile(tab.serie, orig, h)}
        for niveau, nom in NOMS.items():
            print(f"  {nom}…")
            previsions[nom] = evaluer(tab, blocs, fabrique(niveau, hp[niveau], tab.blocs))["prevision"]

        # Empilement : poids appris sur les prévisions hors échantillon d'avant le verrou.
        glissants = origines_glissantes(tab, debut_val, DATE_VERROU, pas=14)
        avant = {n: evaluer(tab, glissants, fabrique(k, hp[k], tab.blocs))["prevision"] for k, n in NOMS.items() if k >= 3}
        y_avant = evaluer(tab, glissants, fabrique(3, hp[3], tab.blocs))["y"]
        taus = sorted(previsions[NOMS[3]])
        orig_avant = torch.cat([tab.origines[d.evaluation] for d in glissants])
        bases_avant = {"persistance": {t: R.persistance(tab.serie, orig_avant, h) for t in taus},
                       "niv3": avant[NOMS[3]], "niv4": avant[NOMS[4]]}
        bases_coffre = {"persistance": {t: previsions["0 · persistance"] for t in taus},
                        "niv3": previsions[NOMS[3]], "niv4": previsions[NOMS[4]]}
        # Un seul « pli » de test placé après tous les plis d'apprentissage.
        tout_y = torch.cat([y_avant, y])
        plis = torch.cat([torch.zeros(len(y_avant)), torch.ones(len(y))])
        tout = {n: {t: torch.cat([bases_avant[n][t], bases_coffre[n][t]]) for t in taus} for n in bases_avant}
        empile, masque = empiler_sequentiel(tout, tout_y, plis, taus)
        previsions["5 · empilement"] = {t: v[len(y_avant):] for t, v in empile.items()}

        tableau = pd.DataFrame([{"niveau": n, **mesures(y, pr, hp[3].tau)} for n, pr in previsions.items()]).set_index("niveau")
        print(tableau.to_string(), "\n")
        suffixe = "" if a.reentrainement == "mensuel" else "_sans_reentrainement"
        tableau.to_csv(sortie / f"validation_finale_{nom}_h{h}{suffixe}.csv", sep=";", encoding="utf-8-sig")
        # Mois par mois : septembre = test à 1 mois ; octobre = deuxième mois (après réentraînement si mensuel).
        par_mois = []
        for m in sorted(set(mois)):
            masque = torch.tensor(mois == m)
            sous = lambda pr: {t: v[masque] for t, v in pr.items()} if isinstance(pr, dict) else pr[masque]
            par_mois += [{"mois": m, "jours": int(masque.sum()), "niveau": n, **mesures(y[masque], sous(pr), hp[3].tau)}
                         for n, pr in previsions.items()]
        par_mois = pd.DataFrame(par_mois).set_index(["mois", "niveau"])
        print(par_mois.to_string(), "\n")
        par_mois.to_csv(sortie / f"validation_finale_{nom}_h{h}_par_mois{suffixe}.csv", sep=";", encoding="utf-8-sig")
        ordre = list(previsions)
        for i, nom in enumerate(ordre[1:], start=1):
            for contre in {"0 · persistance", ordre[i - 1]} - {nom}:
                tests.append({"horizon": h, "reentrainement": a.reentrainement, "modele_A": nom, "modele_B": contre,
                              **M.diebold_mariano(y, point(previsions[nom]), point(previsions[contre]), h=h)})

    pd.DataFrame(tests).to_csv(sortie / f"validation_finale_{nom}_tests{suffixe}.csv", sep=";", encoding="utf-8-sig", index=False)
    print(f"Résultats écrits dans {sortie.resolve()}")


if __name__ == "__main__":
    main()
