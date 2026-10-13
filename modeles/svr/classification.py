r"""
SVM de CLASSIFICATION à coûts asymétriques, et sa transformation en probabilités (Platt),
écrits à la main. Sert au modèle de survie (probabilité de sortie un jour donné) et servira
au module triage.

1. SVM linéaire à coûts par exemple (brique 1 du SVM révisé : coûts asymétriques C+ / C−)
------------------------------------------------------------------------------------------
Étiquettes y_i ∈ {−1, +1}, score f(x) = w·x + b. Objectif (« primal », perte hinge) :
    J(w, b) = ½ ‖w‖² + Σ_i C_i · max(0, 1 − y_i f(x_i))
C_i est le poids de l'exemple i : C+ pour les exemples positifs, C− pour les négatifs, multiplié
par un éventuel poids de l'exemple (par exemple la probabilité qu'une sortie ait eu lieu ce
jour-là quand la date n'est pas écrite). Avec C+ > C−, rater un positif coûte plus cher : la
frontière se déplace pour en manquer moins. Choix usuel pour des classes déséquilibrées :
    C+ / C− = n− / n+   (chaque classe pèse autant au total).
Dérivées (sous-gradient de la hinge : −y_i quand la marge y_i f_i < 1, 0 sinon) :
    ∂J/∂w = w − Σ_i C_i y_i x_i · 1{y_i f_i < 1}
    ∂J/∂b =   − Σ_i C_i y_i     · 1{y_i f_i < 1}

2. Probabilités de Platt (1999)
-------------------------------
Le score f d'un SVM n'est pas une probabilité. Platt ajuste une sigmoïde :
    P(y = 1 | f) = 1 / (1 + exp(A f + B))
en minimisant la log-vraisemblance (pondérée) sur des données NON utilisées pour entraîner le
SVM (sinon les scores sont trop confiants). Cibles adoucies de Platt pour éviter le surajustement :
    t+ = (N+ + 1)/(N+ + 2),   t− = 1/(N− + 2).
Avec z = A f + B et p = 1/(1 + e^z), la perte  L = −Σ w_i [t_i ln p_i + (1 − t_i) ln(1 − p_i)]
a pour dérivées (car dp/dz = −p(1 − p)) :
    ∂L/∂z_i = w_i (t_i − p_i)   ⇒   ∂L/∂A = Σ w_i (t_i − p_i) f_i,   ∂L/∂B = Σ w_i (t_i − p_i)

3. Mesures pour des probabilités (toutes pondérées par w_i)
-----------------------------------------------------------
  score de Brier   (1/Σw) Σ w_i (p_i − y_i)²       0 = parfait ; erreur quadratique des probabilités
  log-loss         −(1/Σw) Σ w_i [y ln p + (1−y) ln(1−p)]
  AUC              probabilité qu'un exemple positif ait un score plus élevé qu'un négatif
                   (statistique de Mann-Whitney ; 0,5 = hasard, 1 = séparation parfaite).
                   Calcul en O(n log n) : on trie les scores et, pour chaque positif, on compte
                   le poids des négatifs de score plus bas (ex æquo comptés pour moitié).
"""
from __future__ import annotations

import torch

from .modeles import TYPE, Entrainement, ModeleSVR
from .optimiseurs import creer as creer_optimiseur


class SVMLineaireClassifieur(ModeleSVR):
    """SVM linéaire, perte hinge, un coût C_i par exemple (asymétrie C+ / C− et poids)."""

    def __init__(self, C_positif: float = 1.0, C_negatif: float = 1.0, entrainement: Entrainement | None = None):
        super().__init__(C=1.0, entrainement=entrainement)
        if C_positif <= 0 or C_negatif <= 0:
            raise ValueError("C+ et C− doivent être strictement positifs.")
        self.C_positif, self.C_negatif = C_positif, C_negatif
        self.poids = None

    def entrainer(self, X, y, poids=None) -> "SVMLineaireClassifieur":
        """y ∈ {0, 1} ou {−1, +1} ; poids optionnel par exemple (1 par défaut)."""
        y = torch.as_tensor(y, dtype=TYPE)
        y = torch.where(y > 0, 1.0, -1.0).to(TYPE)
        self.poids = torch.ones_like(y) if poids is None else torch.as_tensor(poids, dtype=TYPE)
        self.C_exemple = self.poids * torch.where(y > 0, self.C_positif, self.C_negatif).to(TYPE)
        return super().entrainer(X, y)

    def _initialiser(self, X, y):
        self.X = X
        self.parametres = {"w": torch.zeros(X.shape[1], dtype=TYPE), "b": torch.zeros(1, dtype=TYPE)}

    def _f_entrainement(self):
        return self.X @ self.parametres["w"] + self.parametres["b"]

    def objectif_et_gradients(self, y):
        w, f = self.parametres["w"], self._f_entrainement()
        marge = y * f
        actif = (marge < 1).to(TYPE)                                   # exemples dans la marge ou mal classés
        J = 0.5 * float(w @ w) + float((self.C_exemple * (1 - marge).clamp(min=0)).sum())
        coef = self.C_exemple * y * actif                              # C_i y_i 1{y_i f_i < 1}
        return J, {"w": w - self.X.T @ coef, "b": (-coef.sum()).reshape(1)}, f

    def predire(self, X):
        """Score (distance signée à l'hyperplan, au facteur ‖w‖ près) : > 0 → classe positive."""
        return torch.as_tensor(X, dtype=TYPE) @ self.parametres["w"] + self.parametres["b"]


