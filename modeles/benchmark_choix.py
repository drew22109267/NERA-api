r"""
BANC DE COMPARAISON DES CHOIX — chaque décision de conception du module lits est mesurée contre
ses alternatives, dans les mêmes conditions (données verrouillées : le coffre n'est jamais lu).

Pourquoi : un choix n'est défendable devant un jury que si l'on montre ce qu'il apporte par
rapport aux autres options raisonnables. Chaque « dimension » ci-dessous change UNE chose et
garde tout le reste identique (mêmes jours évalués, mêmes découpages, mêmes hyperparamètres).

Dimensions comparées
--------------------
  D1  Modèles classiques contre SVR     persistance, saisonnière, moyenne mobile, Holt-Winters,
                                         régression ridge, SVR niveaux 1 à 4
  D2  Noyau                              linéaire, RBF, composite (même perte ε-insensible)
  D3  Fonction de perte                  carrée (ridge), ε-insensible avec ε = 0 ; 0,5 ; 1 ; 2
  D4  Quantile décisionnel τ et coûts    τ = 0,5 … 0,9 : coût moyen pour différents rapports
                                         « coût d'une pénurie / coût d'un lit vide »
  D5  Variables d'entrée                 retards seuls, + flux, + calendrier, complet,
                                         + jours fériés camerounais, 3 / 7 / 14 jours de retard
  D6  Prétraitement                      avec ou sans standardisation
  D7  Fenêtre d'entraînement             croissante (tout le passé) ou glissante (365, 180, 90 jours)
                                         — mesure aussi ce que coûte un historique court
  D8  Optimisation                       descente de gradient, momentum, Adam ; Adam sans moyenne
                                         de Polyak, sans préconditionnement, sans décroissance de η
  D9  Combinaison                        meilleur modèle seul, moyenne simple, empilement appris
  D10 Recherche d'hyperparamètres        défaut, grille, essaim particulaire  (option --recherche)
  D11 Chaque variable une à une          toutes les variables, puis la même sans chacune d'elles

Protocole commun
----------------
Validation glissante sur les 6 mois avant le verrou (origine tous les `pas` jours, modèle
réentraîné à chaque origine sur tout ce qui précède, standardisation réapprise à chaque fois).
D8 utilise un seul découpage (entraînement avant le début de la validation) : on y compare la
façon d'atteindre le minimum, pas la généralisation.

Pour chaque variante : MAE, RMSE, biais, perte pinball au τ décisionnel, couverture de
l'intervalle à 90 % (si la variante en produit un), temps de calcul, et le test de
Diebold-Mariano (correction HLN, perte absolue) contre le CHOIX RETENU de la dimension :
  « meilleur »    la variante bat significativement le choix retenu (p < 0,05)
  « moins bon »   le choix retenu la bat significativement
  « équivalent »  différence non significative
Si une variante est « meilleure », le choix retenu doit être revu — c'est le but de l'exercice.

Exemple :
    ~/memoire-env/bin/python benchmark_choix.py --service PED --horizons 1 7
    ~/memoire-env/bin/python benchmark_choix.py --service PED --horizons 1 --dimensions D1 D5 --rapide

Sorties dans resultats/ :
    benchmark_<SERVICE>_<D>_h<h>.csv    un tableau par dimension et par horizon
    benchmark_<SERVICE>.md              tous les tableaux, prêts pour le mémoire, avec la conclusion
    benchmark_<SERVICE>_environnement.json   versions et paramètres (reproductibilité)
"""
import argparse
import copy
import dataclasses
import time
from pathlib import Path

import pandas as pd
import torch

from lancer_niveaux import _Identite, chercher, empiler_sequentiel, lire_occupation, point
from nera.verrou import DATE_VERROU
from svr import analyse as A
from svr import metriques as M
from svr import references as R
from svr.calendrier import feries, vacances
from svr.caracteristiques import Standardiseur, construire
from svr import series_classiques as SC
from svr.classiques import RegressionRidge, choisir_holt_winters, holt_winters
from svr.concurrents import CONCURRENTS, HyperConcurrents, fabrique_concurrent
from svr.modeles import Entrainement, IntervalleQuantile, Perte, SVRLineaire, SVRNoyau, SVRNoyauComposite
from svr.niveaux import Hyperparametres, fabrique
from svr.noyaux import NoyauComposite, NoyauRBF
from svr.reproductibilite import ecrire_environnement
from svr.validation import Decoupage, decoupage_final, evaluer, origines_glissantes
from validation_finale import hyperparametres

