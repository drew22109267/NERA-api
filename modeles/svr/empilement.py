r"""
Niveau 5 — combinaison de modèles par empilement (stacking, brique 3).

Idée : plusieurs modèles (références, SVR, SVR quantile…) font chacun une prévision p_k ; un
méta-modèle apprend à les combiner :

    f = Σ_k w_k · p_k + b,     w_k = softplus(u_k) = ln(1 + e^{u_k}) > 0

Les poids sont maintenus POSITIFS par la fonction softplus : on combine des prévisions de
l'occupation, et un poids négatif n'aurait pas de sens (il « parierait contre » un modèle).

Règle indispensable : les p_k utilisées pour apprendre les poids doivent être des prévisions
HORS ÉCHANTILLON (obtenues par validation glissante), sinon le méta-modèle ferait confiance
au modèle qui a le mieux appris par cœur l'entraînement.

Fonction de coût (même perte L que le niveau visé — pinball pour un quantile) :
    J(u, b) = ½ λ Σ_k w_k²  +  C Σ_i L(y_i − f_i)
Dérivées, avec σ = sigmoïde (car softplus'(u) = σ(u)) :
    ∂w_k/∂u_k = σ(u_k)
    ∂f_i/∂u_k = σ(u_k) · p_ik         ∂f_i/∂b = 1
    ∂J/∂u_k = σ(u_k) · [ λ w_k + C Σ_i g_i p_ik ]
    ∂J/∂b   = C Σ_i g_i
Le méta-modèle n'est gardé que si la validation montre un gain par rapport au meilleur modèle
seul (analyse d'ablation, protocole 4.4).
"""
from __future__ import annotations

import torch

from .modeles import TYPE, ModeleSVR
from .noyaux import sigmoide


def softplus(u: torch.Tensor) -> torch.Tensor:
    """ln(1 + e^u), forme stable : pour u grand, ln(1 + e^u) ≈ u."""
    return torch.where(u > 20, u, torch.log1p(torch.exp(torch.clamp(u, max=20))))


class Empilement(ModeleSVR):
    """X = matrice n × m des prévisions hors échantillon des m modèles de base."""

    def __init__(self, lambda_: float = 1e-3, **options):
        super().__init__(**options)
        self.lambda_ = lambda_

    @property
    def poids(self) -> torch.Tensor:
        return softplus(self.parametres["u"])

    def _initialiser(self, X, y):
        self.X = X
        m = X.shape[1]
        # Départ : moyenne simple (w_k = 1/m), soit u_k = softplus⁻¹(1/m) = ln(e^{1/m} − 1).
        u0 = torch.log(torch.expm1(torch.tensor(1.0 / m, dtype=TYPE)))
        self.parametres = {"u": torch.full((m,), float(u0), dtype=TYPE), "b": torch.zeros(1, dtype=TYPE)}

    def _f_entrainement(self):
        return self.X @ self.poids + self.parametres["b"]

    def objectif_et_gradients(self, y):
        w, f = self.poids, self._f_entrainement()
        valeurs, g = self.perte(y, f)
        J = 0.5 * self.lambda_ * float(w @ w) + self.C * float(valeurs.sum())
        s = sigmoide(self.parametres["u"])
        grad_u = s * (self.lambda_ * w + self.C * (self.X.T @ g))
        return J, {"u": grad_u, "b": (self.C * g.sum()).reshape(1)}, f

    def predire(self, X):
        return torch.as_tensor(X, dtype=TYPE) @ self.poids + self.parametres["b"]
