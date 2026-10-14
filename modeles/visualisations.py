r"""
Toutes les figures du module lits, pour comprendre les données et les modèles (données verrouillées :
la période de test final n'est jamais lue ici).

Principe : les CALCULS sont faits par notre propre code (svr/ et nera/, écrits à la main en
PyTorch : modèles SVR, pertes, gradients, Adam, corrélations, autocorrélations…). matplotlib ne
sert qu'à DESSINER les résultats.

Prérequis : rapport_occupation.py a produit resultats/occupation_<SERVICE>.csv
(et, pour la figure 1, les séries _basse et _haute).

Exemple (dans WSL, depuis le dossier modeles) :
    ~/memoire-env/bin/python visualisations.py --service PED
    ~/memoire-env/bin/python visualisations.py --service PED --rapide        (moins d'itérations)

Figures écrites dans resultats/figures_<SERVICE>/ :
    01_serie_occupation       l'occupation jour par jour, sa fourchette, la capacité
    02_profils                occupation moyenne par jour de la semaine et par mois
    03_autocorrelation        ACF et PACF : la « mémoire » de la série
    04_correlations           matrices de corrélation de Pearson et de Spearman
    05_relations              la cible face à chaque variable importante
    06_nuage_3d               les données en 3 dimensions
    07_hyperplan_svr_3d       le SVR linéaire : un PLAN et son tube ±ε, vecteurs supports en rouge
    08_surface_svr_rbf_3d     le SVR à noyau RBF : une SURFACE courbe et l'intervalle quantile
    09_convergence            la descente de l'objectif J pendant l'entraînement (Adam)
    10_courbe_apprentissage   erreur selon le nombre de jours d'entraînement
    11_hyperparametres        erreur de validation selon C et γ (carte de chaleur)
    12_previsions             prévisions contre réalité, avec l'intervalle à 90 %
    13_residus                distribution des erreurs du modèle et de la persistance
    14_calibration            les quantiles prévus sont-ils au bon niveau ?
    15_ablation               métriques des niveaux 0 à 5 (si lancer_niveaux.py a tourné)
    16_sensibilite            gains selon la convention des jours (si sensibilite.py a tourné)
    17_importance_variables   quelles variables comptent (importance par permutation)
"""
import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                     # dessin dans des fichiers, sans fenêtre (WSL n'a pas d'écran)
import matplotlib.pyplot as plt
import pandas as pd
import torch

from lancer_niveaux import lire_occupation, etiquette, option_comptage
from nera.verrou import DATE_VERROU
from svr import analyse as A
from svr import metriques as M
from svr import references as R
from svr.caracteristiques import Standardiseur, construire
from svr.modeles import Entrainement, IntervalleQuantile, Perte, SVRLineaire, SVRNoyau, SVRNoyauComposite
from svr.noyaux import NoyauComposite, NoyauRBF
from svr.validation import decoupage_final

TYPE = torch.float64
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
MOIS = ["jan", "fév", "mar", "avr", "mai", "jun", "jul", "aoû", "sep", "oct", "nov", "déc"]
# Couleurs constantes d'une figure à l'autre : réalité en gris foncé, modèle en bleu, référence en orange.
REEL, MODELE, REFERENCE, ALERTE = "#2b2f36", "#1f5fbf", "#e07b00", "#c0392b"


def enregistrer(fig, dossier: Path, nom: str, mention: str) -> None:
    """Ajoute la mention éventuelle (ex. « données fictives ») en bas de la figure, puis l'écrit en PNG."""
    if mention:
        fig.text(0.5, 0.005, mention, ha="center", va="bottom", fontsize=9, color=ALERTE, fontweight="bold")
    fig.tight_layout(rect=(0, 0.03 if mention else 0, 1, 1))
    fig.savefig(dossier / f"{nom}.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ {nom}.png")


