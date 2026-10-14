r"""
Modèles concurrents du SVR, écrits à la main (aucune bibliothèque d'apprentissage) :

    A. Forêt aléatoire quantile      (Breiman, 2001 ; Meinshausen, 2006)
    B. Gradient boosting quantile    (Friedman, 2001)
    C. Perceptron multicouche (MLP)  quantile, rétropropagation écrite à la main
    D. LSTM                          quantile, rétropropagation dans le temps écrite à la main

Règle d'équité de la comparaison (à écrire dans le mémoire) : chaque concurrent reçoit EXACTEMENT
le même tableau de variables que le SVR (svr/caracteristiques.py : 7 jours d'occupation passée,
flux d'admissions et de sorties, calendrier), la même standardisation apprise sur l'entraînement,
la même validation glissante (svr/validation.py) et produit les mêmes quantiles τ (5 %, 50 %, τ
décisionnel, 95 %). Seule la FORME de la fonction f change. Un écart de précision s'attribue donc
au modèle, pas aux données.

Interface commune (celle de svr/validation.evaluer) :
    modele.entrainer(X, y) -> modele        X : n × p (standardisé), y : n
    modele.predire(X)      -> {τ: tenseur}  quantiles triés (pas de croisement)


A. Arbre de régression (CART) — la brique des méthodes A et B
-------------------------------------------------------------
Un arbre découpe l'espace des variables en rectangles et prédit une constante par rectangle.
À chaque nœud, on cherche la variable j et le seuil s qui minimisent la somme des carrés
    SCE(j, s) = Σ_{x_ij ≤ s} (r_i − r̄_G)² + Σ_{x_ij > s} (r_i − r̄_D)²,
c'est-à-dire qui maximisent le GAIN = SCE(nœud) − SCE(j, s).
Calcul en une passe par variable (sans boucle sur les seuils) : on trie x_j, on cumule
    S_k = Σ_{i≤k} r_(i),  Q_k = Σ_{i≤k} r_(i)²
et SCE_gauche(k) = Q_k − S_k²/k, SCE_droite(k) = (Q_n − Q_k) − (S_n − S_k)²/(n − k).
Les seuils candidats sont les milieux entre deux valeurs distinctes consécutives ; chaque
feuille garde au moins `min_feuille` exemples (évite les feuilles d'un seul jour).

A. Forêt aléatoire quantile (Meinshausen, 2006)
-----------------------------------------------
B arbres, chacun appris sur un échantillon bootstrap (tirage avec remise de n jours) et,
à chaque nœud, sur m = ⌈p/3⌉ variables tirées au hasard : les arbres deviennent différents,
leurs erreurs se compensent quand on les moyenne (réduction de variance du « bagging »).
Prévision quantile : chaque arbre dépose le nouveau jour x dans une feuille F_b(x) ; le poids du
jour d'entraînement i est
    w_i(x) = (1/B) Σ_b 𝟙(x_i ∈ F_b(x)) / |F_b(x)|          (Σ_i w_i = 1)
et le quantile τ est le plus petit y tel que Σ_{y_i ≤ y} w_i(x) ≥ τ.
La forêt ne fait AUCUNE hypothèse sur la forme de la loi : elle estime la loi conditionnelle
entière, d'où tous les quantiles avec une seule forêt.

B. Gradient boosting quantile (Friedman, 2001)
----------------------------------------------
On construit F_M(x) = F_0 + ν Σ_{m=1..M} h_m(x) par descente de gradient dans l'espace des fonctions :
    F_0 = quantile τ de y ;
    à l'étape m :  résidus r_i = y_i − F_{m−1}(x_i),
                   pseudo-résidus  g_i = −∂ρ_τ(r_i)/∂F = τ si r_i > 0, τ − 1 sinon ;
                   un petit arbre h_m (profondeur 3) apprend g sur un sous-échantillon de 80 % ;
                   la valeur de chaque feuille est REMPLACÉE par le quantile τ des résidus r_i
                   de la feuille : c'est le pas optimal argmin_γ Σ_{i ∈ feuille} ρ_τ(r_i − γ) ;
                   F_m = F_{m−1} + ν h_m  (ν = taux d'apprentissage, « shrinkage »).
Un modèle par quantile.

C. Perceptron multicouche quantile
----------------------------------
    z₁ = X W₁ + b₁,  a₁ = ReLU(z₁) ;  z₂ = a₁ W₂ + b₂,  a₂ = ReLU(z₂) ;  F = a₂ W₃ + b₃   (une sortie par τ)
    J = (1/n) Σ_i Σ_q ρ_{τ_q}(y_i − F_iq) + (λ/2)(‖W₁‖² + ‖W₂‖² + ‖W₃‖²)
Rétropropagation (règle de la chaîne, couche par couche) :
    G = ∂J/∂F = (1/n) ρ'_τ   avec ρ'_τ(r) = −τ si r > 0, 1 − τ si r < 0
    ∂J/∂W₃ = a₂ᵀ G + λW₃            ∂J/∂b₃ = Σ_i G_i
    δ₂ = (G W₃ᵀ) ⊙ 𝟙(z₂ > 0)        ∂J/∂W₂ = a₁ᵀ δ₂ + λW₂     ∂J/∂b₂ = Σ_i δ₂,i
    δ₁ = (δ₂ W₂ᵀ) ⊙ 𝟙(z₁ > 0)       ∂J/∂W₁ = Xᵀ δ₁ + λW₁      ∂J/∂b₁ = Σ_i δ₁,i
Initialisation de He (W ~ N(0, 2/entrées)), optimiseur Adam (svr/optimiseurs.py), arrêt anticipé
sur les 15 % derniers jours de l'entraînement (validation interne CHRONOLOGIQUE), moyenne de
plusieurs initialisations (graines) pour réduire la variance due au hasard de l'initialisation.

D. LSTM quantile (Hochreiter et Schmidhuber, 1997)
--------------------------------------------------
La séquence d'entrée est l'occupation des L derniers jours (du plus ancien au plus récent) ;
les autres variables (flux, calendrier) rejoignent l'état final. Pour chaque jour k :
    z_k = x_k W_x + h_{k−1} W_h + b         (4H valeurs : portes i, f, o et candidat g)
    i = σ(z_i)  f = σ(z_f)  o = σ(z_o)  g = tanh(z_g)
    c_k = f ⊙ c_{k−1} + i ⊙ g ;   h_k = o ⊙ tanh(c_k)
    F = [h_L, e] W_s + b_s                  (une sortie par τ)
Rétropropagation dans le temps (de k = L à 1), avec dh_L = G W_s[:H]ᵀ et dc = 0 au départ :
    do = dh ⊙ tanh(c_k)                     dc ← dc + dh ⊙ o ⊙ (1 − tanh²(c_k))
    di = dc ⊙ g   dg = dc ⊙ i   df = dc ⊙ c_{k−1}        (dc_{k−1} = dc ⊙ f)
    dz = [di ⊙ i(1−i), df ⊙ f(1−f), do ⊙ o(1−o), dg ⊙ (1−g²)]
    ∂J/∂W_x += x_kᵀ dz   ∂J/∂W_h += h_{k−1}ᵀ dz   ∂J/∂b += Σ dz   dh_{k−1} = dz W_hᵀ
Biais de la porte d'oubli initialisé à 1 (Jozefowicz et al., 2015) : au départ, la cellule garde
sa mémoire. Mêmes Adam, arrêt anticipé et moyenne de graines que le MLP.
Avertissement (à écrire) : avec quelques centaines de jours, un LSTM est très exposé au
surapprentissage ; c'est précisément ce que la comparaison doit montrer ou démentir.

Tous les gradients (C et D) sont vérifiés par différences finies dans tests/test_concurrents.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch

from .optimiseurs import creer as creer_optimiseur

TYPE = torch.float64


# ── Outils communs ────────────────────────────────────────────────────────────────────────
def pinball_et_gradient(y: torch.Tensor, F: torch.Tensor, taus: torch.Tensor) -> tuple[float, torch.Tensor]:
    """Perte moyenne Σ_q ρ_τq(y − F_q) / n et ∂/∂F (n × Q)."""
    r = y[:, None] - F
    perte = torch.maximum(taus * r, (taus - 1.0) * r).sum() / len(y)
    grad = torch.where(r > 0, -taus.expand_as(r), (1.0 - taus).expand_as(r)) / len(y)
    return float(perte), grad


def trier_quantiles(F: torch.Tensor, taus: tuple[float, ...]) -> dict[float, torch.Tensor]:
    """Tri des sorties de chaque jour : supprime les croisements (Chernozhukov et al., 2010)."""
    trie, _ = torch.sort(F, dim=1)
    return {t: trie[:, k] for k, t in enumerate(taus)}


def quantile_pondere(valeurs_triees: torch.Tensor, poids: torch.Tensor, tau: float) -> torch.Tensor:
    """Pour chaque ligne de `poids` (n × m, lignes de somme 1, colonnes rangées comme `valeurs_triees`) :
    plus petite valeur v telle que Σ_{y ≤ v} w ≥ τ."""
    cumul = torch.cumsum(poids, dim=1)
    k = torch.searchsorted(cumul, torch.full((poids.shape[0], 1), tau - 1e-12, dtype=TYPE)).clamp(max=poids.shape[1] - 1)
    return valeurs_triees[k.squeeze(1)]


# ── Arbre de régression (CART) ───────────────────────────────────────────────────────────
class Arbre:
    """Arbre stocké en tableaux : variable (−1 = feuille), seuil, enfants gauche/droite, valeur."""

    def __init__(self, profondeur_max: int = 12, min_feuille: int = 5, variables_par_noeud: int | None = None,
                 generateur: torch.Generator | None = None):
        self.profondeur_max, self.min_feuille = profondeur_max, min_feuille
        self.m, self.gen = variables_par_noeud, generateur

    def _coupure(self, X: torch.Tensor, r: torch.Tensor) -> tuple[int, float, float]:
        """Meilleure coupure (variable, seuil, gain) ; gain ≤ 0 : pas de coupure utile."""
        n, p = X.shape
        if n < 2 * self.min_feuille:
            return -1, 0.0, 0.0
        cols = torch.arange(p) if not self.m or self.m >= p else torch.randperm(p, generator=self.gen)[: self.m]
        xs, ordre = torch.sort(X[:, cols], dim=0)
        rs = r[ordre]
        S, Q = torch.cumsum(rs, 0), torch.cumsum(rs * rs, 0)
        k = torch.arange(1, n, dtype=TYPE)[:, None]                         # k exemples à gauche
        Sg, Qg, St, Qt = S[:-1], Q[:-1], S[-1], Q[-1]
        sce = (Qg - Sg ** 2 / k) + ((Qt - Qg) - (St - Sg) ** 2 / (n - k))
        valide = (xs[1:] > xs[:-1]) & (k >= self.min_feuille) & (n - k >= self.min_feuille)
        sce = torch.where(valide, sce, torch.full_like(sce, float("inf")))
        i = int(torch.argmin(sce))
        ligne, colonne = divmod(i, len(cols))
        if not math.isfinite(float(sce[ligne, colonne])):
            return -1, 0.0, 0.0
        gain = float(Qt[colonne] - St[colonne] ** 2 / n - sce[ligne, colonne])   # totaux identiques d'une colonne à l'autre
        return int(cols[colonne]), float((xs[ligne, colonne] + xs[ligne + 1, colonne]) / 2), gain

    def construire(self, X: torch.Tensor, r: torch.Tensor, valeur_feuille=None) -> "Arbre":
        """Croissance en profondeur ; `valeur_feuille(indices)` donne la valeur d'une feuille (défaut : moyenne)."""
        valeur_feuille = valeur_feuille or (lambda idx: float(r[idx].mean()))
        self.var, self.seuil, self.gauche, self.droite, self.valeur = [], [], [], [], []
        pile = [(torch.arange(len(r)), 0, None, None)]                       # (indices, profondeur, parent, côté)
        while pile:
            idx, prof, parent, cote = pile.pop()
            noeud = len(self.var)
            if parent is not None:
                (self.gauche if cote == "g" else self.droite)[parent] = noeud
            j, s, gain = self._coupure(X[idx], r[idx]) if prof < self.profondeur_max else (-1, 0.0, 0.0)
            self.var.append(j if gain > 1e-12 else -1)
            self.seuil.append(s)
            self.gauche.append(-1)
            self.droite.append(-1)
            self.valeur.append(valeur_feuille(idx) if self.var[-1] < 0 else 0.0)
            if self.var[-1] >= 0:
                g = X[idx, j] <= s
                pile.append((idx[~g], prof + 1, noeud, "d"))
                pile.append((idx[g], prof + 1, noeud, "g"))
        self.var, self.seuil = torch.tensor(self.var), torch.tensor(self.seuil, dtype=TYPE)
        self.gauche, self.droite = torch.tensor(self.gauche), torch.tensor(self.droite)
        self.valeur = torch.tensor(self.valeur, dtype=TYPE)
        return self

    def feuilles(self, X: torch.Tensor) -> torch.Tensor:
        """Numéro de la feuille atteinte par chaque ligne (descente vectorisée, un niveau à la fois)."""
        noeud = torch.zeros(X.shape[0], dtype=torch.long)
        lignes = torch.arange(X.shape[0])
        for _ in range(self.profondeur_max + 1):
            j = self.var[noeud]
            feuille = j < 0
            if bool(feuille.all()):
                break
            x = X[lignes, j.clamp(min=0)]
            suivant = torch.where(x <= self.seuil[noeud], self.gauche[noeud], self.droite[noeud])
            noeud = torch.where(feuille, noeud, suivant)
        return noeud

    def predire(self, X: torch.Tensor) -> torch.Tensor:
        return self.valeur[self.feuilles(X)]