class CalibrationPlatt:
    """Transforme un score en probabilité : P = 1/(1 + exp(A·score + B)), A et B appris par Adam."""

    def __init__(self, iterations: int = 3000, taux: float = 0.05):
        self.iterations, self.taux = iterations, taux

    def ajuster(self, scores, y, poids=None) -> "CalibrationPlatt":
        s = torch.as_tensor(scores, dtype=TYPE)
        y = (torch.as_tensor(y, dtype=TYPE) > 0).to(TYPE)
        w = torch.ones_like(s) if poids is None else torch.as_tensor(poids, dtype=TYPE)
        n_pos, n_neg = float((w * y).sum()), float((w * (1 - y)).sum())
        t = torch.where(y > 0, (n_pos + 1) / (n_pos + 2), 1 / (n_neg + 2)).to(TYPE)   # cibles adoucies
        # Départ de Platt : A = 0, B = ln((N− + 1)/(N+ + 1)) (probabilité = fréquence des positifs).
        param = {"A": torch.zeros(1, dtype=TYPE), "B": torch.tensor([float(torch.log(torch.tensor((n_neg + 1) / (n_pos + 1))))], dtype=TYPE)}
        opt = creer_optimiseur("adam", taux=self.taux, decroissance=500.0)
        for _ in range(self.iterations):
            p = 1 / (1 + torch.exp(param["A"] * s + param["B"]))
            r = w * (t - p) / float(w.sum())                            # ∂L/∂z_i (moyenne pondérée)
            opt.pas(param, {"A": (r * s).sum().reshape(1), "B": r.sum().reshape(1)})
        self.A, self.B = float(param["A"]), float(param["B"])
        return self

    def probabilite(self, scores) -> torch.Tensor:
        return 1 / (1 + torch.exp(self.A * torch.as_tensor(scores, dtype=TYPE) + self.B))


def brier(p, y, poids=None) -> float:
    p, y = torch.as_tensor(p, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
    w = torch.ones_like(p) if poids is None else torch.as_tensor(poids, dtype=TYPE)
    return float((w * (p - y) ** 2).sum() / w.sum())


def log_loss(p, y, poids=None, eps: float = 1e-12) -> float:
    p = torch.as_tensor(p, dtype=TYPE).clamp(eps, 1 - eps)
    y = torch.as_tensor(y, dtype=TYPE)
    w = torch.ones_like(p) if poids is None else torch.as_tensor(poids, dtype=TYPE)
    return float(-(w * (y * torch.log(p) + (1 - y) * torch.log(1 - p))).sum() / w.sum())


def auc(scores, y, poids=None) -> float:
    """AUC pondérée (Mann-Whitney), en triant les scores une seule fois."""
    s, y = torch.as_tensor(scores, dtype=TYPE), torch.as_tensor(y, dtype=TYPE) > 0
    w = torch.ones_like(s) if poids is None else torch.as_tensor(poids, dtype=TYPE)
    ordre = torch.argsort(s)
    s, y, w = s[ordre], y[ordre], w[ordre]
    total_pos, total_neg = float(w[y].sum()), float(w[~y].sum())
    if total_pos == 0 or total_neg == 0:
        return float("nan")
    gagnes, neg_avant, i, n = 0.0, 0.0, 0, len(s)
    while i < n:                                                       # paquets de scores égaux
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        pos_paquet, neg_paquet = float(w[i:j + 1][y[i:j + 1]].sum()), float(w[i:j + 1][~y[i:j + 1]].sum())
        gagnes += pos_paquet * (neg_avant + 0.5 * neg_paquet)          # négatifs plus bas + moitié des ex æquo
        neg_avant += neg_paquet
        i = j + 1
    return gagnes / (total_pos * total_neg)
