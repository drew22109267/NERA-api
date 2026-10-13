r"""
Modèles statistiques classiques, écrits à la main, pour situer le SVR face aux méthodes que
tout jury connaît : « pourquoi un SVM plutôt qu'un lissage exponentiel ou une régression ? ».

1. Lissage exponentiel de Holt-Winters additif, saison hebdomadaire (m = 7), tendance amortie
---------------------------------------------------------------------------------------------
On suit trois quantités cachées, mises à jour chaque jour t avec l'occupation observée y_t :
    niveau     l_t = α (y_t − s_{t−m}) + (1 − α)(l_{t−1} + φ b_{t−1})
    tendance   b_t = β (l_t − l_{t−1}) + (1 − β) φ b_{t−1}
    saison     s_t = γ (y_t − l_t)     + (1 − γ) s_{t−m}
Prévision faite au soir du jour t pour le jour t + h :
    ŷ_{t+h} = l_t + (φ + φ² + … + φ^h) b_t + s_{t+h−m(k+1)},   k = ⌊(h − 1)/m⌋
α, β, γ ∈ [0, 1] règlent la vitesse d'oubli (proche de 1 : on suit surtout le dernier jour) ;
φ ∈ ]0, 1] amortit la tendance (sans amortissement, une tendance prolongée sur 7 jours
dérive vite, ce qui est irréaliste pour un nombre de lits).
Initialisation sur les deux premières semaines : l = moyenne de la 1ʳᵉ semaine,
b = (moyenne de la 2ᵉ − moyenne de la 1ʳᵉ)/m, s_i = y_i − l.
La récursion n'utilise que le passé : l'état au jour t ne dépend que de y_1 … y_t, donc
aucune fuite. Les paramètres sont choisis par grille en minimisant l'erreur absolue moyenne
des prévisions à h jours sur la période d'entraînement seulement.

2. Régression ridge (moindres carrés pénalisés), solution exacte
----------------------------------------------------------------
    min_w,b  Σ_i (y_i − w·x_i − b)²  +  λ ‖w‖²
En centrant (x̃ = x − x̄, ỹ = y − ȳ), b disparaît et le gradient s'annule pour
    (X̃ᵀX̃ + λ I) w = X̃ᵀ ỹ          puis   b = ȳ − x̄·w
(dérivée : −2 X̃ᵀ(ỹ − X̃w) + 2λw = 0). On résout ce système linéaire directement.
C'est le « cousin » du SVR linéaire avec une perte carrée au lieu de la perte ε-insensible :
la comparer au niveau 1 isole l'effet de la perte.
"""
from __future__ import annotations

import itertools

import torch

TYPE = torch.float64


# ─────────────────────────────────────────────────────────────────────────────
# 1. Holt-Winters
# ─────────────────────────────────────────────────────────────────────────────
def _etats(y: list[float], alpha: float, beta: float, gamma: float, phi: float, m: int):
    """Niveau, tendance et saisons après chaque jour t (listes indexées par t ; None avant 2m − 1)."""
    n = len(y)
    niveaux, tendances = [None] * n, [None] * n
    saisons = [0.0] * n
    l = sum(y[:m]) / m
    b = (sum(y[m:2 * m]) / m - l) / m if n >= 2 * m else 0.0
    for i in range(m):
        saisons[i] = y[i] - l
    for t in range(m, n):
        l_prec, b_prec = l, b
        l = alpha * (y[t] - saisons[t - m]) + (1 - alpha) * (l_prec + phi * b_prec)
        b = beta * (l - l_prec) + (1 - beta) * phi * b_prec
        saisons[t] = gamma * (y[t] - l) + (1 - gamma) * saisons[t - m]
        niveaux[t], tendances[t] = l, b
    return niveaux, tendances, saisons


def holt_winters(serie: torch.Tensor, origines: torch.Tensor, h: int, alpha: float, beta: float,
                 gamma: float, phi: float = 0.9, m: int = 7) -> torch.Tensor:
    """Prévision de y_{t+h} faite au jour t, pour chaque origine t (persistance tant que l'état n'existe pas)."""
    y = [float(v) for v in serie]
    niveaux, tendances, saisons = _etats(y, alpha, beta, gamma, phi, m)
    k = (h - 1) // m
    amorti = sum(phi ** j for j in range(1, h + 1))           # φ + φ² + … + φ^h
    sortie = []
    for t in origines.tolist():
        if niveaux[t] is None:
            sortie.append(y[t])                                 # pas encore d'état : persistance
        else:
            sortie.append(niveaux[t] + amorti * tendances[t] + saisons[t + h - m * (k + 1)])
    return torch.tensor(sortie, dtype=TYPE)


def choisir_holt_winters(serie: torch.Tensor, h: int, fin: int, m: int = 7) -> dict:
    """
    Grille sur (α, β, γ, φ), en ne regardant que les jours d'indice < `fin` (l'entraînement) :
    critère = erreur absolue moyenne des prévisions à h jours dont la cible est avant `fin`.
    """
    origines = torch.arange(2 * m, fin - h)
    if len(origines) < 10:
        return {"alpha": 0.5, "beta": 0.05, "gamma": 0.2, "phi": 0.9}
    cibles = serie[origines + h].to(TYPE)
    meilleur, retenu = float("inf"), None
    for alpha, beta, gamma, phi in itertools.product((0.1, 0.3, 0.5, 0.7, 0.9), (0.0, 0.05, 0.15),
                                                     (0.05, 0.15, 0.3), (0.8, 0.9, 0.98)):
        erreur = float((holt_winters(serie, origines, h, alpha, beta, gamma, phi, m) - cibles).abs().mean())
        if erreur < meilleur:
            meilleur, retenu = erreur, {"alpha": alpha, "beta": beta, "gamma": gamma, "phi": phi}
    return retenu


# ─────────────────────────────────────────────────────────────────────────────
# 2. Régression ridge
# ─────────────────────────────────────────────────────────────────────────────
class RegressionRidge:
    """Même interface que les SVR (entrainer / predire) pour passer dans la validation glissante."""

    def __init__(self, lambda_: float = 1.0):
        self.lambda_ = lambda_
        self.historique: list[float] = []      # pas d'itérations : solution exacte

    def entrainer(self, X, y) -> "RegressionRidge":
        X, y = torch.as_tensor(X, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
        self.x_moyen, y_moyen = X.mean(dim=0), y.mean()
        Xc, yc = X - self.x_moyen, y - y_moyen                  # centrage : b sort du problème
        A = Xc.T @ Xc + self.lambda_ * torch.eye(X.shape[1], dtype=TYPE)
        self.w = torch.linalg.solve(A, Xc.T @ yc)               # (X̃ᵀX̃ + λI) w = X̃ᵀỹ
        self.b = y_moyen - self.x_moyen @ self.w                # b = ȳ − x̄·w
        return self

    def predire(self, X) -> torch.Tensor:
        return torch.as_tensor(X, dtype=TYPE) @ self.w + self.b