# ── A. Forêt aléatoire quantile ─────────────────────────────────────────────────────────
class ForetAleatoireQuantile:
    def __init__(self, taus=(0.05, 0.5, 0.8, 0.95), arbres: int = 300, profondeur_max: int = 12,
                 min_feuille: int = 5, part_variables: float = 1 / 3, graine: int = 0):
        self.taus = tuple(sorted(taus))
        self.B, self.prof, self.min_feuille, self.part, self.graine = arbres, profondeur_max, min_feuille, part_variables, graine

    def entrainer(self, X, y) -> "ForetAleatoireQuantile":
        X, y = torch.as_tensor(X, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
        gen = torch.Generator().manual_seed(self.graine)
        n, p = X.shape
        m = max(1, math.ceil(self.part * p))
        self.arbres = []
        for _ in range(self.B):
            boot = torch.randint(0, n, (n,), generator=gen)                    # échantillon bootstrap
            self.arbres.append(Arbre(self.prof, self.min_feuille, m, gen).construire(X[boot], y[boot]))
        # Feuille de chaque jour d'entraînement (toutes observations, comme quantregForest)
        self.X, self.y = X, y
        self.feuilles_entr = [a.feuilles(X) for a in self.arbres]
        self.ordre = torch.argsort(y)
        self.importance = self._importance_impurete(p)
        return self

    def _importance_impurete(self, p: int) -> torch.Tensor:
        """Fréquence d'utilisation de chaque variable dans les coupures (indicateur simple, normalisé)."""
        compte = torch.zeros(p, dtype=TYPE)
        for a in self.arbres:
            v = a.var[a.var >= 0]
            compte += torch.bincount(v, minlength=p).to(TYPE)
        return compte / compte.sum()

    def poids(self, X) -> torch.Tensor:
        """w_i(x) de Meinshausen, n_test × n_entraînement."""
        X = torch.as_tensor(X, dtype=TYPE)
        W = torch.zeros(X.shape[0], len(self.y), dtype=TYPE)
        for a, fe in zip(self.arbres, self.feuilles_entr):
            meme = (a.feuilles(X)[:, None] == fe[None, :]).to(TYPE)
            W += meme / meme.sum(1, keepdim=True).clamp(min=1.0)
        return W / len(self.arbres)

    def predire(self, X) -> dict[float, torch.Tensor]:
        W = self.poids(X)[:, self.ordre]
        y_trie = self.y[self.ordre]
        F = torch.stack([quantile_pondere(y_trie, W, t) for t in self.taus], dim=1)
        return trier_quantiles(F, self.taus)


# ── B. Gradient boosting quantile ───────────────────────────────────────────────────────
class GradientBoostingQuantile:
    def __init__(self, tau: float = 0.5, etapes: int = 300, taux: float = 0.05, profondeur: int = 3,
                 min_feuille: int = 5, sous_echantillon: float = 0.8, graine: int = 0):
        self.tau, self.M, self.nu, self.prof, self.min_feuille, self.sous, self.graine = tau, etapes, taux, profondeur, min_feuille, sous_echantillon, graine

    def entrainer(self, X, y) -> "GradientBoostingQuantile":
        X, y = torch.as_tensor(X, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
        gen = torch.Generator().manual_seed(self.graine)
        n = len(y)
        self.F0 = float(torch.quantile(y, self.tau))
        F = torch.full((n,), self.F0, dtype=TYPE)
        self.arbres = []
        for _ in range(self.M):
            r = y - F
            g = torch.where(r > 0, torch.full_like(r, self.tau), torch.full_like(r, self.tau - 1.0))   # −∂ρ/∂F
            idx = torch.randperm(n, generator=gen)[: max(2 * self.min_feuille, int(self.sous * n))]
            rs = r[idx]
            # Valeur de feuille = quantile τ des résidus de la feuille (pas optimal pour la perte pinball)
            arbre = Arbre(self.prof, self.min_feuille).construire(X[idx], g[idx], lambda f, rs=rs: float(torch.quantile(rs[f], self.tau)))
            F = F + self.nu * arbre.predire(X)
            self.arbres.append(arbre)
        return self

    def predire(self, X) -> torch.Tensor:
        X = torch.as_tensor(X, dtype=TYPE)
        return self.F0 + self.nu * sum(a.predire(X) for a in self.arbres)


@dataclass
class EnsembleQuantiles:
    """Un modèle par quantile (gradient boosting), sorties triées."""
    fabrique: object
    taus: tuple[float, ...] = (0.05, 0.5, 0.8, 0.95)
    modeles: dict = field(default_factory=dict)

    def entrainer(self, X, y) -> "EnsembleQuantiles":
        self.modeles = {t: self.fabrique(t).entrainer(X, y) for t in self.taus}
        return self

    def predire(self, X) -> dict[float, torch.Tensor]:
        F = torch.stack([self.modeles[t].predire(X) for t in self.taus], dim=1)
        return trier_quantiles(F, self.taus)


# ── Réseaux : socle d'entraînement (Adam, arrêt anticipé chronologique, moyenne de graines) ──
class _ReseauQuantile:
    def __init__(self, taus, taux: float, epoques: int, patience: int, lambda_: float, graines: int, part_validation: float):
        self.taus = tuple(sorted(taus))
        self.taux, self.epoques, self.patience, self.lambda_, self.graines, self.part_val = taux, epoques, patience, lambda_, graines, part_validation

    # À définir : _initialiser(p, gen) -> dict ; _avant(X, P) -> (F, cache) ; _arriere(G, cache, P) -> gradients
    def objectif_et_gradients(self, X, y, P) -> tuple[float, dict]:
        F, cache = self._avant(X, P)
        perte, G = pinball_et_gradient(y, F, torch.tensor(self.taus, dtype=TYPE))
        grads = self._arriere(G, cache, P)
        for nom, v in P.items():
            if nom.startswith("W"):                                       # pénalité L2 sur les poids seulement
                perte += 0.5 * self.lambda_ * float((v * v).sum())
                grads[nom] = grads[nom] + self.lambda_ * v
        return perte, grads

    def _un_entrainement(self, X, y, graine: int) -> dict:
        gen = torch.Generator().manual_seed(graine)
        P = self._initialiser(X.shape[1], gen)
        nv = max(5, int(self.part_val * len(y)))
        Xa, ya, Xv, yv = X[:-nv], y[:-nv], X[-nv:], y[-nv:]                # validation = derniers jours
        opt = creer_optimiseur("adam", taux=self.taux)
        meilleur, garde, attente = float("inf"), None, 0
        taus = torch.tensor(self.taus, dtype=TYPE)
        for _ in range(self.epoques):
            _, grads = self.objectif_et_gradients(Xa, ya, P)
            opt.pas(P, grads)
            pv, _ = pinball_et_gradient(yv, self._avant(Xv, P)[0], taus)
            if pv < meilleur - 1e-9:
                meilleur, garde, attente = pv, {k: v.clone() for k, v in P.items()}, 0
            else:
                attente += 1
                if attente >= self.patience:
                    break
        return garde

    def entrainer(self, X, y):
        X, y = torch.as_tensor(X, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
        self.y_moy, self.y_et = float(y.mean()), float(y.std()) or 1.0      # cible centrée-réduite pendant l'apprentissage
        z = (y - self.y_moy) / self.y_et
        self.parametres = [self._un_entrainement(X, z, g) for g in range(self.graines)]
        return self

    def predire(self, X) -> dict[float, torch.Tensor]:
        X = torch.as_tensor(X, dtype=TYPE)
        F = torch.stack([self._avant(X, P)[0] for P in self.parametres]).mean(0) * self.y_et + self.y_moy
        return trier_quantiles(F, self.taus)


# ── C. Perceptron multicouche quantile ──────────────────────────────────────────────────
class PerceptronQuantile(_ReseauQuantile):
    def __init__(self, taus=(0.05, 0.5, 0.8, 0.95), couches=(32, 16), taux: float = 0.01, epoques: int = 1500,
                 patience: int = 150, lambda_: float = 1e-3, graines: int = 3, part_validation: float = 0.15):
        super().__init__(taus, taux, epoques, patience, lambda_, graines, part_validation)
        self.couches = couches

    def _initialiser(self, p: int, gen) -> dict:
        tailles, P = [p, *self.couches, len(self.taus)], {}
        for k in range(len(tailles) - 1):
            P[f"W{k + 1}"] = torch.randn(tailles[k], tailles[k + 1], generator=gen, dtype=TYPE) * math.sqrt(2.0 / tailles[k])
            P[f"b{k + 1}"] = torch.zeros(tailles[k + 1], dtype=TYPE)
        return P

    def _avant(self, X, P):
        a, cache, L = X, [], len(self.couches) + 1
        for k in range(1, L + 1):
            z = a @ P[f"W{k}"] + P[f"b{k}"]
            cache.append((a, z))
            a = torch.relu(z) if k < L else z
        return a, cache

    def _arriere(self, G, cache, P):
        grads, delta, L = {}, G, len(cache)
        for k in range(L, 0, -1):
            a_prec, z = cache[k - 1]
            if k < L:
                delta = delta * (z > 0).to(TYPE)                                  # dérivée de ReLU
            grads[f"W{k}"], grads[f"b{k}"] = a_prec.T @ delta, delta.sum(0)
            delta = delta @ P[f"W{k}"].T
        return grads


# ── D. LSTM quantile ────────────────────────────────────────────────────────────────────
class LSTMQuantile(_ReseauQuantile):
    """Colonnes 0 … retards−1 de X : occupation de J−0 (plus récente) à J−(retards−1) ; le reste : variables exogènes."""

    def __init__(self, retards: int = 7, taus=(0.05, 0.5, 0.8, 0.95), cache: int = 16, taux: float = 0.01,
                 epoques: int = 1500, patience: int = 150, lambda_: float = 1e-3, graines: int = 3, part_validation: float = 0.15):
        super().__init__(taus, taux, epoques, patience, lambda_, graines, part_validation)
        self.L, self.H = retards, cache

    def _initialiser(self, p: int, gen) -> dict:
        H, e, Q = self.H, p - self.L, len(self.taus)
        b = torch.zeros(4 * H, dtype=TYPE)
        b[H:2 * H] = 1.0                                                          # biais de la porte d'oubli
        return {"Wx": torch.randn(1, 4 * H, generator=gen, dtype=TYPE) * math.sqrt(1.0 / 1),
                "Wh": torch.randn(H, 4 * H, generator=gen, dtype=TYPE) * math.sqrt(1.0 / H),
                "b": b,
                "Ws": torch.randn(H + e, Q, generator=gen, dtype=TYPE) * math.sqrt(1.0 / (H + e)),
                "bs": torch.zeros(Q, dtype=TYPE)}

    def _avant(self, X, P):
        n, H = X.shape[0], self.H
        seq = X[:, : self.L].flip(1)                                              # du plus ancien au plus récent
        h = torch.zeros(n, H, dtype=TYPE)
        c = torch.zeros(n, H, dtype=TYPE)
        pas = []
        for k in range(self.L):
            x = seq[:, k: k + 1]
            z = x @ P["Wx"] + h @ P["Wh"] + P["b"]
            i, f, o = torch.sigmoid(z[:, :H]), torch.sigmoid(z[:, H:2 * H]), torch.sigmoid(z[:, 2 * H:3 * H])
            g = torch.tanh(z[:, 3 * H:])
            c_prec, h_prec = c, h
            c = f * c + i * g
            h = o * torch.tanh(c)
            pas.append((x, h_prec, c_prec, i, f, o, g, c))
        A = torch.cat([h, X[:, self.L:]], dim=1)
        return A @ P["Ws"] + P["bs"], (pas, A)

    def _arriere(self, G, cache, P):
        pas, A = cache
        H = self.H
        grads = {"Ws": A.T @ G, "bs": G.sum(0), "Wx": torch.zeros_like(P["Wx"]), "Wh": torch.zeros_like(P["Wh"]), "b": torch.zeros_like(P["b"])}
        dh = G @ P["Ws"][:H].T
        dc = torch.zeros_like(dh)
        for x, h_prec, c_prec, i, f, o, g, c in reversed(pas):
            tc = torch.tanh(c)
            do = dh * tc
            dc = dc + dh * o * (1.0 - tc * tc)
            di, dg, df = dc * g, dc * i, dc * c_prec
            dz = torch.cat([di * i * (1 - i), df * f * (1 - f), do * o * (1 - o), dg * (1 - g * g)], dim=1)
            grads["Wx"] += x.T @ dz
            grads["Wh"] += h_prec.T @ dz
            grads["b"] += dz.sum(0)
            dh = dz @ P["Wh"].T
            dc = dc * f
        return grads


# ── Hyperparamètres et fabrique ─────────────────────────────────────────────────────────
@dataclass
class HyperConcurrents:
    tau: float = 0.8
    taus_intervalle: tuple = (0.05, 0.5, 0.95)
    # A. forêt
    arbres: int = 300
    profondeur_foret: int = 12
    min_feuille: int = 5
    part_variables: float = 1 / 3
    # B. boosting
    etapes: int = 300
    taux_boosting: float = 0.05
    profondeur_boosting: int = 3
    sous_echantillon: float = 0.8
    # C et D. réseaux
    couches: tuple = (32, 16)
    cache_lstm: int = 16
    taux_reseau: float = 0.01
    epoques: int = 1500
    patience: int = 150
    lambda_: float = 1e-3
    graines: int = 3

    def quantiles(self) -> tuple[float, ...]:
        return tuple(sorted({*self.taus_intervalle, self.tau}))


CONCURRENTS = {"foret": "A · forêt aléatoire quantile", "boosting": "B · gradient boosting quantile",
               "mlp": "C · perceptron multicouche quantile", "lstm": "D · LSTM quantile"}


def fabrique_concurrent(nom: str, hp: HyperConcurrents, retards: int = 7):
    """Fonction sans argument qui crée un concurrent neuf (même usage que svr.niveaux.fabrique)."""
    q = hp.quantiles()
    if nom == "foret":
        return lambda: ForetAleatoireQuantile(q, hp.arbres, hp.profondeur_foret, hp.min_feuille, hp.part_variables)
    if nom == "boosting":
        un = lambda t: GradientBoostingQuantile(t, hp.etapes, hp.taux_boosting, hp.profondeur_boosting, hp.min_feuille, hp.sous_echantillon)
        return lambda: EnsembleQuantiles(un, q)
    if nom == "mlp":
        return lambda: PerceptronQuantile(q, hp.couches, hp.taux_reseau, hp.epoques, hp.patience, hp.lambda_, hp.graines)
    if nom == "lstm":
        return lambda: LSTMQuantile(retards, q, hp.cache_lstm, hp.taux_reseau, hp.epoques, hp.patience, hp.lambda_, hp.graines)
    raise ValueError(f"Concurrent inconnu : {nom}. Choix : {', '.join(CONCURRENTS)}.")


def importance_permutation(modele, X, y, noms: list[str], tau: float = 0.5, repetitions: int = 5, graine: int = 0) -> dict[str, float]:
    """
    Importance d'une variable = hausse de la perte pinball (au quantile τ) quand on mélange sa colonne
    sur des jours NON vus à l'entraînement. Valable pour tous les modèles (SVR compris) : c'est la
    mesure à utiliser pour comparer ce que chaque modèle « regarde ».
    """
    X, y = torch.as_tensor(X, dtype=TYPE), torch.as_tensor(y, dtype=TYPE)
    gen = torch.Generator().manual_seed(graine)
    t = torch.tensor([tau], dtype=TYPE)
    sortie = lambda Z: (modele.predire(Z)[tau] if isinstance(modele.predire(Z), dict) else modele.predire(Z))[:, None]
    base, _ = pinball_et_gradient(y, sortie(X), t)
    res = {}
    for j, nom in enumerate(noms):
        hausses = []
        for _ in range(repetitions):
            Z = X.clone()
            Z[:, j] = Z[torch.randperm(len(y), generator=gen), j]
            p, _ = pinball_et_gradient(y, sortie(Z), t)
            hausses.append(p - base)
        res[nom] = sum(hausses) / repetitions
    return res