TYPE = torch.float64
DEBUT_COMMUN = 13          # première origine commune à toutes les variantes (14 jours de retard au plus)
RAPPORTS_COUTS = (1, 2, 4, 9)   # c_pénurie / c_lit vide testés en D4 (τ* = r/(1+r) : 0,5 ; 0,67 ; 0,8 ; 0,9)


# ─────────────────────────────────────────────────────────────────────────────
# Mesure d'une variante
# ─────────────────────────────────────────────────────────────────────────────
class Dimension:
    """Collecte les variantes d'une dimension, puis les compare toutes au choix retenu."""

    def __init__(self, code: str, titre: str, question: str, h: int, tau: float):
        self.code, self.titre, self.question, self.h, self.tau = code, titre, question, h, tau
        self.lignes, self.points, self.y, self.retenu = [], {}, None, None

    def ajouter(self, nom: str, y: torch.Tensor, prevision, secondes: float, retenu: bool = False, **extra) -> None:
        """Calcule les métriques d'une variante. Toutes les variantes doivent porter sur les mêmes jours y."""
        if self.y is None:
            self.y = y
        elif len(y) != len(self.y) or not torch.equal(y, self.y):
            raise RuntimeError(f"{self.code} · {nom} : jours évalués différents des autres variantes.")
        p = point(prevision)                                           # médiane ou prévision ponctuelle
        q = prevision[self.tau] if isinstance(prevision, dict) and self.tau in prevision else p
        ligne = {"variante": nom + (" (retenu)" if retenu else ""), "MAE": round(M.mae(y, p), 3),
                 "RMSE": round(M.rmse(y, p), 3), "biais": round(M.biais(y, p), 3),
                 f"pinball τ={self.tau}": round(M.pinball_moyenne(y, q, self.tau), 4)}
        if isinstance(prevision, dict) and 0.05 in prevision and 0.95 in prevision:
            ligne["couverture 90 %"] = round(100 * M.couverture(y, prevision[0.05], prevision[0.95]), 1)
        ligne["temps (s)"] = round(secondes, 1)
        ligne.update(extra)
        self.lignes.append(ligne)
        self.points[ligne["variante"]] = p
        if retenu:
            self.retenu = ligne["variante"]

    def tableau(self) -> pd.DataFrame:
        """Ajoute le test de Diebold-Mariano de chaque variante contre le choix retenu."""
        t = pd.DataFrame(self.lignes).set_index("variante")
        if self.retenu is not None and len(self.y) > 10:
            verdicts, pvals = [], []
            for nom, p in self.points.items():
                if nom == self.retenu:
                    verdicts.append("— choix retenu"); pvals.append(None); continue
                dm = M.diebold_mariano(self.y, p, self.points[self.retenu], h=self.h)
                pvals.append(dm["p_valeur"])
                if dm["plus_precis"] == "indéterminé":
                    verdicts.append("identique")                  # mêmes prévisions que le choix retenu
                else:
                    verdicts.append(("meilleur" if dm["plus_precis"] == "A" else "moins bon")
                                    if dm["significatif_5pc"] else "équivalent")
            t["DM p-valeur"], t["vs choix retenu"] = pvals, verdicts
        return t

    def conclusion(self, t: pd.DataFrame) -> str:
        meilleur = t["MAE"].idxmin()
        phrase = f"Plus petite MAE : **{meilleur}** ({t.loc[meilleur, 'MAE']})."
        if self.retenu is not None and "vs choix retenu" in t:
            mieux = list(t.index[t["vs choix retenu"] == "meilleur"])
            phrase += (f" ⚠ Significativement meilleur que le choix retenu : {', '.join(mieux)} — le choix est à revoir."
                       if mieux else f" Aucune variante ne bat significativement le choix retenu ({self.retenu}).")
        return phrase


