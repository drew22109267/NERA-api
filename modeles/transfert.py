r"""
TRANSFERT de la méthode du service source (pédiatrie, 27 mois de données) vers des services
cibles qui n'ont qu'une fenêtre courte (par exemple mai → octobre 2026), et prévision du total
de l'hôpital comme somme des services.

Le problème
-----------
Un modèle appris sur 3 mois ne voit ni une saison complète ni beaucoup de situations rares.
Le banc de comparaison (D7) montre ce que coûte un historique court. On compare ici trois
façons de s'en sortir, sur les MÊMES jours du service cible :

  A · local          le modèle n'apprend que sur la fenêtre courte du service cible, avec les
                     hyperparamètres de la source gelés (pas de nouveau réglage sur 3 mois,
                     qui surapprendrait) ;
  B · transfert direct  le modèle n'apprend QUE sur la source ; il est appliqué tel quel au
                     service cible ;
  C · groupé         le modèle apprend sur la source ET sur la fenêtre de la cible réunies
                     (les jours de la cible peuvent compter plusieurs fois : --poids-cible).
  + la persistance de la cible (référence sans apprentissage).

Rendre les services comparables : les taux
------------------------------------------
« 20 patients » ne veut pas dire la même chose dans un service de 20 lits et de 40 lits. Pour
B et C, toutes les grandeurs (présents, admissions, sorties) sont divisées par le nombre de lits
du service : on modélise des TAUX. La prévision est remultipliée par les lits de la cible.

Les hyperparamètres ont été choisis en NOMBRE de patients ; il faut les convertir pour qu'en
taux le modèle soit le même. Si Y = N·y (N lits) et que le modèle en nombre a pour objectif
    J_N = ½ αᵀKα + C Σ L_ε(Y − f),
en posant f = N f_r, α = N α_r et en remarquant que L_ε(N r) = N L_{ε/N}(r) (pour la perte
ε-insensible comme pour la pinball, qui sont positivement homogènes) :
    J_N = N² · [ ½ α_rᵀKα_r + (C/N) Σ L_{ε/N}(y − f_r) ].
Minimiser J_N revient donc à minimiser le même objectif en taux avec
    C_taux = C / N        et        ε_taux = ε / N
(γ ne change pas : les variables sont standardisées). N = lits de la source.

Rien du futur
-------------
En validation glissante, à chaque origine O, A n'utilise que les jours de la cible de cible ≤ O,
B et C que les jours de la source de cible ≤ O (et les jours de la cible ≤ O pour C) : au soir
du jour O, on ne connaît rien d'autre. La période de test final (le coffre) n'est lue qu'avec la
phrase de confirmation, comme dans validation_finale.py.

Total de l'hôpital
------------------
Le total des lits est la somme des services. Chaque stratégie donne une prévision par service ;
on additionne les MÉDIANES (prévisions centrales) jour par jour, la source étant prévue par son
propre modèle local. Attention : la somme des quantiles 80 % n'est pas le quantile 80 % de la
somme (les erreurs des services se compensent en partie) ; on ne note donc le total que sur
sa prévision centrale (MAE, biais), pas sur un quantile.

Exemples
--------
Développement (données verrouillées) :
    ~/memoire-env/bin/python transfert.py donnees/<export>.csv --source PED --cibles MED CHI \
        --lits PED=20 MED=24 CHI=18 --horizons 1 7
Test final, UNE fois à la fin :
    ~/memoire-env/bin/python transfert.py donnees/<export>.csv --source PED --cibles MED CHI \
        --lits PED=20 MED=24 CHI=18 --extraction 2026-10-31 \
        --confirmation "J'ouvre le coffre pour la validation finale"

Sorties dans resultats/ : transfert_<CIBLE>_h<h>.csv, transfert_total_h<h>.csv, transfert.md
(tableaux et conclusions pour le mémoire), transfert_environnement.json.
"""
import argparse
import dataclasses
from pathlib import Path

import pandas as pd
import torch

from benchmark_choix import Dimension, en_markdown
from nera.chargement import lire_export, periode_exploitable, preparer_sejours
from nera.occupation import reconstituer_occupation
from nera.verrou import DATE_VERROU
from svr import metriques as M
from svr import references as R
from svr.caracteristiques import Standardiseur, construire
from svr.niveaux import Hyperparametres, fabrique
from svr.reproductibilite import ecrire_environnement
from svr.validation import Decoupage, decoupage_final, origines_glissantes
from validation_finale import hyperparametres

