r"""
Optimiseurs, écrits à la main (aucun appel à torch.optim).

Tous minimisent une fonction de coût J(θ) à partir de son gradient g = ∇J(θ), calculé
analytiquement par le modèle. Les paramètres sont rangés dans un dictionnaire
{nom: tenseur} ; chaque appel à `pas(parametres, gradients)` les met à jour sur place.

1. Descente de gradient  (SGD, ici sur tout le jeu de données à chaque pas)
    θ ← θ − η · g
   η (taux d'apprentissage) : trop grand, ça oscille ou diverge ; trop petit, c'est lent.

2. Momentum
    v ← μ · v + g
    θ ← θ − η · v
   v accumule les gradients passés (μ ≈ 0,9) : on garde l'élan dans les directions
   constantes et on amortit les oscillations — utile quand la fonction de coût est une
   « vallée » étroite, ce qui arrive avec les noyaux.

3. Adam  (Kingma & Ba, 2015)
    m ← β₁ · m + (1 − β₁) · g          moyenne mobile du gradient        (β₁ = 0,9)
    v ← β₂ · v + (1 − β₂) · g²         moyenne mobile du gradient au carré (β₂ = 0,999)
    m̂ = m / (1 − β₁ᵗ),   v̂ = v / (1 − β₂ᵗ)   correction du biais de démarrage
    θ ← θ − η · m̂ / (√v̂ + ε)
   Pourquoi la correction : m et v partent de 0, donc aux premiers pas ils sous-estiment
   le vrai gradient. Au pas t, E[m] ≈ (1 − β₁ᵗ) · E[g] ; diviser par (1 − β₁ᵗ) corrige.
   Pourquoi diviser par √v̂ : chaque paramètre reçoit son propre pas, plus petit là où le
   gradient est grand ou instable, plus grand là où il est faible et régulier.
   ε (≈ 1e−8) évite la division par zéro.
   Pour une perte linéaire par morceaux (ε-insensible, pinball), le gradient ne s'annule
   pas au voisinage du minimum : on fait donc décroître η, ce qui garantit la convergence
   (décroissance η_t = η₀ / √(1 + t/T)).
"""
from __future__ import annotations

import math

import torch


class Optimiseur:
    def __init__(self, taux: float, decroissance: float | None = None):
        if taux <= 0:
            raise ValueError("Le taux d'apprentissage doit être positif.")
        self.taux0, self.decroissance, self.t = taux, decroissance, 0

    def taux(self) -> float:
        """η_t = η₀ / √(1 + t/T) si une échelle T de décroissance est donnée, sinon η₀."""
        return self.taux0 if not self.decroissance else self.taux0 / math.sqrt(1.0 + self.t / self.decroissance)

    def pas(self, parametres: dict[str, torch.Tensor], gradients: dict[str, torch.Tensor]) -> None:
        raise NotImplementedError


class DescenteGradient(Optimiseur):
    def pas(self, parametres, gradients):
        self.t += 1
        eta = self.taux()
        for nom, p in parametres.items():
            p -= eta * gradients[nom]


class Momentum(Optimiseur):
    def __init__(self, taux: float, mu: float = 0.9, decroissance: float | None = None):
        super().__init__(taux, decroissance)
        self.mu, self.v = mu, {}

    def pas(self, parametres, gradients):
        self.t += 1
        eta = self.taux()
        for nom, p in parametres.items():
            v = self.v.setdefault(nom, torch.zeros_like(p))
            v.mul_(self.mu).add_(gradients[nom])          # v ← μ v + g
            p -= eta * v                                   # θ ← θ − η v


class Adam(Optimiseur):
    def __init__(self, taux: float = 0.01, beta1: float = 0.9, beta2: float = 0.999,
                 epsilon: float = 1e-8, decroissance: float | None = None):
        super().__init__(taux, decroissance)
        self.beta1, self.beta2, self.epsilon = beta1, beta2, epsilon
        self.m, self.v = {}, {}

    def pas(self, parametres, gradients):
        self.t += 1
        eta = self.taux()
        correction1 = 1.0 - self.beta1 ** self.t
        correction2 = 1.0 - self.beta2 ** self.t
        for nom, p in parametres.items():
            g = gradients[nom]
            m = self.m.setdefault(nom, torch.zeros_like(p))
            v = self.v.setdefault(nom, torch.zeros_like(p))
            m.mul_(self.beta1).add_((1.0 - self.beta1) * g)          # m ← β₁ m + (1 − β₁) g
            v.mul_(self.beta2).add_((1.0 - self.beta2) * g * g)      # v ← β₂ v + (1 − β₂) g²
            m_chapeau = m / correction1                               # m̂
            v_chapeau = v / correction2                               # v̂
            p -= eta * m_chapeau / (torch.sqrt(v_chapeau) + self.epsilon)


def creer(nom: str, **options) -> Optimiseur:
    """Fabrique : 'sgd', 'momentum' ou 'adam'."""
    classes = {"sgd": DescenteGradient, "momentum": Momentum, "adam": Adam}
    if nom not in classes:
        raise ValueError(f"Optimiseur inconnu : {nom}. Choix : {', '.join(classes)}.")
    return classes[nom](**options)
