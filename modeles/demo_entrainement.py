"""
Voir un entraînement se dérouler, pas à pas : J, norme du gradient, taux d'apprentissage,
paramètres (b, ‖w‖ ou ‖α‖, β du noyau composite), puis la courbe de J et les prévisions.

1. Sur l'exercice de la leçon (3 jours, aucune donnée à préparer) :
    ~/memoire-env/bin/python demo_entrainement.py --exercice

2. Sur un service (après rapport_occupation.py), pour un niveau et un horizon :
    ~/memoire-env/bin/python demo_entrainement.py --service PED --niveau 3 --horizon 1
   Le modèle apprend sur tout ce qui précède les 4 dernières semaines avant le verrou, puis
   prévoit ces 4 semaines (jamais le coffre). Graphique : resultats/demo_<service>_niveau<n>.png
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import torch

from lancer_niveaux import lire_occupation, mesures
from nera.verrou import DATE_VERROU
from svr.caracteristiques import Standardiseur, construire
from svr.modeles import Entrainement, Perte, SVRLineaire
from svr.niveaux import Hyperparametres, fabrique
from svr.validation import Decoupage


def exercice() -> None:
    print("Exercice de la leçon : x = occupation de la veille, y = occupation du jour.")
    X = torch.tensor([[10.0], [12.0], [11.0]], dtype=torch.float64)
    y = torch.tensor([12.0, 11.0, 15.0], dtype=torch.float64)
    # Comme dans la vraie chaîne, x est standardisé : z = (x − μ)/σ. Sans cela, x ≈ 11 rend w et b
    # presque interchangeables (vallée étroite) et la descente est très lente.
    std = Standardiseur([0]).ajuster(X)
    Z = std.transformer(X)
    print(f"x standardisé : z = (x − {float(std.moyenne[0]):.2f}) / {float(std.ecart[0]):.4f}\n")
    m = SVRLineaire(C=1.0, perte=Perte("epsilon", 1.0),
                    entrainement=Entrainement(taux=0.05, iterations=3000, afficher=250))
    m.entrainer(Z, y)
    w, b = float(m.parametres["w"][0]), float(m.parametres["b"][0])

    # Vérification indépendante : minimum de J sur une grille fine, dans le même repère (w, b).
    gw = torch.linspace(-4, 4, 1601, dtype=torch.float64)[:, None, None]
    gb = torch.linspace(5, 20, 1501, dtype=torch.float64)[None, :, None]
    Jg = 0.5 * gw[..., 0] ** 2 + torch.clamp((y - (gw * Z[:, 0] + gb)).abs() - 1, min=0).sum(-1)
    i = int(torch.argmin(Jg))
    print(f"\nModèle appris : f(z) = {w:.3f}·z + {b:.3f}  →  J = {m.objectif_final:.4f}")
    print(f"Contrôle par grille (précision limitée par le pas de la grille) : J = {float(Jg.flatten()[i]):.4f} pour w = {float(gw.flatten()[i // 1501]):.3f}, "
          f"b = {float(gb.flatten()[i % 1501]):.3f}")
    for xi, zi, yi in zip(X[:, 0].tolist(), Z[:, 0].tolist(), y.tolist()):
        f = w * zi + b
        r = abs(yi - f)
        position = ("dans le tube" if r < 0.99 else "sur le bord du tube : vecteur de support" if r <= 1.01
                    else "hors du tube : vecteur de support")
        print(f"  x = {xi:4.0f} → f = {f:6.2f} · réel {yi:4.0f} · résidu {yi - f:+6.2f} ({position})")
    tracer_J(m.historique, Path("resultats") / "demo_exercice_J.png", "Exercice de la leçon")


def service(nom: str, niveau: int, h: int) -> None:
    tab = construire(lire_occupation(nom), h)
    debut_eval = DATE_VERROU - pd.Timedelta(days=28)
    entr = torch.nonzero(torch.tensor(tab.dates_cible < debut_eval)).flatten()
    ev = torch.nonzero(torch.tensor(tab.dates_origine >= debut_eval)).flatten()
    dec = Decoupage(entr, ev, debut_eval)
    hp = Hyperparametres()
    hp.entrainement.afficher = 250
    std = Standardiseur(tab.continues).ajuster(tab.X[dec.entrainement])
    modele = fabrique(niveau, hp, tab.blocs)()
    print(f"Niveau {niveau} · horizon J+{h} · apprentissage jusqu'au {debut_eval:%d/%m/%Y}, "
          f"prévision des 4 semaines suivantes (avant le verrou)\n")
    modele.entrainer(std.transformer(tab.X[dec.entrainement]), tab.y[dec.entrainement])
    prev = modele.predire(std.transformer(tab.X[dec.evaluation]))
    y = tab.y[dec.evaluation]
    print("\nMesures sur les 4 semaines :")
    for k, v in mesures(y, prev, hp.tau).items():
        print(f"  {k} : {v}")

    sortie = Path("resultats"); sortie.mkdir(exist_ok=True)
    dates = tab.dates_cible[dec.evaluation.numpy()]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(dates, y, "k.-", label="Occupation réelle")
    if isinstance(prev, dict):
        taus = sorted(prev)
        ax.fill_between(dates, prev[taus[0]], prev[taus[-1]], alpha=0.25, label=f"Intervalle {taus[0]}–{taus[-1]}")
        ax.plot(dates, prev[0.5], label="Médiane prévue")
        ax.plot(dates, prev[hp.tau], "--", label=f"Quantile décisionnel τ = {hp.tau}")
    else:
        ax.plot(dates, prev, label="Prévision")
    ax.set_title(f"{nom} · niveau {niveau} · J+{h}"); ax.legend(); fig.tight_layout()
    fig.savefig(sortie / f"demo_{nom}_niveau{niveau}.png", dpi=150)
    modeles = modele.modeles.values() if hasattr(modele, "modeles") else [modele]
    tracer_J(next(iter(modeles)).historique, sortie / f"demo_{nom}_niveau{niveau}_J.png", f"{nom} · niveau {niveau}")
    print(f"\nGraphiques écrits dans {sortie.resolve()}")


def tracer_J(historique, chemin: Path, titre: str) -> None:
    chemin.parent.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(historique); ax.set_xlabel("pas"); ax.set_ylabel("J"); ax.set_yscale("log")
    ax.set_title(f"Fonction de coût pendant l'entraînement — {titre}"); fig.tight_layout(); fig.savefig(chemin, dpi=150)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Démonstration d'un entraînement, pas à pas.")
    p.add_argument("--exercice", action="store_true")
    p.add_argument("--service")
    p.add_argument("--niveau", type=int, default=3, choices=[1, 2, 3, 4])
    p.add_argument("--horizon", type=int, default=1)
    a = p.parse_args()
    exercice() if a.exercice else service(a.service, a.niveau, a.horizon)