TYPE = torch.float64
GRANDEURS = ("presents", "admissions")       # + toutes les colonnes sorties_*, divisées par les lits


def occupation_du_service(df: pd.DataFrame, code: str, extraction, fenetre_courte: bool) -> pd.DataFrame:
    """Occupation attendue d'un service, sur sa période exploitable (rodage au début si fenêtre courte)."""
    sejours, _ = preparer_sejours(df, code, extraction)
    if sejours.empty:
        raise ValueError(f"Aucun séjour pour le service {code}.")
    periode = periode_exploitable(sejours, rodage_au_debut=fenetre_courte)
    return reconstituer_occupation(sejours, extraction, debut=periode["debut"], scenario="attendue")


def en_taux(occ: pd.DataFrame, lits: int) -> pd.DataFrame:
    """Présents, admissions et sorties divisés par le nombre de lits : des taux comparables entre services."""
    t = occ.copy()
    for c in [*GRANDEURS, *[c for c in occ.columns if c.startswith("sorties_")]]:
        t[c] = occ[c] / lits
    return t


def hp_en_taux(hp: Hyperparametres, lits: int) -> Hyperparametres:
    """C/N et ε/N : le même modèle, exprimé en taux (démonstration dans l'en-tête)."""
    return dataclasses.replace(hp, C=hp.C / lits, epsilon=hp.epsilon / lits, epsilon_quantile=hp.epsilon_quantile / lits)


def multiplier(prevision, facteur: float):
    """Remet une prévision en nombre de patients (tenseur, ou dict {τ: tenseur})."""
    if isinstance(prevision, dict):
        return {t: v * facteur for t, v in prevision.items()}
    return prevision * facteur


def entrainer_predire(fab, X_entr, y_entr, X_pred, continues):
    """Standardisation apprise sur l'entraînement seul, puis entraînement et prévision."""
    std = Standardiseur(continues).ajuster(X_entr)
    return fab().entrainer(std.transformer(X_entr), y_entr).predire(std.transformer(X_pred))


def concatener(morceaux):
    """Recolle les prévisions des origines successives (tenseurs ou dict {τ: tenseur})."""
    if isinstance(morceaux[0], dict):
        return {t: torch.cat([m[t] for m in morceaux]) for t in morceaux[0]}
    return torch.cat(morceaux)


