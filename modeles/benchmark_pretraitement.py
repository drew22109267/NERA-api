r"""
Banc de comparaison des choix de PRÉTRAITEMENT (des registres à la série d'occupation), données verrouillées.

Chaque dimension change UNE décision de prétraitement et garde toutes les autres au choix retenu (marqué « retenu ») :

  P1  Durées inconnues        exclure · médiane du service · estimée (prix, puis issue, puis médiane)  (retenu)
  P2  Fenêtre de censure      14 j · 30 j · p95 des durées connues (retenu) · 60 j
  P3  Convention des jours    attendue (nuit incertaine comptée 1 − p) (retenu) · tout inclusif · tout en nuits
  P4  Patients reportés       garder (retenu) · fusionner les reports confirmés
  P5  Période exploitable     part de durées connues ≥ 80 % · 90 % (retenu) · 95 % · rodage compté dès le début
  P6  Fin de série            aucune coupe · 7 derniers jours retirés · p95 du délai d'inscription  (retenu)
  P7  Trous (≥ 4 jours sans admission)  gardés (retenu) · lignes d'apprentissage qui les touchent exclues
  P8  Méthode de comptage     recensement de minuit (retenu) · présence dans la journée (jour de sortie compris)

Pourquoi deux mesures d'erreur
------------------------------
Changer le prétraitement change la série cible elle-même : comparer l'erreur de chaque variante sur SA série
ne dit pas laquelle est juste (une série plus lisse est plus facile à prévoir sans être plus vraie). On mesure :
  1. l'erreur contre sa propre série (MAE, pinball, gain sur la persistance) : la variante reste-t-elle prévisible ?
  2. l'erreur contre la série RETENUE, sur les mêmes jours : la décision change-t-elle les prévisions ?
     C'est sur cette mesure (même y pour toutes les variantes) que porte le test de Diebold-Mariano.
Une décision est sans conséquence si l'écart (2) n'est pas significatif ; sinon elle doit être justifiée par
autre chose que l'erreur (vraisemblance clinique, loi de Little, comptages réels).

Mêmes jours évalués pour toutes les variantes (intersection des dates cibles), même modèle (SVR quantile à noyau
composite, niveau 4, hyperparamètres retenus), même validation glissante, même horizon.

Exemple :
    ~/memoire-env/bin/python benchmark_pretraitement.py donnees/<export>.csv --service PED --lits 20 --horizons 1 7
Sorties : resultats/pretraitement_<SERVICE>_<P>_h<h>.csv, resultats/pretraitement_<SERVICE>.md
"""
from __future__ import annotations

import argparse
import dataclasses
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import torch

from benchmark_choix import en_markdown
from lancer_niveaux import point
from nera.chargement import lire_export, periode_exploitable, preparer_sejours
from nera.doublons import reperer_reports, retirer_reports_confirmes
from nera.garde_fous import verifier_little
from nera.occupation import reconstituer_occupation
from nera.verrou import DATE_VERROU
from svr import metriques as M
from svr import references as R
from svr.caracteristiques import construire
from svr.niveaux import Hyperparametres, fabrique
from svr.reproductibilite import ecrire_environnement
from svr.validation import Decoupage, evaluer, origines_glissantes
from validation_finale import hyperparametres

TYPE = torch.float64


@dataclass(frozen=True)
class Pretraitement:
    inconnues: str = "estimee"          # exclure | mediane | estimee
    censure: int | str = "p95"          # jours, ou « p95 »
    scenario: str = "attendue"          # attendue | basse | haute
    reports: str = "garder"             # garder | retirer
    seuil: float = 0.9                  # part minimale de durées connues (période exploitable)
    rodage_debut: bool = False
    fin: int | str = "p95"              # jours retirés en fin de série : 0, 7 ou « p95 » du délai d'inscription
    trous: str = "garder"               # garder | exclure
    comptage: str = "minuit"            # minuit | journee


RETENU = Pretraitement()
DIMENSIONS = {
    "P1": ("Durées inconnues", [("Exclure les séjours sans durée", dict(inconnues="exclure")),
                                ("Médiane du service", dict(inconnues="mediane")),
                                ("Estimée : prix, puis issue, puis médiane", dict(inconnues="estimee"))]),
    "P2": ("Fenêtre de censure (encore hospitalisé)", [("14 jours", dict(censure=14)), ("30 jours", dict(censure=30)),
                                                       ("p95 des durées connues", dict(censure="p95")), ("60 jours", dict(censure=60))]),
    "P3": ("Convention du nombre de jours", [("Attendue (nuit incertaine = 1 − p)", dict(scenario="attendue")),
                                            ("Tout inclusif (borne basse)", dict(scenario="basse")),
                                            ("Tout en nuits (borne haute)", dict(scenario="haute"))]),
    "P4": ("Patients « Ancien » reportés", [("Garder toutes les lignes", dict(reports="garder")),
                                            ("Fusionner les reports confirmés", dict(reports="retirer"))]),
    "P5": ("Période exploitable", [("Durées connues ≥ 80 %", dict(seuil=0.8)), ("Durées connues ≥ 90 %", dict(seuil=0.9)),
                                   ("Durées connues ≥ 95 %", dict(seuil=0.95)), ("≥ 90 %, rodage dès le début", dict(rodage_debut=True))]),
    "P6": ("Fin de série (délai d'inscription)", [("Aucune coupe", dict(fin=0)), ("7 derniers jours retirés", dict(fin=7)),
                                                 ("p95 du délai d'inscription", dict(fin="p95"))]),
    "P7": ("Trous de saisie (≥ 4 jours sans admission)", [("Gardés tels quels", dict(trous="garder")),
                                                          ("Lignes d'apprentissage qui les touchent exclues", dict(trous="exclure"))]),
    "P8": ("Méthode de comptage des présents", [("Recensement de minuit (nuits passées)", dict(comptage="minuit")),
                                                ("Présence dans la journée (jour de sortie compris)", dict(comptage="journee"))]),
}


