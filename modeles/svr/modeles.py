r"""
Les modèles SVR du module lits, du plus simple au plus révisé, entraînés par gradient.

Tous minimisent la même forme de fonction de coût (le « primal » du SVR) :

    J = ½ · ‖w‖²  +  C · Σ_i L(y_i − f(x_i))
        ─────────     ────────────────────
        régularité     erreurs hors du tube (pondérées par C)

et ne diffèrent que par la forme de f (linéaire, noyau, noyau composite) et par la perte L
(ε-insensible, pinball, pinball ε-insensible — voir pertes.py).

Le gradient est calculé À LA MAIN par dérivation en chaîne. Pour un paramètre θ :
    ∂J/∂θ = ∂(régularité)/∂θ + C · Σ_i (∂L/∂f_i) · (∂f_i/∂θ)
On note g le vecteur des ∂L/∂f_i, fourni par la perte.
Chaque gradient est vérifié par différences finies dans tests/test_gradients.py.


Niveau 1 — SVR linéaire
-----------------------
    f(x) = w·x + b          (pour tous les jours : f = X w + b)
    J(w, b) = ½ w·w + C Σ L(y_i − f_i)
Dérivées :
    ∂(½ w·w)/∂w = w
    ∂f_i/∂w = x_i   et   ∂f_i/∂b = 1
    ⇒  ∂J/∂w = w + C Σ_i g_i x_i = w + C Xᵀ g
       ∂J/∂b = C Σ_i g_i


Niveaux 2 et 3 — SVR à noyau (ε-insensible ou quantile)
-------------------------------------------------------
Théorème du représentant : w = Σ_j α_j φ(x_j), où φ est la transformation implicite du noyau
(K(x, z) = φ(x)·φ(z)). Donc
    f(x) = Σ_j α_j K(x_j, x) + b           (pour l'entraînement : f = K α + b)
    ‖w‖² = Σ_j Σ_k α_j α_k K(x_j, x_k) = αᵀ K α
    J(α, b) = ½ αᵀ K α + C Σ L(y_i − f_i)
Dérivées (K est symétrique) :
    ∂(½ αᵀ K α)/∂α = K α
    ∂f_i/∂α = K[i, :]   ⇒  Σ_i g_i ∂f_i/∂α = Kᵀ g = K g
    ⇒  ∂J/∂α = K α + C K g = K (α + C g)
       ∂J/∂b = C Σ_i g_i
Option « préconditionnée » : le gradient vaut K·(α + C g). La matrice K, souvent presque
singulière, rend la descente lente dans certaines directions. En prenant comme direction
(α + C g) — le gradient « dans l'espace des fonctions », où le facteur K disparaît — chaque
pas a le même effet sur f dans toutes les directions. C'est la même solution optimale
(le gradient s'annule au même point), atteinte plus vite.


Niveau 4 — noyau composite à poids appris (brique 2)
----------------------------------------------------
    K(θ) = β K₁ + (1 − β) K₂,   β = σ(θ)
    J(α, b, θ) = ½ αᵀ K(θ) α + C Σ L(y_i − f_i),   f = K(θ) α + b
∂J/∂α et ∂J/∂b : comme au niveau 2 avec K = K(θ).
Pour θ, avec D = K₁ − K₂ et ∂K/∂θ = β(1 − β) D :
    ∂(½ αᵀ K α)/∂θ = ½ β(1 − β) αᵀ D α
    ∂f/∂θ = β(1 − β) D α          ⇒  Σ_i g_i ∂f_i/∂θ = β(1 − β) gᵀ D α
    ⇒  ∂J/∂θ = β(1 − β) · [ ½ αᵀ D α + C gᵀ D α ]
Attention (à écrire dans le mémoire) : apprendre β sur les données d'entraînement peut
favoriser le noyau qui colle le mieux à ces données. La validation glissante (validation.py)
vérifie que ce choix tient sur des jours jamais vus ; à défaut, on fixe β par validation.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import torch

from . import pertes as P
from .noyaux import NoyauComposite, sigmoide
from .optimiseurs import creer as creer_optimiseur

TYPE = torch.float64


@dataclass
class Perte:
    """Choix de la perte : 'epsilon', 'pinball' ou 'pinball_epsilon'."""
    nom: str = "epsilon"
    epsilon: float = 1.0
    tau: float = 0.5

    def __call__(self, y: torch.Tensor, f: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if self.nom == "epsilon":
            return P.epsilon_insensible(y, f, self.epsilon)
        if self.nom == "pinball":
            return P.pinball(y, f, self.tau)
        if self.nom == "pinball_epsilon":
            return P.pinball_epsilon(y, f, self.tau, self.epsilon)
        raise ValueError(f"Perte inconnue : {self.nom}")

    def niveau_initial(self, y: torch.Tensor) -> float:
        """Point de départ de b : la médiane (perte symétrique) ou le quantile τ de y."""
        q = 0.5 if self.nom == "epsilon" else self.tau
        return float(torch.quantile(y, q))


@dataclass
class Entrainement:
    """Réglages de l'optimisation."""
    optimiseur: str = "adam"
    taux: float = 0.05
    iterations: int = 3000
    decroissance: float | None = 500.0     # échelle T de η_t = η₀/√(1 + t/T)
    tolerance: float = 1e-7                # arrêt si J ne baisse plus (relativement) sur 100 pas
    preconditionne: bool = True            # direction (α + C g) pour les modèles à noyau
    afficher: int = 0                      # > 0 : affiche J, ‖∇J‖ et les paramètres tous les `afficher` pas
    moyenne_polyak: float = 0.5            # moyenne des points visités sur la fin (0 : désactivée)