def main() -> None:
    p = argparse.ArgumentParser(description="Figures du module lits (données verrouillées).")
    p.add_argument("--service", required=True)
    p.add_argument("--horizon", type=int, default=1, help="horizon de prévision h en jours (1)")
    p.add_argument("--jours-validation", type=int, default=56,
                   help="nombre de jours, juste avant le verrou, gardés pour la validation des figures (56)")
    p.add_argument("--tau", type=float, default=0.8, help="quantile décisionnel (0,8)")
    p.add_argument("--rapide", action="store_true", help="moins d'itérations (figures plus vite, un peu moins précises)")
    p.add_argument("--mention", default="", help="texte ajouté sous chaque figure (ex. « DONNÉES FICTIVES »)")
    option_comptage(p)
    a = p.parse_args()
    a.service = etiquette(a.service, a.comptage)

    resultats = Path("resultats")
    dossier = resultats / f"figures_{a.service}"
    dossier.mkdir(parents=True, exist_ok=True)
    iterations = 800 if a.rapide else 2500
    entr = Entrainement(iterations=iterations)

    # ── Données ──────────────────────────────────────────────────────────────
    # La série d'occupation (scénario « attendue ») et le tableau des variables d'entrée :
    # une ligne par jour d'origine t, les 7 retards d'occupation, les flux, le calendrier, et la
    # cible = occupation du jour t + h (voir svr/caracteristiques.py).
    occ = lire_occupation(a.service)
    tab = construire(occ, a.horizon)
    noms = tab.noms
    lits = int(occ["lits"].iloc[0]) if "lits" in occ and pd.notna(occ["lits"].iloc[0]) else None

    # Découpage pour les figures : les `jours_validation` derniers jours avant le verrou servent de
    # validation ; l'entraînement n'utilise que des lignes dont la cible précède ces jours (pas de fuite).
    debut_val = tab.dates_origine[-1] - pd.Timedelta(days=a.jours_validation - 1)
    dec = decoupage_final(tab, debut_val)
    X_entr, y_entr = tab.X[dec.entrainement], tab.y[dec.entrainement]
    X_val, y_val = tab.X[dec.evaluation], tab.y[dec.evaluation]
    std = Standardiseur(tab.continues).ajuster(X_entr)          # μ, σ appris sur l'entraînement seulement
    Z_entr, Z_val = std.transformer(X_entr), std.transformer(X_val)
    print(f"Série du {occ.index.min():%d/%m/%Y} au {occ.index.max():%d/%m/%Y} (verrou {DATE_VERROU:%d/%m/%Y}) · "
          f"horizon J+{a.horizon} · {len(y_entr)} jours d'entraînement, {len(y_val)} de validation\n")

    # ── 01 · La série d'occupation et sa fourchette ──────────────────────────
    fig, ax = plt.subplots(figsize=(12, 4))
    if {"presents_basse", "presents_haute"} <= set(occ.columns):
        # Bande = encadrement exact dû aux sorties non écrites (tout inclusif / tout en nuits).
        ax.fill_between(occ.index, occ["presents_basse"], occ["presents_haute"], color=MODELE, alpha=0.18, lw=0,
                        label="Fourchette : tout inclusif – tout en nuits")
    ax.plot(occ.index, occ["presents"], color=MODELE, lw=1, label="Présents à minuit (attendu)")
    if lits:
        ax.axhline(lits, color=ALERTE, ls="--", lw=1.2, label=f"Capacité : {lits} lits")
    ax.axvspan(debut_val, occ.index.max(), color="#999", alpha=0.12, label="Validation des figures")
    ax.set_title(f"Occupation journalière — {a.service}"); ax.set_ylabel("Patients"); ax.legend(loc="upper left", fontsize=8)
    enregistrer(fig, dossier, "01_serie_occupation", a.mention)

    # ── 02 · Profils moyens : jour de la semaine et mois ─────────────────────
    y_serie = torch.tensor(occ["presents"].to_numpy(), dtype=TYPE)
    jour = torch.tensor(occ.index.dayofweek.to_numpy())          # 0 = lundi … 6 = dimanche
    mois = torch.tensor(occ.index.month.to_numpy() - 1)          # 0 = janvier … 11 = décembre
    adm = torch.tensor(occ["admissions"].to_numpy(), dtype=TYPE)
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    for ax, (groupe, etiquettes, titre) in zip(axes[:2], [(jour, JOURS, "par jour de la semaine"), (mois, MOIS, "par mois")]):
        m, s = A.moyenne_par_groupe(y_serie, groupe, len(etiquettes))
        ax.bar(range(len(etiquettes)), m.numpy(), yerr=s.numpy(), color=MODELE, alpha=0.75, capsize=3)
        ax.set_xticks(range(len(etiquettes)), etiquettes); ax.set_title(f"Occupation moyenne {titre}")
        ax.set_ylabel("Patients (moyenne ± écart-type)")
    m, s = A.moyenne_par_groupe(adm, jour, 7)
    axes[2].bar(range(7), m.numpy(), yerr=s.numpy(), color=REFERENCE, alpha=0.75, capsize=3)
    axes[2].set_xticks(range(7), JOURS); axes[2].set_title("Admissions moyennes par jour de la semaine")
    enregistrer(fig, dossier, "02_profils", a.mention)

    # ── 03 · Autocorrélation et autocorrélation partielle ────────────────────
    retard_max = 35
    rho, phi, seuil = A.acf(y_serie, retard_max), A.pacf(y_serie, retard_max), A.bande_acf(len(y_serie))
    fig, axes = plt.subplots(1, 2, figsize=(13, 3.8))
    for ax, valeurs, titre in [(axes[0], rho, "ACF : ressemblance avec il y a k jours"),
                               (axes[1], phi, "PACF : apport propre du retard k")]:
        ax.bar(range(retard_max + 1), valeurs.numpy(), color=MODELE, width=0.6)
        ax.axhspan(-seuil, seuil, color="#999", alpha=0.25, label="± 1,96/√n (bruit)")
        for k in (7, 14, 21, 28, 35):
            ax.axvline(k, color=REFERENCE, lw=0.8, ls=":")
        ax.set_title(titre); ax.set_xlabel("Retard k (jours)"); ax.legend(fontsize=8)
    enregistrer(fig, dossier, "03_autocorrelation", a.mention)

    # ── 04 · Matrices de corrélation (variables d'entrée + cible) ────────────
    gardees = [j for j in range(len(noms)) if not noms[j].startswith("cible_jour")]   # le jour de la semaine est montré en 02
    etiquettes = [noms[j] for j in gardees] + [f"cible J+{a.horizon}"]
    T = torch.cat([tab.X[:, gardees], tab.y[:, None]], dim=1)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
    for ax, Rm, titre in [(axes[0], A.matrice_pearson(T), "Pearson (relation linéaire)"),
                          (axes[1], A.matrice_spearman(T), "Spearman (relation monotone, sur les rangs)")]:
        im = ax.imshow(Rm.numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(etiquettes)), etiquettes, rotation=60, ha="right", fontsize=8)
        ax.set_yticks(range(len(etiquettes)), etiquettes, fontsize=8)
        for i in range(len(etiquettes)):                         # le nombre dans chaque case
            for j in range(len(etiquettes)):
                v = float(Rm[i, j])
                if not math.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                            color="white" if abs(v) > 0.6 else "black")
        ax.set_title(titre)
        fig.colorbar(im, ax=ax, fraction=0.046)
    enregistrer(fig, dossier, "04_correlations", a.mention)

    # ── 05 · La cible face aux variables principales ─────────────────────────
    i_occ, i_adm7, i_sor7 = noms.index("occ_j-0"), noms.index("adm_7j"), noms.index("sorties_7j")
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.8))
    for ax, j, titre in [(axes[0], i_occ, "Occupation du jour t"), (axes[1], i_adm7, "Admissions des 7 derniers jours"),
                         (axes[2], i_sor7, "Sorties des 7 derniers jours")]:
        ax.scatter(tab.X[:, j].numpy(), tab.y.numpy(), s=6, alpha=0.4, color=MODELE)
        r = float(A.matrice_pearson(torch.stack([tab.X[:, j], tab.y], dim=1))[0, 1])
        ax.set_title(f"{titre}\nr de Pearson = {r:.2f}", fontsize=10)
        ax.set_xlabel(noms[j]); ax.set_ylabel(f"Occupation J+{a.horizon}")
    jour_cible = torch.tensor(tab.dates_cible.dayofweek.to_numpy())
    m, s = A.moyenne_par_groupe(tab.y, jour_cible, 7)
    axes[3].errorbar(range(7), m.numpy(), yerr=s.numpy(), fmt="o-", color=MODELE, capsize=3)
    axes[3].set_xticks(range(7), JOURS); axes[3].set_title("Cible selon le jour de la semaine", fontsize=10)
    enregistrer(fig, dossier, "05_relations", a.mention)

    # ── 06 · Nuage de points en 3D ───────────────────────────────────────────
    fig = plt.figure(figsize=(8, 6.5))
    ax = fig.add_subplot(projection="3d")
    nuage = ax.scatter(tab.X[:, i_occ].numpy(), tab.X[:, i_adm7].numpy(), tab.y.numpy(),
                       c=jour_cible.numpy(), cmap="viridis", s=8, alpha=0.7)
    ax.set_xlabel("Occupation du jour t"); ax.set_ylabel("Admissions 7 j"); ax.set_zlabel(f"Occupation J+{a.horizon}")
    ax.set_title("Les données en 3D (couleur = jour de la semaine de la cible)")
    fig.colorbar(nuage, ax=ax, shrink=0.6, ticks=range(7)).ax.set_yticklabels(JOURS)
    enregistrer(fig, dossier, "06_nuage_3d", a.mention)

    # ── 07 · SVR LINÉAIRE en 3D : l'hyperplan et son tube ±ε ─────────────────
    # Modèle de démonstration à 2 variables (occupation du jour t, admissions 7 j), pour pouvoir
    # le dessiner : f(x) = w₁ z₁ + w₂ z₂ + b est un PLAN (un hyperplan en dimension 2).
    # Le tube = les deux plans parallèles f ± ε : les jours DANS le tube ne coûtent rien (perte
    # ε-insensible) ; les jours SUR ou HORS du tube sont les VECTEURS SUPPORTS : eux seuls
    # déterminent la position du plan (ce sont les seuls dont le gradient de la perte est non nul).
    X2_entr = X_entr[:, [i_occ, i_adm7]]
    std2 = Standardiseur([0, 1]).ajuster(X2_entr)
    epsilon = 1.0
    lin = SVRLineaire(C=1.0, perte=Perte("epsilon", epsilon), entrainement=entr).entrainer(std2.transformer(X2_entr), y_entr)
    residus = y_entr - lin.predire(std2.transformer(X2_entr))
    support = residus.abs() >= epsilon - 1e-9                  # sur le bord ou hors du tube
    g1 = torch.linspace(float(X2_entr[:, 0].min()), float(X2_entr[:, 0].max()), 30, dtype=TYPE)
    g2 = torch.linspace(float(X2_entr[:, 1].min()), float(X2_entr[:, 1].max()), 30, dtype=TYPE)
    G1, G2 = torch.meshgrid(g1, g2, indexing="ij")
    grille = torch.stack([G1.reshape(-1), G2.reshape(-1)], dim=1)
    F = lin.predire(std2.transformer(grille)).reshape(G1.shape)
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    ax.plot_surface(G1.numpy(), G2.numpy(), F.numpy(), color=MODELE, alpha=0.35)
    for signe in (+1, -1):                                     # les deux bords du tube
        ax.plot_wireframe(G1.numpy(), G2.numpy(), (F + signe * epsilon).numpy(), color=MODELE, alpha=0.25,
                          rstride=5, cstride=5, lw=0.6)
    ax.scatter(X2_entr[~support, 0].numpy(), X2_entr[~support, 1].numpy(), y_entr[~support].numpy(),
               s=8, color=REEL, alpha=0.5, label=f"dans le tube ({int((~support).sum())} jours)")
    ax.scatter(X2_entr[support, 0].numpy(), X2_entr[support, 1].numpy(), y_entr[support].numpy(),
               s=10, color=ALERTE, alpha=0.8, label=f"vecteurs supports ({int(support.sum())} jours)")
    w = lin.parametres["w"]
    ax.set_title(f"SVR linéaire : plan f = {float(w[0]):.2f}·z₁ + {float(w[1]):.2f}·z₂ + {float(lin.parametres['b'][0]):.2f}"
                 f"\ntube ±ε = ±{epsilon:g} lit", fontsize=10)
    ax.set_xlabel("Occupation du jour t"); ax.set_ylabel("Admissions 7 j"); ax.set_zlabel(f"Occupation J+{a.horizon}")
    ax.legend(loc="upper left", fontsize=8)
    enregistrer(fig, dossier, "07_hyperplan_svr_3d", a.mention)

    # ── 08 · SVR à noyau RBF en 3D : une surface courbe et l'intervalle à 90 % ─
    # Avec le noyau RBF, f(x) = Σ α_j K(x_j, x) + b n'est plus un plan : c'est un hyperplan dans
    # l'espace (de dimension infinie) où le noyau projette les données, qui redevient une SURFACE
    # COURBE dans l'espace d'origine. On dessine la médiane (τ = 0,5) et les quantiles 5 % et 95 %
    # (perte pinball) : la vraie occupation doit tomber entre les deux surfaces 9 jours sur 10.
    gamma2d = 0.5
    rbf = IntervalleQuantile(lambda tau: SVRNoyau(NoyauRBF(gamma2d), C=1.0, perte=Perte("pinball", tau=tau), entrainement=entr),
                             (0.05, 0.5, 0.95)).entrainer(std2.transformer(X2_entr), y_entr)
    Q = {t: v.reshape(G1.shape) for t, v in rbf.predire(std2.transformer(grille)).items()}
    # Loin des données, un noyau RBF ne sait rien : K(x, x_j) ≈ 0 pour tous les jours j, donc
    # f(x) ≈ b (la surface « retombe »). Dessiner ces zones vides serait trompeur : on masque
    # (NaN) chaque point de la grille dont le jour d'entraînement le plus proche est à plus de
    # 0,4 écart-type (distance calculée dans l'espace standardisé, celui que voit le noyau).
    Zg, Zd = std2.transformer(grille), std2.transformer(X2_entr)
    proche = (torch.cdist(Zg, Zd).min(dim=1).values <= 0.4).reshape(G1.shape)
    Q = {t: torch.where(proche, v, torch.tensor(float("nan"), dtype=TYPE)) for t, v in Q.items()}
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    ax.plot_surface(G1.numpy(), G2.numpy(), Q[0.5].numpy(), cmap="Blues", alpha=0.6)
    for t in (0.05, 0.95):
        ax.plot_wireframe(G1.numpy(), G2.numpy(), Q[t].numpy(), color=REFERENCE, alpha=0.35, rstride=5, cstride=5, lw=0.6)
    ax.scatter(X2_entr[:, 0].numpy(), X2_entr[:, 1].numpy(), y_entr.numpy(), s=6, color=REEL, alpha=0.4)
    ax.set_title("SVR à noyau RBF : médiane (surface) et quantiles 5 % / 95 % (grilles orange)\n"
                 "dessinés seulement là où il y a des données", fontsize=10)
    ax.set_xlabel("Occupation du jour t"); ax.set_ylabel("Admissions 7 j"); ax.set_zlabel(f"Occupation J+{a.horizon}")
    enregistrer(fig, dossier, "08_surface_svr_rbf_3d", a.mention)

    # ── 09 · Convergence de l'entraînement (toutes les variables) ────────────
    # J(t) = ½‖w‖² (ou ½αᵀKα) + C Σ perte : on trace J(t)/J(0) en échelle logarithmique.
    modeles = {
        "Niveau 1 · SVR linéaire": SVRLineaire(C=1.0, perte=Perte("epsilon", 1.0), entrainement=entr),
        "Niveau 2 · SVR RBF": SVRNoyau(NoyauRBF(0.05), C=1.0, perte=Perte("epsilon", 1.0), entrainement=entr),
        f"Niveau 3 · quantile RBF (τ = {a.tau})": SVRNoyau(NoyauRBF(0.05), C=1.0, perte=Perte("pinball", tau=a.tau), entrainement=entr),
        f"Niveau 4 · noyau composite (τ = {a.tau})": SVRNoyauComposite(
            NoyauComposite(tab.blocs["occupation"], tab.blocs["flux_saison"], 0.05, 0.1), C=1.0,
            perte=Perte("pinball", tau=a.tau), entrainement=entr),
    }
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for nom, m in modeles.items():
        m.entrainer(Z_entr, y_entr)
        h = torch.tensor(m.historique, dtype=TYPE)
        ax.plot((h / h[0]).numpy(), lw=1.2, label=f"{nom} — {m.arret}")
    ax.set_yscale("log"); ax.set_xlabel("Pas d'Adam t"); ax.set_ylabel("J(t) / J(0)")
    ax.set_title("Convergence : l'objectif J diminue pendant l'entraînement"); ax.legend(fontsize=8)
    enregistrer(fig, dossier, "09_convergence", a.mention)

    # ── 17 · Importance des variables (par permutation, svr/analyse.py) ──────
    # On reprend le SVR RBF du niveau 2 déjà entraîné ci-dessus, on « casse » un groupe de
    # variables en mélangeant ses lignes, et on mesure de combien la MAE de validation augmente.
    groupes = {"Occupation des 7 derniers jours": [j for j, n in enumerate(noms) if n.startswith("occ_")],
               "Occupation du jour t seule": [noms.index("occ_j-0")],
               "Admissions récentes (3 et 7 j)": [noms.index("adm_3j"), noms.index("adm_7j")],
               "Sorties des 7 derniers jours": [noms.index("sorties_7j")],
               "Jour de la semaine de la cible": [j for j, n in enumerate(noms) if n.startswith("cible_jour")],
               "Mois (sinus, cosinus)": [noms.index("mois_sin"), noms.index("mois_cos")]}
    imp = A.importance_permutation(modeles["Niveau 2 · SVR RBF"], Z_val, y_val, M.mae, groupes, repetitions=10)
    ordre = sorted(imp, key=lambda k: imp[k][0])
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(ordre, [imp[k][0] for k in ordre], xerr=[imp[k][1] for k in ordre], color=MODELE, alpha=0.8, capsize=3)
    ax.axvline(0, color=REEL, lw=1)
    ax.set_xlabel("Hausse de la MAE de validation quand le groupe est mélangé (lits)")
    ax.set_title("Importance des variables par permutation (niveau 2) — plus la barre est longue, plus la variable compte")
    enregistrer(fig, dossier, "17_importance_variables", a.mention)

    # ── 10 · Courbe d'apprentissage ──────────────────────────────────────────
    tailles = [t for t in (30, 60, 90, 120, 180, 240, 360, 480) if t < len(y_entr)] + [len(y_entr)]
    pinball = lambda y, q: M.pinball_moyenne(y, q, a.tau)
    courbes = {
        "Niveau 1 · linéaire (MAE)": (lambda: SVRLineaire(C=1.0, perte=Perte("epsilon", 1.0), entrainement=entr), M.mae),
        "Niveau 2 · RBF (MAE)": (lambda: SVRNoyau(NoyauRBF(0.05), C=1.0, perte=Perte("epsilon", 1.0), entrainement=entr), M.mae),
        f"Niveau 3 · quantile τ = {a.tau} (pinball)": (
            lambda: SVRNoyau(NoyauRBF(0.05), C=1.0, perte=Perte("pinball", tau=a.tau), entrainement=entr), pinball),
    }
    fig, axes = plt.subplots(1, len(courbes), figsize=(15, 4))
    for ax, (nom, (fab, err)) in zip(axes, courbes.items()):
        res = A.courbe_apprentissage(X_entr, y_entr, X_val, y_val, fab, tailles, err)
        n = [r["taille"] for r in res]
        ax.plot(n, [r["erreur_entrainement"] for r in res], "o-", color=MODELE, label="entraînement")
        ax.plot(n, [r["erreur_validation"] for r in res], "s-", color=ALERTE, label="validation")
        ax.set_xscale("log")
        ax.minorticks_off()                                    # sinon les graduations « 3×10¹ » se chevauchent
        ax.set_xticks(n, [str(v) for v in n], rotation=45)     # une étiquette lisible par taille essayée
        ax.set_xlabel("Jours d'entraînement (échelle log)"); ax.set_title(nom, fontsize=10)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Erreur (lits)")
    enregistrer(fig, dossier, "10_courbe_apprentissage", a.mention)

    # ── 11 · Sensibilité aux hyperparamètres C et γ (niveau 2) ───────────────
    Cs, gammas = [0.1, 0.3, 1.0, 3.0, 10.0], [0.01, 0.03, 0.1, 0.3, 1.0]
    carte = torch.empty(len(Cs), len(gammas), dtype=TYPE)
    for i, C in enumerate(Cs):
        for j, g in enumerate(gammas):
            m = SVRNoyau(NoyauRBF(g), C=C, perte=Perte("epsilon", 1.0), entrainement=Entrainement(iterations=iterations // 2))
            carte[i, j] = M.mae(y_val, m.entrainer(Z_entr, y_entr).predire(Z_val))
    fig, ax = plt.subplots(figsize=(6.5, 5))
    im = ax.imshow(carte.numpy(), cmap="viridis_r")
    ax.set_xticks(range(len(gammas)), [f"{g:g}" for g in gammas]); ax.set_yticks(range(len(Cs)), [f"{c:g}" for c in Cs])
    ax.set_xlabel("γ (portée du noyau RBF)"); ax.set_ylabel("C (poids des erreurs)")
    for i in range(len(Cs)):
        for j in range(len(gammas)):
            ax.text(j, i, f"{float(carte[i, j]):.2f}", ha="center", va="center", fontsize=8, color="white")
    i, j = divmod(int(torch.argmin(carte)), len(gammas))
    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, ec=ALERTE, lw=2))
    ax.set_title("MAE de validation selon C et γ (niveau 2)\ncadre rouge = meilleur couple")
    fig.colorbar(im, ax=ax, fraction=0.046)
    enregistrer(fig, dossier, "11_hyperparametres", a.mention)

    # ── 12 · Prévisions contre réalité, avec l'intervalle ────────────────────
    taus = tuple(sorted({0.05, 0.5, a.tau, 0.95}))
    niv3 = IntervalleQuantile(lambda tau: SVRNoyau(NoyauRBF(0.05), C=1.0, perte=Perte("pinball", tau=tau), entrainement=entr),
                              taus).entrainer(Z_entr, y_entr)
    q = niv3.predire(Z_val)
    persistance = R.persistance(tab.serie, tab.origines[dec.evaluation], a.horizon)
    dates = tab.dates_cible[dec.evaluation.numpy()]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.fill_between(dates, q[0.05].numpy(), q[0.95].numpy(), color=MODELE, alpha=0.18, label="Intervalle 90 % (quantiles 5 %–95 %)")
    ax.plot(dates, q[0.5].numpy(), color=MODELE, lw=1.5, label="Médiane prévue")
    ax.plot(dates, q[a.tau].numpy(), color=MODELE, lw=1, ls="--", label=f"Quantile décisionnel τ = {a.tau}")
    ax.plot(dates, persistance.numpy(), color=REFERENCE, lw=1, alpha=0.8, label="Persistance (référence)")
    ax.plot(dates, y_val.numpy(), "o-", color=REEL, ms=3, lw=1, label="Occupation réelle")
    if lits:
        ax.axhline(lits, color=ALERTE, ls="--", lw=1, label=f"{lits} lits")
    couv = M.couverture(y_val, q[0.05], q[0.95])
    ax.set_title(f"Prévisions à J+{a.horizon} sur la validation · MAE médiane {M.mae(y_val, q[0.5]):.2f} "
                 f"(persistance {M.mae(y_val, persistance):.2f}) · couverture 90 % : {100 * couv:.0f} %", fontsize=10)
    ax.set_ylabel("Patients"); ax.legend(fontsize=8, ncol=3)
    enregistrer(fig, dossier, "12_previsions", a.mention)

    # ── 13 · Distribution des erreurs ────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    e_mod, e_per = (y_val - q[0.5]), (y_val - persistance)
    bornes = torch.linspace(float(torch.min(torch.cat([e_mod, e_per]))), float(torch.max(torch.cat([e_mod, e_per]))), 25)
    axes[0].hist(e_mod.numpy(), bins=bornes.numpy(), color=MODELE, alpha=0.6, label=f"Modèle (biais {M.biais(y_val, q[0.5]):+.2f})")
    axes[0].hist(e_per.numpy(), bins=bornes.numpy(), color=REFERENCE, alpha=0.5, label=f"Persistance (biais {M.biais(y_val, persistance):+.2f})")
    axes[0].axvline(0, color=REEL, lw=1); axes[0].set_xlabel("Erreur = réel − prévu (lits)"); axes[0].legend(fontsize=8)
    axes[0].set_title("Histogramme des erreurs")
    axes[1].plot(dates, e_mod.numpy(), color=MODELE, lw=1, label="Modèle")
    axes[1].plot(dates, e_per.numpy(), color=REFERENCE, lw=1, alpha=0.8, label="Persistance")
    axes[1].axhline(0, color=REEL, lw=1); axes[1].set_title("Erreurs au fil des jours (une dérive se voit ici)")
    axes[1].legend(fontsize=8)
    enregistrer(fig, dossier, "13_residus", a.mention)

    # ── 14 · Calibration des quantiles ───────────────────────────────────────
    cal = A.calibration_quantiles(y_val, q)
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.plot([0, 1], [0, 1], color="#999", ls="--", label="Calibration parfaite")
    ax.plot(list(cal), list(cal.values()), "o-", color=MODELE, ms=7, label="Modèle (niveau 3)")
    for t, c in cal.items():
        ax.annotate(f"{100 * c:.0f} %", (t, c), textcoords="offset points", xytext=(6, -12), fontsize=8)
    ax.set_xlabel("Niveau τ demandé"); ax.set_ylabel("Part des jours où réel ≤ quantile prévu")
    ax.set_title("Calibration : au-dessus = prudent,\nen dessous = sous-estime les besoins")
    ax.legend(fontsize=8)
    enregistrer(fig, dossier, "14_calibration", a.mention)

    # ── 15 et 16 · Résultats des scripts d'ablation et de sensibilité, s'ils existent ─
    chemin = resultats / f"ablation_{a.service}_h{a.horizon}.csv"
    if chemin.exists():
        abl = pd.read_csv(chemin, sep=";", encoding="utf-8-sig", index_col="niveau")
        colonnes = [c for c in ("MAE", "RMSE") if c in abl]
        fig, ax = plt.subplots(figsize=(11, 4.5))
        abl[colonnes].plot.barh(ax=ax, color=[MODELE, REFERENCE][: len(colonnes)])
        ax.invert_yaxis(); ax.set_xlabel("Erreur (lits) — plus petit = meilleur")
        ax.set_title(f"Ablation des niveaux 0 à 5 (validation glissante), horizon J+{a.horizon}")
        enregistrer(fig, dossier, "15_ablation", a.mention)
    chemin = resultats / f"sensibilite_{a.service}.csv"
    if chemin.exists():
        sens = pd.read_csv(chemin, sep=";", encoding="utf-8-sig")
        sens = sens[sens["horizon"] == a.horizon]
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
        for ax, critere in zip(axes, ("MAE", "pinball")):
            sens.pivot(index="niveau", columns="scenario", values=f"gain_{critere}_%")[["basse", "attendue", "haute"]] \
                .plot.barh(ax=ax, color=["#8fb3e6", MODELE, "#0b2f66"])
            ax.axvline(0, color=REEL, lw=1); ax.invert_yaxis()
            ax.set_xlabel("Gain sur la persistance (%)"); ax.set_title(f"Critère {critere}")
        fig.suptitle("Sensibilité à la façon de compter les jours (tout inclusif / attendue / tout en nuits)")
        enregistrer(fig, dossier, "16_sensibilite", a.mention)

    print(f"\nFigures écrites dans {dossier.resolve()}")


if __name__ == "__main__":
    main()