def delai_inscription(df: pd.DataFrame, service: str) -> int:
    """p95 de (date d'enregistrement − date d'entrée), borné entre 2 et 10 jours (même règle que l'outil)."""
    d = df[df["service_code"] == service]
    if "date_enregistrement" not in d:
        return 0
    delai = (d["date_enregistrement"] - d["date_entree"]).dt.days.dropna()
    delai = delai[(delai >= 0) & (delai <= 60)]
    return int(min(10, max(2, round(float(delai.quantile(0.95)))))) if len(delai) else 0


def construire_serie(df: pd.DataFrame, service: str, lits, cfg: Pretraitement) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Des lignes du registre à la série d'occupation, selon le prétraitement `cfg`."""
    d = df
    if cfg.reports == "retirer":
        d, _ = retirer_reports_confirmes(df, reperer_reports(df, service))
    sejours, _ = preparer_sejours(d, service, DATE_VERROU, cfg.censure, cfg.inconnues)
    per = periode_exploitable(sejours, cfg.seuil, rodage_au_debut=cfg.rodage_debut)
    occ = reconstituer_occupation(sejours, DATE_VERROU, lits=lits, debut=per["debut"], scenario=cfg.scenario, comptage=cfg.comptage)
    coupe = delai_inscription(d, service) if cfg.fin == "p95" else int(cfg.fin)
    if coupe:
        occ = occ.iloc[:-coupe]
    return occ, sejours, {"debut": per["debut"], "coupe_fin": coupe}


def jours_de_trou(occ: pd.DataFrame, longueur: int = 4) -> set:
    """Jours appartenant à une suite d'au moins `longueur` jours consécutifs sans aucune admission."""
    vide = (occ["admissions"] == 0).to_list()
    trous, debut = set(), None
    for i, v in enumerate(vide + [False]):
        if v and debut is None:
            debut = i
        elif not v and debut is not None:
            if i - debut >= longueur:
                trous.update(occ.index[debut:i])
            debut = None
    return trous


def exclure_trous(tab, decs: list[Decoupage], trous: set, retards: int = 7) -> list[Decoupage]:
    """Retire des lignes d'APPRENTISSAGE celles dont les retards ou la cible tombent dans un trou."""
    if not trous:
        return decs
    origines = pd.DatetimeIndex(tab.dates_origine)
    touche = torch.tensor([any((o - pd.Timedelta(days=k)) in trous for k in range(retards)) or c in trous
                           for o, c in zip(origines, pd.DatetimeIndex(tab.dates_cible))])
    return [Decoupage(dc.entrainement[~touche[dc.entrainement]], dc.evaluation, dc.origine) for dc in decs]


def prevoir(occ: pd.DataFrame, h: int, hp: Hyperparametres, debut_val, pas: int, trous: str) -> pd.DataFrame:
    """Prévisions du niveau 4 et de la persistance, indexées par la date cible."""
    tab = construire(occ, h, debut_min=13)
    decs = origines_glissantes(tab, debut_val, DATE_VERROU, pas=pas)
    if trous == "exclure":
        decs = exclure_trous(tab, decs, jours_de_trou(occ))
    r = evaluer(tab, decs, fabrique(4, hp, tab.blocs))
    pers = R.persistance(tab.serie, r["origines"], h)
    t = pd.DataFrame({"y": r["y"].numpy(), "persistance": pers.numpy()}, index=r["dates"])
    for tau, v in r["prevision"].items():
        t[f"q{tau}"] = v.numpy()
    return t