class SansColonne:
    """Le même modèle, à qui l'on cache la colonne j de X : mesure ce que cette variable apporte (ablation)."""

    def __init__(self, fabrique_modele, j: int):
        self.modele, self.j = fabrique_modele(), j

    def _x(self, X):
        X = torch.as_tensor(X)
        return torch.cat([X[:, :self.j], X[:, self.j + 1:]], dim=1)

    def entrainer(self, X, y):
        self.modele.entrainer(self._x(X), y)
        return self

    def predire(self, X):
        return self.modele.predire(self._x(X))


def chrono(fonction):
    """Exécute `fonction()` et renvoie (résultat, secondes écoulées)."""
    debut = time.perf_counter()
    resultat = fonction()
    return resultat, time.perf_counter() - debut


def en_markdown(t: pd.DataFrame) -> str:
    """Tableau markdown écrit à la main (pas de dépendance supplémentaire)."""
    colonnes = [t.index.name or "variante", *t.columns]
    lignes = ["| " + " | ".join(colonnes) + " |", "|" + "---|" * len(colonnes)]
    for nom, rangee in t.iterrows():
        cellules = ["" if (isinstance(v, float) and pd.isna(v)) or v is None else str(v) for v in rangee]
        lignes.append("| " + " | ".join([str(nom), *cellules]) + " |")
    return "\n".join(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# Programme principal
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="Banc de comparaison des choix de conception (module lits).")
    p.add_argument("--service", required=True)
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 7])
    p.add_argument("--tau", type=float, default=0.8)
    p.add_argument("--pas", type=int, default=28, help="jours entre deux origines de la validation glissante (28)")
    p.add_argument("--debut-validation", help="première origine (défaut : 6 mois avant le verrou)")
    p.add_argument("--dimensions", nargs="+", default=[f"D{i}" for i in (*range(1, 10), 11)],
                   help="dimensions à lancer (D1 … D9 et D11 par défaut ; D10 avec --recherche)")
    p.add_argument("--recherche", action="store_true", help="ajoute D10 (grille et essaim : long)")
    p.add_argument("--rapide", action="store_true", help="800 itérations au lieu de celles des hyperparamètres")
    a = p.parse_args()
    dims = set(a.dimensions) | ({"D10"} if a.recherche else set())

    resultats = Path("resultats")
    ecrire_environnement(resultats / f"benchmark_{a.service}_environnement.json", **vars(a))
    occ = lire_occupation(a.service)
    jours_feries = feries(range(occ.index.min().year, occ.index.max().year + 2),
                          Path("donnees") / "feries_supplementaires.csv")
    jours_vacances = vacances(Path("donnees") / "vacances_scolaires.csv")
    debut_val = pd.Timestamp(a.debut_validation) if a.debut_validation else DATE_VERROU - pd.DateOffset(months=6)
    fin_entr = int((occ.index < debut_val).sum())             # indice du premier jour de validation dans la série
    rapport = [f"# Banc de comparaison des choix — service {a.service}\n",
               f"Validation glissante du {debut_val:%d/%m/%Y} au verrou ({DATE_VERROU:%d/%m/%Y}), une origine tous les "
               f"{a.pas} jours, modèle réentraîné à chaque origine. « (retenu) » = choix retenu. Test de Diebold-Mariano "
               "(perte absolue, correction HLN) contre le choix retenu.\n"]

    for h in a.horizons:
        print(f"\n══════ Horizon J+{h}")
        chemin_hp = resultats / f"hyperparametres_{a.service}_h{h}.json"
        hp = hyperparametres(chemin_hp) if chemin_hp.exists() else {n: Hyperparametres(tau=a.tau) for n in (1, 2, 3, 4)}
        if a.rapide:
            for n in hp:
                hp[n] = dataclasses.replace(hp[n], entrainement=dataclasses.replace(hp[n].entrainement, iterations=800))
        e = hp[2].entrainement

        tab = construire(occ, h, debut_min=DEBUT_COMMUN)
        decs = origines_glissantes(tab, debut_val, DATE_VERROU, pas=a.pas)
        ref = evaluer(tab, decs, lambda: _Identite())
        y, orig = ref["y"], ref["origines"]
        rapport.append(f"\n## Horizon J+{h} — {len(y)} jours évalués, {len(decs)} origines\n")

        def prevoir(fab, tableau=tab, decoupages=decs):
            return chrono(lambda: evaluer(tableau, decoupages, fab)["prevision"])

        def publier(dim: Dimension) -> None:
            t = dim.tableau()
            print(f"\n── {dim.code} · {dim.titre}\n{t.to_string()}")
            t.to_csv(resultats / f"benchmark_{a.service}_{dim.code}_h{h}.csv", sep=";", encoding="utf-8-sig")
            rapport.extend([f"\n### {dim.code} · {dim.titre}\n", f"*{dim.question}*\n", en_markdown(t), "\n", dim.conclusion(t), "\n"])

        # ── D1 · Modèles classiques contre SVR ──────────────────────────────
        if "D1" in dims:
            d = Dimension("D1", "Modèles de référence, concurrents et SVR",
                          "Le SVR fait-il mieux que les méthodes statistiques usuelles et que les autres modèles d'apprentissage ?", h, a.tau)
            for nom, f in [("Persistance", lambda: R.persistance(tab.serie, orig, h)),
                           ("Saisonnière hebdomadaire", lambda: R.saisonniere(tab.serie, orig, h)),
                           ("Moyenne mobile 7 j", lambda: R.moyenne_mobile(tab.serie, orig, h))]:
                prev, s = chrono(f); d.ajouter(nom, y, prev, s)
            # Références sur la série seule (lissages, Thêta, AR, SARIMA) : paramètres réestimés à chaque origine,
            # quantiles tirés de leurs erreurs d'apprentissage (svr/series_classiques.py). Ordre SARIMA choisi une
            # fois, sur les jours d'avant la validation seulement.
            blocs = [tab.origines[dec.evaluation].tolist() for dec in decs]
            (ordre, essais), s_ordre = chrono(lambda: SC.choisir_ordre_sarima([float(v) for v in tab.serie[:fin_entr]]))
            pd.DataFrame(essais).to_csv(resultats / f"benchmark_{a.service}_sarima_ordres_h{h}.csv", sep=";", encoding="utf-8-sig", index=False)
            for nom, fab in SC.modeles_de_reference(ordre).items():
                prev, s = chrono(lambda: SC.evaluer_serie(fab, tab.serie, blocs, h, taus=(0.05, a.tau, 0.95)))
                d.ajouter(nom, y, prev, s + (s_ordre if "SARIMA" in nom else 0.0))
            (params, prev), s = chrono(lambda: (lambda pr: (pr, holt_winters(tab.serie, orig, h, **pr)))(
                choisir_holt_winters(tab.serie, h, fin_entr)))
            d.ajouter("Holt-Winters additif, grille fixée avant la validation", y, prev, s,
                      **{"réglages": ", ".join(f"{k}={v}" for k, v in params.items())})
            prev, s = prevoir(lambda: RegressionRidge(1.0)); d.ajouter("Régression ridge (λ = 1)", y, prev, s)
            # Concurrents d'apprentissage : même tableau de variables, même standardisation, même validation.
            hpc = HyperConcurrents(tau=a.tau)
            if a.rapide:
                hpc = dataclasses.replace(hpc, arbres=60, etapes=80, epoques=300, graines=1)
            for cle, nom in CONCURRENTS.items():
                prev, s = prevoir(fabrique_concurrent(cle, hpc, retards=7)); d.ajouter(nom, y, prev, s)
            for niveau, nom in [(1, "SVR linéaire (niveau 1)"), (2, "SVR RBF (niveau 2)"),
                                (3, "SVR quantile RBF (niveau 3)"), (4, "SVR quantile composite (niveau 4)")]:
                prev, s = prevoir(fabrique(niveau, hp[niveau], tab.blocs))
                d.ajouter(nom, y, prev, s, retenu=(niveau == 4))
            publier(d)

        # ── D2 · Noyau ──────────────────────────────────────────────────────
        if "D2" in dims:
            d = Dimension("D2", "Noyau", "Quel noyau décrit le mieux la dynamique ? (même perte ε-insensible, même C)", h, a.tau)
            eps = Perte("epsilon", hp[2].epsilon)
            for nom, fab, ret in [
                ("Linéaire", lambda: SVRLineaire(C=hp[2].C, perte=eps, entrainement=e), False),
                (f"RBF (γ = {hp[2].gamma:g})", lambda: SVRNoyau(NoyauRBF(hp[2].gamma), C=hp[2].C, perte=eps, entrainement=e), False),
                ("Composite occupation / flux et saison (β appris)",
                 lambda: SVRNoyauComposite(NoyauComposite(tab.blocs["occupation"], tab.blocs["flux_saison"], hp[4].gamma1, hp[4].gamma2),
                                           C=hp[2].C, perte=eps, entrainement=e), True)]:
                prev, s = prevoir(fab); d.ajouter(nom, y, prev, s, retenu=ret)
            publier(d)

        # ── D3 · Fonction de perte ──────────────────────────────────────────
        if "D3" in dims:
            d = Dimension("D3", "Fonction de perte", "Quelle perte pour un modèle linéaire identique ? (isole l'effet de la perte)", h, a.tau)
            prev, s = prevoir(lambda: RegressionRidge(1.0 / hp[1].C)); d.ajouter("Carrée (ridge, λ = 1/C)", y, prev, s)
            for eps_val in (0.0, 0.5, 1.0, 2.0):
                prev, s = prevoir(lambda ev=eps_val: SVRLineaire(C=hp[1].C, perte=Perte("epsilon", ev), entrainement=e))
                d.ajouter(f"ε-insensible, ε = {eps_val:g} lit" + (" (= valeur absolue)" if eps_val == 0 else ""), y, prev, s,
                          retenu=(eps_val == hp[1].epsilon))
            publier(d)

        # ── D4 · Quantile décisionnel τ et coûts ────────────────────────────
        if "D4" in dims:
            d = Dimension("D4", "Quantile décisionnel τ et coût des décisions",
                          "Quel τ minimise le coût réel selon le rapport pénurie / lit vide ? (τ optimal théorique = r/(1+r))", h, a.tau)
            for t_val in (0.5, 0.6, 0.7, 0.8, 0.9):
                prev, s = prevoir(lambda tv=t_val: SVRNoyau(NoyauRBF(hp[3].gamma), C=hp[3].C,
                                                             perte=Perte("pinball", tau=tv), entrainement=e))
                couts = {f"coût r={r}": round(A.cout_decision(y, prev, r, 1.0), 3) for r in RAPPORTS_COUTS}
                d.ajouter(f"τ = {t_val}", y, prev, s, retenu=(t_val == a.tau),
                          **{"jours sous-estimés %": round(100 * float((y > prev).double().mean()), 1),
                             "lits prévus en moyenne": round(float(prev.mean()), 2)}, **couts)
            t = d.tableau()
            print(f"\n── D4 · {d.titre}\n{t.to_string()}")
            t.to_csv(resultats / f"benchmark_{a.service}_D4_h{h}.csv", sep=";", encoding="utf-8-sig")
            meilleurs = ", ".join(f"r = {r} → {t[f'coût r={r}'].idxmin()}" for r in RAPPORTS_COUTS)
            rapport.extend([f"\n### D4 · {d.titre}\n", f"*{d.question}*\n", en_markdown(t), "\n",
                            f"τ le moins coûteux pour chaque rapport de coûts r = c_pénurie / c_lit vide : {meilleurs}. "
                            f"Le choix τ = {a.tau} correspond à r = {a.tau / (1 - a.tau):g}.\n"])

        # ── D5 · Variables d'entrée ─────────────────────────────────────────
        if "D5" in dims:
            d = Dimension("D5", "Variables d'entrée", "Que rapporte chaque groupe de variables ? (même modèle RBF du niveau 2)", h, a.tau)
            variantes = [("7 retards seuls", dict(flux=False, calendrier=False)),
                         ("7 retards + flux", dict(calendrier=False)),
                         ("7 retards + calendrier (jour, mois)", dict(flux=False)),
                         ("Complet : retards + flux + calendrier", dict()),
                         ("Complet + jours fériés camerounais", dict(feries=jours_feries)),
                         ("Complet + vacances scolaires", dict(vacances=jours_vacances)),
                         ("Complet + fériés + vacances scolaires", dict(feries=jours_feries, vacances=jours_vacances)),
                         ("3 retards + flux + calendrier", dict(retards=3)),
                         ("14 retards + flux + calendrier", dict(retards=14))]
            for nom, options in variantes:
                t_var = construire(occ, h, debut_min=DEBUT_COMMUN, **options)
                d_var = origines_glissantes(t_var, debut_val, DATE_VERROU, pas=a.pas)
                prev, s = prevoir(fabrique(2, hp[2], t_var.blocs), t_var, d_var)
                d.ajouter(nom, evaluer(t_var, d_var, lambda: _Identite())["y"], prev, s,
                          retenu=(nom.startswith("Complet :")), **{"variables": t_var.X.shape[1]})
            publier(d)

        # ── D6 · Standardisation ────────────────────────────────────────────
        if "D6" in dims:
            d = Dimension("D6", "Prétraitement", "La standardisation des variables est-elle utile ? (modèle RBF du niveau 2)", h, a.tau)
            prev, s = prevoir(fabrique(2, hp[2], tab.blocs)); d.ajouter("Avec standardisation", y, prev, s, retenu=True)
            brut = dataclasses.replace(tab, continues=[])          # plus aucune colonne standardisée
            prev, s = prevoir(fabrique(2, hp[2], tab.blocs), brut); d.ajouter("Sans standardisation", y, prev, s)
            publier(d)

        # ── D7 · Fenêtre d'entraînement ─────────────────────────────────────
        if "D7" in dims:
            d = Dimension("D7", "Fenêtre d'entraînement",
                          "Faut-il tout le passé, ou seulement les derniers mois ? (mesure aussi le coût d'un historique court)", h, a.tau)
            prev, s = prevoir(fabrique(4, hp[4], tab.blocs)); d.ajouter("Croissante (tout le passé)", y, prev, s, retenu=True)
            for jours in (365, 180, 90):
                fenetres = [Decoupage(dc.entrainement[torch.tensor(tab.dates_cible[dc.entrainement.numpy()]
                                                                   > dc.origine - pd.Timedelta(days=jours))],
                                      dc.evaluation, dc.origine) for dc in decs]
                prev, s = prevoir(fabrique(4, hp[4], tab.blocs), tab, fenetres)
                d.ajouter(f"Glissante : {jours} derniers jours", y, prev, s)
            publier(d)

        # ── D8 · Optimisation (un seul découpage) ───────────────────────────
        if "D8" in dims:
            final = decoupage_final(tab, debut_val)
            std = Standardiseur(tab.continues).ajuster(tab.X[final.entrainement])
            Z_e, y_e = std.transformer(tab.X[final.entrainement]), tab.y[final.entrainement]
            Z_v, y_v = std.transformer(tab.X[final.evaluation]), tab.y[final.evaluation]
            d = Dimension("D8", "Optimisation", "Comment atteindre le minimum de J le plus sûrement ? (SVR RBF, un découpage)", h, a.tau)
            variantes = [("Adam + Polyak + préconditionnement + décroissance η", {}, True),
                         ("Adam sans moyenne de Polyak", dict(moyenne_polyak=0.0), False),
                         ("Adam sans préconditionnement", dict(preconditionne=False), False),
                         ("Adam sans décroissance de η", dict(decroissance=None), False),
                         ("Momentum", dict(optimiseur="momentum"), False),
                         ("Descente de gradient simple", dict(optimiseur="sgd"), False)]
            for nom, options, ret in variantes:
                m = SVRNoyau(NoyauRBF(hp[2].gamma), C=hp[2].C, perte=Perte("epsilon", hp[2].epsilon),
                             entrainement=dataclasses.replace(e, **options))
                _, s = chrono(lambda: m.entrainer(Z_e, y_e))
                d.ajouter(nom, y_v, m.predire(Z_v), s, retenu=ret,
                          **{"J final": round(m.objectif_final, 2), "pas effectués": len(m.historique), "arrêt": m.arret,
                             "solution gardée": m.origine_solution})
            publier(d)

        # ── D9 · Combinaison ────────────────────────────────────────────────
        if "D9" in dims:
            (p3, p4), s34 = chrono(lambda: (evaluer(tab, decs, fabrique(3, hp[3], tab.blocs))["prevision"],
                                            evaluer(tab, decs, fabrique(4, hp[4], tab.blocs))["prevision"]))
            taus = sorted(p3)
            pers = R.persistance(tab.serie, orig, h)
            plis = torch.cat([torch.full((len(dc.evaluation),), i) for i, dc in enumerate(decs)])
            bases = {"persistance": {t: pers for t in taus}, "niv3": p3, "niv4": p4}
            (empile, masque), s5 = chrono(lambda: empiler_sequentiel(bases, y, plis, taus))
            if masque.any():
                tri = torch.sort(torch.stack([(pers + p3[t] + p4[t]) / 3 for t in taus]), dim=0).values
                moyenne = {t: tri[i] for i, t in enumerate(taus)}
                sous = lambda pr: {t: v[masque] for t, v in pr.items()}
                d = Dimension("D9", "Combinaison des modèles",
                              "Apprendre les poids de combinaison apporte-t-il plus qu'une moyenne ? (jours où l'empilement prédit)", h, a.tau)
                d.ajouter("Niveau 4 seul (meilleur modèle unique)", y[masque], sous(p4), s34 / 2)
                d.ajouter("Moyenne simple persistance + niv. 3 + niv. 4", y[masque], sous(moyenne), s34)
                d.ajouter("Empilement appris (poids positifs)", y[masque], sous(empile), s34 + s5, retenu=True)
                publier(d)

        # ── D10 · Recherche d'hyperparamètres (option) ──────────────────────
        if "D10" in dims:
            d = Dimension("D10", "Recherche d'hyperparamètres", "La recherche paie-t-elle son temps de calcul ? (niveau 2)", h, a.tau)
            prev, s = prevoir(fabrique(2, Hyperparametres(tau=a.tau), tab.blocs)); d.ajouter("Valeurs par défaut", y, prev, s)
            for methode in ("grille", "pso"):
                hp_m, s_r = chrono(lambda mt=methode: chercher(2, tab, decs, copy.deepcopy(hp[2]), mt))
                prev, s = prevoir(fabrique(2, hp_m, tab.blocs))
                d.ajouter("Grille" if methode == "grille" else "Essaim particulaire", y, prev, s + s_r,
                          retenu=(methode == "grille"), **{"C": round(hp_m.C, 3), "γ": round(hp_m.gamma, 4)})
            publier(d)

        # ── D11 · Chaque variable une à une (ablation) ──────────────────────
        if "D11" in dims:
            d = Dimension("D11", "Chaque variable, une à une",
                          "Que perd le modèle si on lui retire cette seule variable ? (modèle RBF du niveau 2, mêmes jours)", h, a.tau)
            prev, s = prevoir(fabrique(2, hp[2], tab.blocs))
            d.ajouter("Toutes les variables", y, prev, s, retenu=True)
            for j, nom in enumerate(tab.noms):
                prev, s = prevoir(lambda j=j: SansColonne(fabrique(2, hp[2], tab.blocs), j))
                d.ajouter(f"Sans {nom}", y, prev, s)
            publier(d)

    (resultats / f"benchmark_{a.service}.md").write_text("\n".join(rapport), encoding="utf-8")
    print(f"\nTableaux écrits dans {resultats.resolve()} (benchmark_{a.service}.md pour le mémoire)")


if __name__ == "__main__":
    main()