def main() -> None:
    p = argparse.ArgumentParser(description="Transfert de la méthode vers des services à historique court.")
    p.add_argument("export")
    p.add_argument("--source", default="PED", help="service source, à long historique (PED)")
    p.add_argument("--cibles", nargs="+", required=True, help="services cibles, à fenêtre courte")
    p.add_argument("--lits", nargs="+", required=True, help="lits de chaque service : PED=20 MED=24 …")
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 7])
    p.add_argument("--tau", type=float, default=0.8)
    p.add_argument("--niveau", type=int, default=4, choices=[1, 2, 3, 4], help="niveau de modèle transféré (4)")
    p.add_argument("--pas", type=int, default=14)
    p.add_argument("--minimum-entrainement", type=int, default=28,
                   help="jours d'entraînement de la cible au minimum avant la première origine (28)")
    p.add_argument("--poids-cible", type=int, default=1, help="stratégie C : nombre de fois où chaque jour de la cible compte (1)")
    p.add_argument("--extraction", help="test final : date du relevé du registre (aaaa-mm-jj)")
    p.add_argument("--confirmation", help="test final : phrase d'ouverture du coffre")
    a = p.parse_args()

    lits = {k: int(v) for k, v in (x.split("=") for x in a.lits)}
    manquants = [s for s in [a.source, *a.cibles] if s not in lits]
    if manquants:
        raise SystemExit(f"Nombre de lits manquant pour : {', '.join(manquants)} (option --lits).")
    final = a.confirmation is not None
    if final and not a.extraction:
        raise SystemExit("Le test final demande --extraction (date du relevé).")
    resultats = Path("resultats"); resultats.mkdir(exist_ok=True)
    ecrire_environnement(resultats / "transfert_environnement.json", **{k: v for k, v in vars(a).items() if k != "confirmation"})

    df = lire_export(a.export, confirmation_coffre=a.confirmation) if final else lire_export(a.export)
    extraction = pd.Timestamp(a.extraction) if final else DATE_VERROU
    occs = {a.source: occupation_du_service(df, a.source, extraction, fenetre_courte=False)}
    for c in a.cibles:
        occs[c] = occupation_du_service(df, c, extraction, fenetre_courte=True)
        print(f"{c} : occupation exploitable du {occs[c].index.min():%d/%m/%Y} au {occs[c].index.max():%d/%m/%Y}")
    N_s = lits[a.source]
    rapport = [f"# Transfert de la méthode — source {a.source} vers {', '.join(a.cibles)}\n",
               ("**Test final sur le coffre** (septembre–octobre 2026)." if final else
                "Validation glissante sur la fenêtre de chaque service cible (données verrouillées).")
               + f" Niveau transféré : {a.niveau}. ★ = stratégie A (locale), référence du test de Diebold-Mariano.\n"]

    for h in a.horizons:
        print(f"\n══════ Horizon J+{h}")
        chemin = resultats / f"hyperparametres_{a.source}_h{h}.json"
        if chemin.exists():
            hp = hyperparametres(chemin)[a.niveau]
        else:
            print(f"  ({chemin.name} absent : hyperparamètres par défaut — lancez d'abord lancer_niveaux.py sur {a.source})")
            hp = Hyperparametres(tau=a.tau)
        hp_taux = hp_en_taux(hp, N_s)
        tab_s = construire(en_taux(occs[a.source], N_s), h)
        totaux = {}                                              # stratégie → {service → Series par date}
        # Mêmes origines pour tous les services (indispensable pour additionner les prévisions au total) :
        # la première origine laisse `minimum_entrainement` jours à la cible qui démarre le plus tard.
        debut_val = max(occs[c].index.min() for c in a.cibles) + pd.Timedelta(days=a.minimum_entrainement + h + 7)

        for cible in a.cibles:
            N_c = lits[cible]
            tab_c = construire(occs[cible], h)                  # en nombre (stratégie A, persistance)
            tab_ct = construire(en_taux(occs[cible], N_c), h)   # en taux (stratégies B et C)
            if final:
                decs = [decoupage_final(tab_c, DATE_VERROU)]
            else:
                decs = origines_glissantes(tab_c, debut_val, DATE_VERROU, pas=a.pas, minimum_entrainement=a.minimum_entrainement)

            y = torch.cat([tab_c.y[d.evaluation] for d in decs])
            orig = torch.cat([tab_c.origines[d.evaluation] for d in decs])
            dates = pd.DatetimeIndex([dt for d in decs for dt in tab_c.dates_cible[d.evaluation.numpy()]])
            previsions = {"Persistance de la cible": R.persistance(tab_c.serie, orig, h)}
            morceaux = {"A · local (cible seule, réglages de la source gelés)": [],
                        "B · transfert direct (source seule, en taux)": [],
                        f"C · groupé (source + cible ×{a.poids_cible}, en taux)": []}
            noms = list(morceaux)
            for d in decs:
                # Jours de la source connus au soir de l'origine (cible ≤ O ; < verrou au test final).
                connus = tab_s.dates_cible < d.origine if final else tab_s.dates_cible <= d.origine
                i_s = torch.nonzero(torch.tensor(connus)).flatten()
                Xs, ys = tab_s.X[i_s], tab_s.y[i_s]
                Xc, yc = tab_ct.X[d.entrainement].repeat(a.poids_cible, 1), tab_ct.y[d.entrainement].repeat(a.poids_cible)
                morceaux[noms[0]].append(entrainer_predire(fabrique(a.niveau, hp, tab_c.blocs), tab_c.X[d.entrainement],
                                                           tab_c.y[d.entrainement], tab_c.X[d.evaluation], tab_c.continues))
                morceaux[noms[1]].append(multiplier(entrainer_predire(fabrique(a.niveau, hp_taux, tab_s.blocs), Xs, ys,
                                                                      tab_ct.X[d.evaluation], tab_s.continues), N_c))
                morceaux[noms[2]].append(multiplier(entrainer_predire(fabrique(a.niveau, hp_taux, tab_s.blocs),
                                                                      torch.cat([Xs, Xc]), torch.cat([ys, yc]),
                                                                      tab_ct.X[d.evaluation], tab_s.continues), N_c))
            for nom, m in morceaux.items():
                previsions[nom] = concatener(m)

            dim = Dimension(cible, f"Service {cible} ({N_c} lits)", "Quelle stratégie prévoit le mieux un service à historique court ?", h, a.tau)
            for nom, prev in previsions.items():
                dim.ajouter(nom, y, prev, 0.0, retenu=nom.startswith("A ·"))
                totaux.setdefault(nom, {})[cible] = pd.Series(point_de(prev).numpy(), index=dates)
            totaux.setdefault("_vrai", {})[cible] = pd.Series(y.numpy(), index=dates)
            t = dim.tableau().drop(columns=["temps (s)"])
            print(f"\n── {cible} · {len(y)} jours évalués, {len(decs)} origine(s)\n{t.to_string()}")
            t.to_csv(resultats / f"transfert_{cible}_h{h}.csv", sep=";", encoding="utf-8-sig")
            rapport.extend([f"\n## Horizon J+{h} · service {cible} ({N_c} lits, {len(y)} jours évalués)\n",
                            en_markdown(t), "\n", dim.conclusion(t), "\n"])

        # ── Total de l'hôpital : somme des prévisions centrales des services, sur les jours communs ─
        if a.source not in totaux.get("_vrai", {}):
            tab_src = construire(occs[a.source], h)
            jours_cibles = sorted(set.intersection(*(set(s.index) for s in totaux["_vrai"].values())))
            if jours_cibles:
                # La source est prévue par son propre modèle local, réentraîné aux MÊMES origines que
                # les cibles (un entraînement par origine, pas un par jour).
                decs_src = ([decoupage_final(tab_src, DATE_VERROU)] if final
                            else origines_glissantes(tab_src, debut_val, DATE_VERROU, pas=a.pas))
                prev_src = torch.cat([point_de(entrainer_predire(fabrique(a.niveau, hp, tab_src.blocs), tab_src.X[d.entrainement],
                                                                 tab_src.y[d.entrainement], tab_src.X[d.evaluation], tab_src.continues))
                                      for d in decs_src]).tolist()
                vrai_src = torch.cat([tab_src.y[d.evaluation] for d in decs_src]).tolist()
                jours_src = [dt for d in decs_src for dt in tab_src.dates_cible[d.evaluation.numpy()]]
                lignes = []
                vrai = sum(totaux["_vrai"][c].reindex(jours_cibles) for c in a.cibles) + pd.Series(vrai_src, index=jours_src).reindex(jours_cibles)
                for nom in [n for n in totaux if n != "_vrai"]:
                    prev = sum(totaux[nom][c].reindex(jours_cibles) for c in a.cibles) + pd.Series(prev_src, index=jours_src).reindex(jours_cibles)
                    ok = vrai.notna() & prev.notna()
                    yv, pv = torch.tensor(vrai[ok].to_numpy(), dtype=TYPE), torch.tensor(prev[ok].to_numpy(), dtype=TYPE)
                    lignes.append({"stratégie (services cibles)": nom, "jours": int(ok.sum()),
                                   "MAE total (lits)": round(M.mae(yv, pv), 3), "biais total": round(M.biais(yv, pv), 3)})
                tt = pd.DataFrame(lignes).set_index("stratégie (services cibles)")
                print(f"\n── Total de l'hôpital ({a.source} + {' + '.join(a.cibles)}) : {sum(lits[s] for s in [a.source, *a.cibles])} lits\n{tt.to_string()}")
                tt.to_csv(resultats / f"transfert_total_h{h}.csv", sep=";", encoding="utf-8-sig")
                rapport.extend([f"\n## Horizon J+{h} · total de l'hôpital ({a.source} + {' + '.join(a.cibles)})\n", en_markdown(tt),
                                "\nSomme des prévisions centrales (médianes) ; la source est prévue par son modèle local.\n"])

    (resultats / "transfert.md").write_text("\n".join(rapport), encoding="utf-8")
    print(f"\nTableaux écrits dans {resultats.resolve()} (transfert.md pour le mémoire)")


def point_de(prevision):
    """Prévision centrale : la médiane d'une prévision quantile, sinon la prévision elle-même."""
    return prevision[0.5] if isinstance(prevision, dict) else prevision


if __name__ == "__main__":
    main()