def main() -> None:
    p = argparse.ArgumentParser(description="Banc de comparaison des choix de prétraitement.")
    p.add_argument("export"); p.add_argument("--service", required=True); p.add_argument("--lits", type=int)
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 7]); p.add_argument("--tau", type=float, default=0.8)
    p.add_argument("--pas", type=int, default=28); p.add_argument("--dimensions", nargs="+", default=list(DIMENSIONS))
    p.add_argument("--rapide", action="store_true", help="800 itérations d'optimisation")
    a = p.parse_args()
    sortie = Path("resultats"); sortie.mkdir(exist_ok=True)
    ecrire_environnement(sortie / f"pretraitement_{a.service}_environnement.json", **vars(a))
    df = lire_export(a.export)
    debut_val = DATE_VERROU - pd.DateOffset(months=6)
    rapport = [f"# Banc de comparaison du prétraitement — service {a.service}\n",
               "Une décision change à la fois ; « (retenu) » = choix retenu. MAE « propre » : contre la série de la variante ; "
               "MAE « retenue » : contre la série du choix retenu, mêmes jours pour toutes les variantes. "
               "Diebold-Mariano (perte absolue, correction HLN) sur la MAE « retenue ».\n"]
    occ_ref, sej_ref, _ = construire_serie(df, a.service, a.lits, RETENU)

    for h in a.horizons:
        chemin_hp = sortie / f"hyperparametres_{a.service}_h{h}.json"
        hp = hyperparametres(chemin_hp)[4] if chemin_hp.exists() else Hyperparametres(tau=a.tau)
        if a.rapide:
            hp = dataclasses.replace(hp, entrainement=dataclasses.replace(hp.entrainement, iterations=800))
        rapport.append(f"\n## Horizon J+{h}\n")
        for code in a.dimensions:
            titre, variantes = DIMENSIONS[code]
            print(f"\n── {code} · {titre} (J+{h})")
            res = []
            for nom, changement in variantes:
                cfg = dataclasses.replace(RETENU, **changement)
                debut = time.perf_counter()
                occ, sej, info = construire_serie(df, a.service, a.lits, cfg)
                prev = prevoir(occ, h, hp, debut_val, a.pas, cfg.trous)
                try:
                    little = verifier_little(occ, sej, scenario=cfg.scenario, comptage=cfg.comptage)["ecart_pourcent"]
                except Exception:                                   # période trop courte, etc.
                    little = float("nan")
                res.append((nom + (" (retenu)" if cfg == RETENU else ""), cfg == RETENU, occ, prev, info, little, time.perf_counter() - debut))
            communs = sorted(set.intersection(*(set(r[3].index) for r in res)))
            y_ref = torch.tensor(occ_ref["presents"].reindex(communs).to_numpy(), dtype=TYPE)
            lignes, points = [], {}
            for nom, retenu, occ, prev, info, little, secondes in res:
                t = prev.loc[communs]
                y = torch.tensor(t["y"].to_numpy(), dtype=TYPE)
                med = torch.tensor(t["q0.5"].to_numpy(), dtype=TYPE)
                q = torch.tensor(t[f"q{a.tau}"].to_numpy(), dtype=TYPE)
                pers = torch.tensor(t["persistance"].to_numpy(), dtype=TYPE)
                points[nom] = med
                lignes.append({"variante": nom, "début série": f"{info['debut']:%d/%m/%Y}", "jours coupés en fin": info["coupe_fin"],
                               "présents moyens": round(float(occ["presents"].mean()), 2),
                               "TOM %": round(100 * float(occ["taux_occupation"].mean()), 1) if "taux_occupation" in occ else None,
                               "écart Little %": little,
                               "MAE propre": round(M.mae(y, med), 3), f"pinball τ={a.tau} propre": round(M.pinball_moyenne(y, q, a.tau), 4),
                               "gain / persistance %": round(100 * (1 - M.mae(y, med) / M.mae(y, pers)), 1),
                               "MAE retenue": round(M.mae(y_ref, med), 3), "temps (s)": round(secondes, 1)})
            tab = pd.DataFrame(lignes).set_index("variante")
            nom_ref = next(r[0] for r in res if r[1])
            verdicts, pvals = [], []
            for nom in tab.index:
                if nom == nom_ref:
                    verdicts.append("— choix retenu"); pvals.append(None); continue
                dm = M.diebold_mariano(y_ref, points[nom], points[nom_ref], h=h)
                pvals.append(dm["p_valeur"])
                verdicts.append("identique" if dm["plus_precis"] == "indéterminé" else
                                ("meilleur" if dm["plus_precis"] == "A" else "moins bon") if dm["significatif_5pc"] else "équivalent")
            tab["DM p-valeur"], tab["vs choix retenu"] = pvals, verdicts
            print(tab.to_string())
            tab.to_csv(sortie / f"pretraitement_{a.service}_{code}_h{h}.csv", sep=";", encoding="utf-8-sig")
            mieux = list(tab.index[tab["vs choix retenu"] == "meilleur"])
            rapport += [f"\n### {code} · {titre}\n", f"{len(communs)} jours évalués.\n", en_markdown(tab), "\n",
                        (f"Significativement meilleur que le choix retenu : {', '.join(mieux)} — à revoir." if mieux
                         else f"Aucune variante ne fait significativement mieux que le choix retenu ({nom_ref})."), "\n"]
    (sortie / f"pretraitement_{a.service}.md").write_text("\n".join(rapport), encoding="utf-8")
    print(f"\nRapport : {(sortie / f'pretraitement_{a.service}.md').resolve()}")


if __name__ == "__main__":
    main()