class ModeleSVR:
    r"""
    Socle commun : boucle d'entraînement, meilleur point, moyenne de Polyak, historique de J.

    Pourquoi une moyenne de Polyak (Polyak & Juditsky, 1992) : avec une perte linéaire par
    morceaux, le gradient ne diminue pas près du minimum, il change brusquement de valeur ;
    les itérés θ_t oscillent autour de la solution sans s'y poser. La moyenne des itérés
        θ̄ = (1/K) Σ_{t=T₀}^{T₀+K−1} θ_t,   mise à jour en ligne : θ̄ ← θ̄ + (θ_t − θ̄)/k
    compense les oscillations de part et d'autre du minimum ; comme J est convexe,
    J(θ̄) ≤ (1/K) Σ J(θ_t) (inégalité de Jensen). On calcule la moyenne sur la fin de
    l'entraînement (à partir de la fraction `moyenne_polyak` des pas) et on garde, entre ce
    point moyen et le meilleur point rencontré, celui dont J est le plus petit.

    Arrêt anticipé. L'entraînement s'arrête dès que J ne baisse plus sur 100 pas ; cela peut
    arriver AVANT le pas où la moyenne devait commencer (le banc de comparaison l'a montré :
    arrêt au pas 272 pour un début de moyenne prévu au pas 400 → aucune moyenne). On garde donc
    toujours les FENETRE_POLYAK derniers points visités : si la moyenne de fin n'a pas pu
    commencer, on moyenne ces derniers points — justement la phase où J oscille autour du
    minimum, ce qui est le cas d'usage de Polyak.
    """

    FENETRE_POLYAK = 100

    def __init__(self, C: float = 1.0, perte: Perte | None = None, entrainement: Entrainement | None = None):
        if C <= 0:
            raise ValueError("C doit être strictement positif.")
        self.C = C
        self.perte = perte or Perte()
        self.entrainement = entrainement or Entrainement()
        self.parametres: dict[str, torch.Tensor] = {}
        self.historique: list[float] = []

    # À définir par chaque modèle
    def _initialiser(self, X: torch.Tensor, y: torch.Tensor) -> None: ...
    def objectif_et_gradients(self, y: torch.Tensor) -> tuple[float, dict[str, torch.Tensor], torch.Tensor]: ...
    def predire(self, X: torch.Tensor) -> torch.Tensor: ...

    def entrainer(self, X, y) -> "ModeleSVR":
        X, y = torch.as_tensor(X, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
        self._initialiser(X, y)
        e = self.entrainement
        opt = creer_optimiseur(e.optimiseur, taux=e.taux, decroissance=e.decroissance)
        meilleur, meilleurs_parametres = float("inf"), None
        self.historique, self.arret = [], f"{e.iterations} pas atteints"
        if e.afficher:
            print(f"Entraînement {type(self).__name__} · perte {self.perte.nom} · C = {self.C} · "
                  f"{e.optimiseur}, η₀ = {e.taux} · {X.shape[0]} exemples × {X.shape[1]} variables")
        debut_moyenne = int(e.moyenne_polyak * e.iterations) if e.moyenne_polyak else None
        moyenne, k = None, 0
        derniers = deque(maxlen=self.FENETRE_POLYAK)          # les derniers points visités (anneau)
        for t in range(e.iterations):
            J, gradients, _ = self.objectif_et_gradients(y)
            self.historique.append(J)
            # Les pertes linéaires par morceaux font osciller J : on garde le meilleur point vu.
            if J < meilleur:
                meilleur, meilleurs_parametres = J, {n: v.clone() for n, v in self.parametres.items()}
            if e.afficher and t % e.afficher == 0:
                print(self._ligne_suivi(t, J, gradients, opt))
            if t >= 100 and abs(self.historique[-100] - J) <= e.tolerance * max(1.0, abs(J)):
                self.arret = f"J stable depuis 100 pas (pas {t})"
                break
            opt.pas(self.parametres, gradients)
            if debut_moyenne is not None:
                derniers.append({n: v.clone() for n, v in self.parametres.items()})
            if debut_moyenne is not None and t >= debut_moyenne:          # θ̄ ← θ̄ + (θ_t − θ̄)/k
                k += 1
                if moyenne is None:
                    moyenne = {n: v.clone() for n, v in self.parametres.items()}
                else:
                    for n, v in self.parametres.items():
                        moyenne[n] += (v - moyenne[n]) / k
        origine = "meilleur point rencontré"
        if moyenne is None and len(derniers) >= 10:
            # Arrêt avant le début prévu de la moyenne : moyenne des derniers points visités.
            moyenne = {n: torch.stack([p[n] for p in derniers]).mean(dim=0) for n in derniers[0]}
            k = len(derniers)
        if moyenne is not None:
            self.parametres = moyenne
            J_moyen, _, _ = self.objectif_et_gradients(y)
            if J_moyen < meilleur:
                meilleur, meilleurs_parametres, origine = J_moyen, moyenne, f"moyenne de Polyak sur {k} pas"
        self.parametres = meilleurs_parametres
        self.objectif_final = meilleur
        self.origine_solution = origine                        # « meilleur point » ou « moyenne de Polyak … »
        if e.afficher:
            print(f"Fin : {self.arret} · J retenu = {meilleur:.4f} ({origine})")
        return self

    def _ligne_suivi(self, t: int, J: float, gradients: dict, opt) -> str:
        norme = float(torch.sqrt(sum((g * g).sum() for g in gradients.values())))
        p = self.parametres
        extra = f"b = {float(p['b'][0]):8.3f}"
        if "w" in p:
            extra += f" · ‖w‖ = {float(p['w'].norm()):.3f}"
        if "alpha" in p:
            extra += f" · ‖α‖ = {float(p['alpha'].norm()):.3f}"
        if "theta" in p:
            extra += f" · β = {float(sigmoide(p['theta'])):.3f}"
        return f"  pas {t:5d} · J = {J:12.4f} · ‖∇J‖ = {norme:10.4f} · η = {opt.taux():.4f} · {extra}"

    def residus_entrainement(self, y) -> torch.Tensor:
        return torch.as_tensor(y, dtype=TYPE) - self._f_entrainement()

    def nombre_vecteurs_support(self, y) -> int:
        """Jours d'entraînement sur le bord ou hors du tube (|r| ≥ ε) : ceux qui portent la solution."""
        return int((self.residus_entrainement(y).abs() >= self.perte.epsilon - 1e-9).sum()) \
            if self.perte.nom != "pinball" else int((self.residus_entrainement(y).abs() > 1e-9).sum())


class SVRLineaire(ModeleSVR):
    """Niveau 1 : f(x) = w·x + b."""

    def _initialiser(self, X, y):
        self.X = X
        self.parametres = {"w": torch.zeros(X.shape[1], dtype=TYPE),
                           "b": torch.tensor([self.perte.niveau_initial(y)], dtype=TYPE)}

    def _f_entrainement(self):
        return self.X @ self.parametres["w"] + self.parametres["b"]

    def objectif_et_gradients(self, y):
        w, f = self.parametres["w"], self._f_entrainement()
        valeurs, g = self.perte(y, f)
        J = 0.5 * float(w @ w) + self.C * float(valeurs.sum())
        gradients = {"w": w + self.C * (self.X.T @ g),            # ∂J/∂w = w + C Xᵀ g
                     "b": (self.C * g.sum()).reshape(1)}          # ∂J/∂b = C Σ g
        return J, gradients, f

    def predire(self, X):
        return torch.as_tensor(X, dtype=TYPE) @ self.parametres["w"] + self.parametres["b"]


class SVRNoyau(ModeleSVR):
    """Niveaux 2 et 3 : f(x) = Σ_j α_j K(x_j, x) + b, avec un noyau donné (RBF, linéaire…)."""

    def __init__(self, noyau, C: float = 1.0, perte: Perte | None = None, entrainement: Entrainement | None = None):
        super().__init__(C, perte, entrainement)
        self.noyau = noyau

    def _initialiser(self, X, y):
        self.X = X
        self.K = self.noyau(X, X)                                  # calculée une seule fois
        self.parametres = {"alpha": torch.zeros(X.shape[0], dtype=TYPE),
                           "b": torch.tensor([self.perte.niveau_initial(y)], dtype=TYPE)}

    def _f_entrainement(self):
        return self.K @ self.parametres["alpha"] + self.parametres["b"]

    def objectif_et_gradients(self, y):
        a, f = self.parametres["alpha"], self._f_entrainement()
        valeurs, g = self.perte(y, f)
        Ka = self.K @ a
        J = 0.5 * float(a @ Ka) + self.C * float(valeurs.sum())   # ½ αᵀKα + C Σ L
        direction = a + self.C * g
        grad_alpha = direction if self.entrainement.preconditionne else self.K @ direction   # K(α + C g)
        return J, {"alpha": grad_alpha, "b": (self.C * g.sum()).reshape(1)}, f

    def gradient_exact(self, y) -> dict[str, torch.Tensor]:
        """Le vrai gradient ∂J/∂α = K(α + C g), même en mode préconditionné (pour les tests)."""
        _, g = self.perte(y, self._f_entrainement())
        return {"alpha": self.K @ (self.parametres["alpha"] + self.C * g), "b": (self.C * g.sum()).reshape(1)}

    def predire(self, X):
        return self.noyau(torch.as_tensor(X, dtype=TYPE), self.X) @ self.parametres["alpha"] + self.parametres["b"]


class SVRNoyauComposite(SVRNoyau):
    """Niveau 4 : K = β K₁ + (1 − β) K₂ avec β = σ(θ), appris (ou fixé) en même temps que α et b."""

    def __init__(self, noyau: NoyauComposite, C: float = 1.0, perte: Perte | None = None,
                 entrainement: Entrainement | None = None, beta_initial: float = 0.5, apprendre_beta: bool = True):
        super().__init__(noyau, C, perte, entrainement)
        if not 0 < beta_initial < 1:
            raise ValueError("β initial doit être strictement entre 0 et 1.")
        self.theta_initial = torch.tensor([torch.logit(torch.tensor(beta_initial, dtype=TYPE)).item()], dtype=TYPE)
        self.apprendre_beta = apprendre_beta

    @property
    def beta(self) -> float:
        return float(sigmoide(self.parametres["theta"]))

    def _initialiser(self, X, y):
        self.X = X
        self.K1, self.K2 = self.noyau.partiels(X, X)
        self.parametres = {"alpha": torch.zeros(X.shape[0], dtype=TYPE),
                           "b": torch.tensor([self.perte.niveau_initial(y)], dtype=TYPE),
                           "theta": self.theta_initial.clone()}

    @property
    def K(self):
        return NoyauComposite.melanger(self.K1, self.K2, self.parametres["theta"])

    @K.setter
    def K(self, _):  # la matrice est recalculée à partir de θ, jamais stockée
        pass

    def objectif_et_gradients(self, y):
        J, gradients, f = super().objectif_et_gradients(y)
        a, beta = self.parametres["alpha"], self.beta
        _, g = self.perte(y, f)
        Da = (self.K1 - self.K2) @ a                               # D α
        grad_theta = beta * (1 - beta) * (0.5 * float(a @ Da) + self.C * float(g @ Da))
        gradients["theta"] = torch.tensor([grad_theta if self.apprendre_beta else 0.0], dtype=TYPE)
        return J, gradients, f

    def gradient_exact(self, y):
        _, gradients, _ = SVRNoyauComposite.objectif_et_gradients(self, y)
        gradients.update(SVRNoyau.gradient_exact(self, y))
        return gradients

    def predire(self, X):
        K1, K2 = self.noyau.partiels(torch.as_tensor(X, dtype=TYPE), self.X)
        return NoyauComposite.melanger(K1, K2, self.parametres["theta"]) @ self.parametres["alpha"] + self.parametres["b"]


@dataclass
class IntervalleQuantile:
    """
    Prévision par intervalle : un modèle par quantile (ex. τ = 0,05 ; 0,5 ; 0,95 → intervalle à 90 %).
    `fabrique(tau)` renvoie un modèle non entraîné pour ce quantile.
    Des modèles entraînés séparément peuvent « se croiser » (borne basse > médiane) ; on trie
    alors les trois valeurs de chaque jour, ce qui ne dégrade jamais la perte pinball
    (Chernozhukov et al., 2010).
    """
    fabrique: object
    taus: tuple[float, ...] = (0.05, 0.5, 0.95)
    modeles: dict = field(default_factory=dict)

    def entrainer(self, X, y) -> "IntervalleQuantile":
        self.modeles = {tau: self.fabrique(tau).entrainer(X, y) for tau in self.taus}
        return self

    def predire(self, X) -> dict[float, torch.Tensor]:
        brut = torch.stack([self.modeles[t].predire(X) for t in self.taus])
        trie, _ = torch.sort(brut, dim=0)
        return {t: trie[i] for i, t in enumerate(self.taus)}
