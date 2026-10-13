r"""
Noyaux, écrits à la main.

Idée
----
Un modèle linéaire f(x) = w·x + b ne peut suivre que des relations droites. L'astuce du noyau
remplace le produit scalaire x·z par une fonction K(x, z) qui mesure la RESSEMBLANCE de deux
situations (deux jours). Le théorème du représentant dit alors que la meilleure fonction
s'écrit comme une combinaison des jours d'entraînement :

    f(x) = Σ_j α_j K(x_j, x) + b

Chaque jour d'entraînement x_j « vote » pour la prévision, avec un poids α_j, d'autant plus
fort que la situation x lui ressemble. Les jours avec α_j ≠ 0 sont les vecteurs de support.

Noyaux disponibles
------------------
Linéaire :   K(x, z) = x · z                      (retrouve le modèle linéaire)
RBF :        K(x, z) = exp(−γ ‖x − z‖²)           (gaussien)
    K = 1 si x = z, et décroît vers 0 quand les situations s'éloignent.
    γ règle la portée : γ grand → seuls les jours très semblables comptent (modèle très souple,
    risque de surapprentissage) ; γ petit → beaucoup de jours comptent (modèle lisse).
    Calcul de la distance sans boucle :  ‖x − z‖² = ‖x‖² + ‖z‖² − 2 x·z
    (une petite valeur négative due aux arrondis est ramenée à 0).

Noyau composite  (brique 2 du SVM révisé, MKL)
---------------------------------------------
On découpe les variables en deux BLOCS (ex. occupation passée / admissions récentes et
saison) et on mélange deux noyaux, chacun calculé sur son bloc :

    K(x, z) = β · K₁(x⁽¹⁾, z⁽¹⁾) + (1 − β) · K₂(x⁽²⁾, z⁽²⁾),   β = σ(θ) = 1 / (1 + e^{−θ})

β ∈ ]0, 1[ dit quelle source d'information compte le plus. Écrire β = σ(θ) garantit qu'il
reste entre 0 et 1 quelle que soit la valeur de θ, et permet de l'APPRENDRE par gradient.
Une somme pondérée positive de noyaux valides est encore un noyau valide (matrice
semi-définie positive), donc toute la théorie du SVR s'applique.
Dérivée utile :  ∂K/∂θ = σ'(θ)·(K₁ − K₂) = β(1 − β)·(K₁ − K₂).
"""
from __future__ import annotations

from dataclasses import dataclass

import torch


def lineaire(X: torch.Tensor, Z: torch.Tensor) -> torch.Tensor:
    """Matrice K[i, j] = X[i] · Z[j]."""
    return X @ Z.T


def distances_carrees(X: torch.Tensor, Z: torch.Tensor) -> torch.Tensor:
    """Matrice D[i, j] = ‖X[i] − Z[j]‖² = ‖X[i]‖² + ‖Z[j]‖² − 2 X[i]·Z[j], sans boucle."""
    nx = (X * X).sum(dim=1, keepdim=True)          # colonne n×1
    nz = (Z * Z).sum(dim=1, keepdim=True).T        # ligne 1×m
    return torch.clamp(nx + nz - 2.0 * (X @ Z.T), min=0.0)


def rbf(X: torch.Tensor, Z: torch.Tensor, gamma: float) -> torch.Tensor:
    """Matrice K[i, j] = exp(−γ ‖X[i] − Z[j]‖²)."""
    if gamma <= 0:
        raise ValueError("γ doit être strictement positif.")
    return torch.exp(-gamma * distances_carrees(X, Z))


def sigmoide(theta: torch.Tensor) -> torch.Tensor:
    """σ(θ) = 1 / (1 + e^{−θ}), écrite à la main (forme stable pour θ très négatif)."""
    return torch.where(theta >= 0, 1.0 / (1.0 + torch.exp(-theta)), torch.exp(theta) / (1.0 + torch.exp(theta)))


@dataclass
class NoyauRBF:
    gamma: float

    def __call__(self, X: torch.Tensor, Z: torch.Tensor) -> torch.Tensor:
        return rbf(X, Z, self.gamma)


@dataclass
class NoyauLineaire:
    def __call__(self, X: torch.Tensor, Z: torch.Tensor) -> torch.Tensor:
        return lineaire(X, Z)


@dataclass
class NoyauComposite:
    """
    K = β·RBF(γ₁) sur les colonnes `bloc1` + (1 − β)·RBF(γ₂) sur les colonnes `bloc2`.
    Les deux matrices partielles sont renvoyées séparément pour calculer ∂K/∂θ.
    """
    bloc1: list[int]
    bloc2: list[int]
    gamma1: float
    gamma2: float

    def partiels(self, X: torch.Tensor, Z: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return rbf(X[:, self.bloc1], Z[:, self.bloc1], self.gamma1), rbf(X[:, self.bloc2], Z[:, self.bloc2], self.gamma2)

    @staticmethod
    def melanger(K1: torch.Tensor, K2: torch.Tensor, theta: torch.Tensor) -> torch.Tensor:
        beta = sigmoide(theta)
        return beta * K1 + (1.0 - beta) * K2
