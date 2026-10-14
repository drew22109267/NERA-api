"""
Rapport d'occupation d'un service à partir de l'export de l'application (données verrouillées :
rien après nera.verrou.DATE_VERROU n'est lu).

Exemple (dans WSL, depuis le dossier modeles) :
    ~/memoire-env/bin/python rapport_occupation.py donnees/dataset-hospitalisation-2026-10-03.csv \
        --service PED --lits 20

Les sorties calculées (entrée + nombre de jours) sont traitées selon la part de lignes
inclusives mesurée sur les sorties écrites (voir nera.chargement et nera.occupation) :
  attendue  la nuit incertaine compte pour 1 − p  (série de référence, utilisée par les modèles)
  basse     toutes les lignes inclusives          (borne basse de l'occupation)
  haute     toutes les lignes en nuits            (borne haute)

Produit :
  - à l'écran : convention des jours, séjours gardés/écartés, part des durées connues par mois,
    période exploitable, occupation avec sa fourchette, loi de Little, Erlang B ;
  - resultats/occupation_<SERVICE>.csv : la série jour par jour (scénario « attendue »), avec les
    colonnes presents_basse et presents_haute ;
  - resultats/occupation_<SERVICE>_basse.csv et _haute.csv : les séries complètes des deux bornes,
    pour l'analyse de sensibilité (sensibilite.py, lancer_niveaux.py --scenario) ;
  - resultats/indicateurs_<SERVICE>_par_mois.csv et _par_annee.csv : avec TOM_bas_% et TOM_haut_% ;
  - resultats/occupation_<SERVICE>.png : la courbe, sa fourchette et la capacité ;
  - resultats/flux_donnees_<SERVICE>.csv / .png : le diagramme de flux des données (lignes
    saisies → écartées, avec la raison → utilisées), à mettre dans le mémoire ;
  - resultats/reports_<SERVICE>.csv : les lignes « Ancien » suspectes d'être des patients reportés ;
  - resultats/rapport_<SERVICE>_environnement.json : versions et paramètres (reproductibilité).

Options utiles :
  --lits-fichier donnees/lits_PED.csv   capacité qui change dans le temps (colonnes date_debut;lits)
  --reports retirer                     fusionne les reports confirmés (à faire seulement quand le
                                        service a confirmé que « A » veut dire « réécrit au report »)
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pandas as pd

from nera.imputation import valider_estimation
from nera.chargement import convention_nombre_de_jours, lire_export, lire_lits, periode_exploitable, preparer_sejours
from nera.doublons import reperer_reports, retirer_reports_confirmes
from nera.garde_fous import erlang_b, comparer_erlang, verifier_little
from nera.indicateurs import indicateurs_avec_fourchette
from nera.occupation import resume_occupation, trois_scenarios
from lancer_niveaux import etiquette
from nera.verrou import DATE_VERROU
from svr.reproductibilite import ecrire_environnement


def diagramme_flux(etapes: list[tuple[str, int]], chemin_png: Path, titre: str) -> None:
    """
    Diagramme de flux vertical : une boîte par étape (séjours restants), et à droite ce qui a été
    écarté à chaque étape (la différence avec l'étape précédente). Dessiné avec matplotlib seulement.
    """
    fig, ax = plt.subplots(figsize=(9, 1.25 * len(etapes) + 0.6))
    ax.axis("off")
    for k, (texte, n) in enumerate(etapes):
        yk = len(etapes) - k
        ax.text(0.32, yk, f"{texte}\n{n} séjours", ha="center", va="center", fontsize=10,
                bbox=dict(boxstyle="round,pad=0.5", fc="#e8f0fb", ec="#1f5fbf"))
        if k:
            ax.annotate("", xy=(0.32, yk + 0.32), xytext=(0.32, yk + 0.68), arrowprops=dict(arrowstyle="->"))
            ecart = etapes[k - 1][1] - n
            if ecart:
                ax.text(0.8, yk + 0.5, f"écartés : {ecart}", ha="center", va="center", fontsize=9, color="#c0392b",
                        bbox=dict(boxstyle="round,pad=0.35", fc="#fdecea", ec="#c0392b"))
    ax.set_xlim(0, 1); ax.set_ylim(0.4, len(etapes) + 0.6)
    ax.set_title(titre, fontsize=11)
    fig.tight_layout(); fig.savefig(chemin_png, dpi=150); plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="Reconstitue l'occupation journalière d'un service.")
    p.add_argument("export", help="CSV exporté depuis l'application (registre d'hospitalisation)")
    p.add_argument("--service", required=True, help="code du service, ex. PED")
    p.add_argument("--lits", type=int, help="nombre de lits du service (capacité fixe)")
    p.add_argument("--lits-fichier", help="capacité variable : fichier date_debut;lits (remplace --lits)")
    p.add_argument("--scenarios-lits", type=int, nargs="+",
                   help="capacité incertaine : refait taux, sureffectif et Erlang B pour chaque nombre de lits (ex. 15 16 17 18 19 20)"),
    p.add_argument("--reports", choices=["garder", "retirer"], default="garder",
                   help="patients « Ancien » réécrits au report : garder (défaut, prudent) ou fusionner les reports confirmés")
    p.add_argument("--fenetre-censure", type=lambda v: v if v == "p95" else int(v), default=30,
                   help="jours avant le verrou où un séjour sans sortie est jugé encore en cours (30), ou p95")
    p.add_argument("--inconnues", choices=["exclure", "mediane", "estimee"], default="exclure",
                   help="durées inconnues : exclues (défaut), médiane du service, ou estimées par le prix puis l'issue")
    p.add_argument("--rodage-debut", action="store_true",
                   help="saisie commencée en cours de route (fenêtre courte) : écarte les premières semaines")
    p.add_argument("--comptage", choices=["minuit", "journee"], default="minuit",
                   help="minuit : nuits passées (entrée ≤ jour < sortie) ; journee : jour de sortie compris")
    p.add_argument("--seuil-duree", type=float, default=0.9,
                   help="part minimale de durées connues par mois pour reconstituer l'occupation (0,9)")
    a = p.parse_args()
    nom = etiquette(a.service, a.comptage)          # « PED » ou « PED_journee » : les deux séries coexistent

    extraction = DATE_VERROU      # pendant le développement, on « vit » au jour du verrou
    sortie = Path("resultats"); sortie.mkdir(exist_ok=True)
    ecrire_environnement(sortie / f"rapport_{nom}_environnement.json", **vars(a))
    lits = lire_lits(a.lits_fichier) if a.lits_fichier else a.lits
    print(f"Données lues jusqu'au {DATE_VERROU:%d/%m/%Y} (exclu) — la période de test final reste fermée.\n")
    df = lire_export(a.export)
    n_service = int((df["service_code"] == a.service).sum())

    # Patients reportés (même séjour écrit deux fois) : diagnostic toujours, retrait seulement sur demande.
    reports = reperer_reports(df, a.service)
    reports.to_csv(sortie / f"reports_{nom}.csv", sep=";", encoding="utf-8-sig", index=False)
    print("── Lignes « Ancien » enregistrées plus de 3 jours après l'entrée (reports possibles)")
    print("  " + (", ".join(f"{k} : {v}" for k, v in reports["classement"].value_counts().items()) or "aucune"))
    n_retires = 0
    if a.reports == "retirer":
        df, n_retires = retirer_reports_confirmes(df, reports)
        print(f"  → {n_retires} report(s) confirmé(s) fusionné(s) avec leur ligne d'origine")
    print()
    print("── Comment le registre compte-t-il les jours ? (lignes avec sortie écrite ET nombre de jours)")
    for k, v in convention_nombre_de_jours(df, a.service).items():
        if k != "par_mois":
            print(f"  {k} : {v}")
        elif len(v):
            print("  part inclusive retenue par mois d'admission (%) : "
                  + ", ".join(f"{m} {round(100 * x)}" for m, x in v.items()))
    sejours, rapport = preparer_sejours(df, a.service, extraction, a.fenetre_censure, a.inconnues)
    if a.inconnues != "exclure":
        connus = sejours[sejours["statut"].isin(["observee", "calculee"])]
        validation = valider_estimation(connus)
        validation.to_csv(sortie / f"estimation_durees_{nom}.csv", sep=";", encoding="utf-8-sig")
        print("── Estimation des durées inconnues : validation croisée sur les séjours connus")
        print(validation.to_string())
        print("  sources : " + ", ".join(f"{k} {v}" for k, v in sejours["nuits_source"].value_counts().items()))
    print("\n── Séjours\n" + str(rapport))

    periode = periode_exploitable(sejours, a.seuil_duree, rodage_au_debut=a.rodage_debut)
    print("\n── Part des séjours à durée connue, par mois d'admission (%)")
    print(periode["part_duree_connue_par_mois"].to_string())
    print(f"\nPremier mois complet : {periode['premier_mois_complet']} · rodage : {periode['rodage_jours']} j"
          f" → occupation reconstituée à partir du {periode['debut']:%d/%m/%Y}")

    occs = trois_scenarios(sejours, extraction, lits=lits, debut=periode["debut"], comptage=a.comptage)

    # Diagramme de flux : d'où viennent les séjours utilisés, et pourquoi les autres sont écartés.
    fin_sejour = sejours["sortie"].fillna(pd.Timestamp(extraction))
    exploitables = sejours["statut"] != "inconnue"
    etapes = [(f"Lignes du service {a.service} lues avant le verrou", n_service),
              ("Après fusion des patients reportés", n_service - n_retires),
              ("Après retrait des sorties antérieures à l'entrée", len(sejours)),
              ("Durée connue, calculée" + (", estimée" if a.inconnues != "exclure" else "") + ", ou encore hospitalisé", int(exploitables.sum())),
              (f"Présents pendant la période exploitable (dès le {periode['debut']:%d/%m/%Y})",
               int((exploitables & (fin_sejour > periode["debut"])).sum()))]
    if not n_retires:
        etapes.pop(1)
    pd.DataFrame(etapes, columns=["etape", "sejours"]).to_csv(sortie / f"flux_donnees_{nom}.csv",
                                                               sep=";", encoding="utf-8-sig", index=False)
    diagramme_flux(etapes, sortie / f"flux_donnees_{nom}.png", f"Flux des données — {nom}")
    print("\n── Flux des données\n" + "\n".join(f"  {e} : {n}" for e, n in etapes))
    occ = occs["attendue"]
    print("\n── Occupation — scénario attendu  [tout inclusif – tout en nuits]")
    resumes = {sc: resume_occupation(o) for sc, o in occs.items()}
    for k, v in resumes["attendue"].items():
        bornes = (f"  [{resumes['basse'][k]} – {resumes['haute'][k]}]"
                  if k not in ("jours", "jour_max") and resumes["basse"][k] != resumes["haute"][k] else "")
        print(f"  {k} : {v}{bornes}")

    print("\n── Loi de Little (L = λW), scénario attendu")
    try:
        little = verifier_little(occ, sejours, scenario="attendue", comptage=a.comptage)
        for k, v in little.items():
            print(f"  {k} : {v}")
        if lits is not None:
            # Erlang B suppose une capacité fixe : avec une capacité variable, on prend la moyenne arrondie.
            c = int(round(float(occ["lits"].mean())))
            print("\n── Erlang B" + (f" (capacité moyenne {c} lits)" if a.lits_fichier else ""))
            for k, v in comparer_erlang(occ, c, little).items():
                print(f"  {k} : {v}")
    except ValueError as e:
        print(f"  non calculée : {e}")

    # Capacité incertaine (date du passage de 15 à 20 lits inconnue, lits pas tous opérationnels) : la série des
    # présents ne dépend pas du nombre de lits ; seuls les indicateurs rapportés aux lits changent.
    if a.scenarios_lits:
        lignes = []
        for c in a.scenarios_lits:
            p_ = occ["presents"]
            lignes.append({"lits": c, "taux_occupation_%": round(100 * float(p_.mean()) / c, 1),
                           "jours_satures_%": round(100 * float((p_ >= c).mean()), 1),
                           "jours_en_sureffectif": int((p_ > c).sum()), "sureffectif_max": round(float((p_ - c).clip(lower=0).max()), 1),
                           "erlang_b_%": round(100 * erlang_b(c, float(p_.mean())), 2)})
        t = pd.DataFrame(lignes).set_index("lits")
        print("\n── Scénarios de capacité (même série de présents, nombre de lits incertain)\n" + t.to_string())
        t.to_csv(sortie / f"scenarios_lits_{nom}.csv", sep=";", encoding="utf-8-sig")

    if lits is not None:
        tableau = indicateurs_avec_fourchette(occs, sejours)
        print("\n── Indicateurs par mois (TOM = taux d'occupation moyen, entre TOM_bas et TOM_haut ; "
              "DMS = durée moyenne de séjour)")
        print(tableau[["admissions", "sorties", "journees_hospitalisation", "TOM_%", "TOM_bas_%", "TOM_haut_%",
                       "occupation_max", "jours_en_sureffectif", "DMS_nuits", "rotation_lits",
                       "intervalle_rotation_jours", "mortalite_%"]].to_string())
        tableau.to_csv(sortie / f"indicateurs_{nom}_par_mois.csv", sep=";", encoding="utf-8-sig")
        indicateurs_avec_fourchette(occs, sejours, par="Y").to_csv(
            sortie / f"indicateurs_{nom}_par_annee.csv", sep=";", encoding="utf-8-sig")
    else:
        print("\n(Indiquez --lits pour obtenir le taux d'occupation et les indicateurs par mois.)")

    complet = occ.assign(presents_basse=occs["basse"]["presents"], presents_haute=occs["haute"]["presents"])
    complet.to_csv(sortie / f"occupation_{nom}.csv", sep=";", encoding="utf-8-sig")
    for sc in ("basse", "haute"):
        occs[sc].to_csv(sortie / f"occupation_{nom}_{sc}.csv", sep=";", encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(occ.index, occs["basse"]["presents"], occs["haute"]["presents"], alpha=0.25, lw=0,
                    label="Fourchette : tout inclusif – tout en nuits")
    ax.plot(occ.index, occ["presents"], lw=1, label="Patients présents à minuit (attendu)")
    if lits is not None:
        ax.step(occ.index, occ["lits"], where="post", color="crimson", ls="--", lw=1, label="Capacité (lits)")
    ax.set_ylabel("Patients"); ax.set_title(f"Occupation journalière — {nom}"); ax.legend()
    fig.tight_layout(); fig.savefig(sortie / f"occupation_{nom}.png", dpi=150)
    print(f"\nSéries et graphique écrits dans {sortie.resolve()}")


if __name__ == "__main__":
    main()
