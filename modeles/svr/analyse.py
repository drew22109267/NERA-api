r"""
Statistiques descriptives et diagnostics, codés à la main (aucune fonction toute faite de
statistique : ni numpy.corrcoef, ni pandas.corr, ni statsmodels).

Ce fichier sert aux graphiques du mémoire (visualisations.py) : il calcule les nombres, les
graphiques ne font que les dessiner. Chaque fonction rappelle sa formule.

Contenu
-------
1. Corrélation de Pearson (linéaire) entre toutes les variables      → matrice_pearson
2. Corrélation de Spearman (monotone, sur les rangs)                  → rangs, matrice_spearman
3. Autocorrélation d'une série (ACF) et autocorrélation partielle     → acf, pacf
4. Bande de significativité de l'ACF                                   → bande_acf
5. Profils moyens (par jour de la semaine, par mois)                   → moyenne_par_groupe
6. Calibration des quantiles (couverture observée vs nominale)        → calibration_quantiles
7. Courbe d'apprentissage (erreur selon la taille de l'entraînement)  → courbe_apprentissage

Toutes les fonctions prennent et rendent des tenseurs PyTorch en double précision (float64),
comme le reste du code des modèles.
"""
from __future__ import annotations

import torch

TYPE = torch.float64


# ─────────────────────────────────────────────────────────────────────────────
# 1. Corrélation de Pearson
# ─────────────────────────────────────────────────────────────────────────────
def matrice_pearson(X: torch.Tensor) -> torch.Tensor:
    r"""
    Matrice des corrélations de Pearson entre les colonnes de X (n lignes × p variables).

    Pour deux variables a et b observées n fois :
        r(a, b) = Σ (a_i − ā)(b_i − b̄) / √[ Σ (a_i − ā)² · Σ (b_i − b̄)² ]
    r vaut +1 si b augmente exactement comme une droite croissante de a, −1 pour une droite
    décroissante, 0 s'il n'y a aucune relation LINÉAIRE (une relation courbe peut donner r ≈ 0).

    Calcul matriciel : on centre et on réduit chaque colonne,
        Z = (X − μ) / σ        avec μ la moyenne et σ l'écart-type (division par n),
    alors la matrice des corrélations est simplement
        R = Zᵀ Z / n           (chaque case R[j, k] est la moyenne des produits z_j · z_k).
    Une colonne constante (σ = 0) n'a pas de corrélation définie : on met NaN sur sa ligne
    et sa colonne, plutôt qu'une valeur trompeuse.
    """
    X = torch.as_tensor(X, dtype=TYPE)
    n = X.shape[0]
    moyenne = X.mean(dim=0)                                  # μ_j pour chaque colonne j
    centre = X - moyenne                                     # x − μ
    ecart = torch.sqrt((centre ** 2).sum(dim=0) / n)         # σ_j (écart-type « population »)
    constante = ecart < 1e-12                                # colonnes sans variation
    Z = centre / torch.where(constante, torch.ones_like(ecart), ecart)
    R = (Z.T @ Z) / n                                        # corrélations
    R[constante, :] = float("nan")
    R[:, constante] = float("nan")
    return R.clamp(-1.0, 1.0)                                # supprime les 1,0000000002 d'arrondi


# ─────────────────────────────────────────────────────────────────────────────
# 2. Corrélation de Spearman
# ─────────────────────────────────────────────────────────────────────────────
def rangs(x: torch.Tensor) -> torch.Tensor:
    r"""
    Rang de chaque valeur (1 = la plus petite), les ex æquo recevant le rang MOYEN.

    Exemple : x = (10, 30, 20, 30)  →  rangs = (1, 3,5, 2, 3,5)
    (les deux 30 occupent les places 3 et 4 : chacun reçoit (3 + 4)/2 = 3,5).

    Algorithme : on trie ; on parcourt les valeurs triées par paquets de valeurs égales ;
    un paquet qui occupe les places i+1 … j (numérotées à partir de 1) reçoit le rang
    (i + 1 + j)/2.
    """
    x = torch.as_tensor(x, dtype=TYPE)
    ordre = torch.argsort(x)                                 # indices du plus petit au plus grand
    tries = x[ordre]
    r = torch.empty_like(x)
    i, n = 0, len(x)
    while i < n:
        j = i
        while j + 1 < n and tries[j + 1] == tries[i]:       # agrandit le paquet d'ex æquo
            j += 1
        r[ordre[i:j + 1]] = (i + 1 + j + 1) / 2.0            # rang moyen des places i+1 … j+1
        i = j + 1
    return r


def matrice_spearman(X: torch.Tensor) -> torch.Tensor:
    r"""
    Corrélation de Spearman = corrélation de Pearson calculée sur les RANGS.

    Elle mesure une relation MONOTONE (toujours croissante ou toujours décroissante), même
    courbe : si b = a³, Pearson < 1 mais Spearman = 1. Elle est aussi peu sensible aux valeurs
    extrêmes (un jour exceptionnel ne pèse qu'un rang).
    """
    X = torch.as_tensor(X, dtype=TYPE)
    R = torch.stack([rangs(X[:, j]) for j in range(X.shape[1])], dim=1)
    return matrice_pearson(R)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Autocorrélation (ACF) et autocorrélation partielle (PACF)
# ─────────────────────────────────────────────────────────────────────────────
def acf(x: torch.Tensor, retard_max: int) -> torch.Tensor:
    r"""
    Autocorrélation de la série x aux retards k = 0, 1, …, retard_max.

        ρ̂(k) = Σ_{t=1}^{n−k} (x_t − x̄)(x_{t+k} − x̄)  /  Σ_{t=1}^{n} (x_t − x̄)²

    ρ̂(k) dit à quel point l'occupation d'aujourd'hui ressemble à celle d'il y a k jours.
    Un pic à k = 7, 14, 21 révèle un rythme HEBDOMADAIRE ; une décroissance lente révèle une
    forte « mémoire » (l'occupation change peu d'un jour à l'autre) : c'est ce qui justifie
    les 7 retards utilisés comme variables d'entrée (svr/caracteristiques.py).
    On divise par la somme sur toute la série (estimateur standard, toujours entre −1 et 1).
    """
    x = torch.as_tensor(x, dtype=TYPE)
    c = x - x.mean()
    denominateur = (c * c).sum()
    sortie = torch.empty(retard_max + 1, dtype=TYPE)
    for k in range(retard_max + 1):
        sortie[k] = (c[: len(c) - k] * c[k:]).sum() / denominateur
    return sortie


def pacf(x: torch.Tensor, retard_max: int) -> torch.Tensor:
    r"""
    Autocorrélation PARTIELLE aux retards 0 … retard_max, par la récursion de Durbin-Levinson.

    L'ACF au retard 2 mélange un effet direct (J−2 → J) et un effet indirect (J−2 → J−1 → J).
    La PACF φ_kk ne garde que l'effet DIRECT du retard k, une fois les retards 1 … k−1 pris
    en compte. Elle indique combien de retards apportent une information nouvelle.

    Récursion (ρ = ACF, φ_{k,j} = coefficient du retard j dans le meilleur prédicteur linéaire
    d'ordre k) :
        φ_11 = ρ(1)
        φ_kk = [ ρ(k) − Σ_{j=1}^{k−1} φ_{k−1,j} ρ(k−j) ]  /  [ 1 − Σ_{j=1}^{k−1} φ_{k−1,j} ρ(j) ]
        φ_kj = φ_{k−1,j} − φ_kk · φ_{k−1,k−j}        pour j = 1 … k−1
    Par convention φ_00 = 1.
    """
    rho = acf(x, retard_max)
    sortie = torch.zeros(retard_max + 1, dtype=TYPE)
    sortie[0] = 1.0
    if retard_max == 0:
        return sortie
    precedent = torch.zeros(retard_max + 1, dtype=TYPE)     # φ_{k−1, ·} (indice 1 … k−1 utilisé)
    for k in range(1, retard_max + 1):
        if k == 1:
            phi_kk = rho[1]
        else:
            numerateur = rho[k] - sum(precedent[j] * rho[k - j] for j in range(1, k))
            denominateur = 1.0 - sum(precedent[j] * rho[j] for j in range(1, k))
            phi_kk = numerateur / denominateur
        courant = precedent.clone()
        courant[k] = phi_kk
        for j in range(1, k):
            courant[j] = precedent[j] - phi_kk * precedent[k - j]
        sortie[k] = phi_kk
        precedent = courant
    return sortie


def bande_acf(n: int) -> float:
    r"""
    Seuil de significativité approché à 95 % pour l'ACF et la PACF d'une série de longueur n.

    Si la série était un bruit sans mémoire, ρ̂(k) suivrait à peu près une loi normale de
    moyenne 0 et d'écart-type 1/√n (formule de Bartlett, cas du bruit blanc) ; 95 % des valeurs
    tombent alors dans ± 1,96/√n. Une barre qui dépasse ce seuil est donc probablement réelle.
    """
    return 1.96 / n ** 0.5


# ─────────────────────────────────────────────────────────────────────────────
# 5. Profils moyens
# ─────────────────────────────────────────────────────────────────────────────
def moyenne_par_groupe(valeurs: torch.Tensor, groupes: torch.Tensor, nombre_groupes: int) -> tuple[torch.Tensor, torch.Tensor]:
    r"""
    Moyenne et écart-type des valeurs dans chaque groupe 0 … nombre_groupes−1
    (par exemple groupe = jour de la semaine, 0 = lundi).

        moyenne_g = (1/n_g) Σ_{i : groupe_i = g} v_i
        écart_g   = √[ (1/n_g) Σ (v_i − moyenne_g)² ]
    Un groupe vide reçoit NaN.
    """
    valeurs = torch.as_tensor(valeurs, dtype=TYPE)
    groupes = torch.as_tensor(groupes)
    moyennes = torch.full((nombre_groupes,), float("nan"), dtype=TYPE)
    ecarts = torch.full((nombre_groupes,), float("nan"), dtype=TYPE)
    for g in range(nombre_groupes):
        v = valeurs[groupes == g]
        if len(v):
            moyennes[g] = v.mean()
            ecarts[g] = torch.sqrt(((v - v.mean()) ** 2).mean())
    return moyennes, ecarts


# ─────────────────────────────────────────────────────────────────────────────
# 6. Calibration des quantiles
# ─────────────────────────────────────────────────────────────────────────────
def calibration_quantiles(y: torch.Tensor, quantiles: dict[float, torch.Tensor]) -> dict[float, float]:
    r"""
    Pour chaque niveau τ prévu, part des jours où la vraie occupation est sous la prévision :

        couverture(τ) = (1/n) Σ 1{ y_i ≤ q̂_τ(x_i) }

    Un quantile bien calibré a une couverture ≈ τ : le quantile à 80 % doit être dépassé
    environ 1 jour sur 5. Sur le graphique de calibration, les points doivent tomber sur la
    diagonale ; au-dessus, le modèle est prudent (il surestime) ; en dessous, il sous-estime
    le besoin en lits — l'erreur la plus coûteuse pour le module lits.
    """
    y = torch.as_tensor(y, dtype=TYPE)
    return {tau: float((y <= torch.as_tensor(q, dtype=TYPE)).double().mean()) for tau, q in sorted(quantiles.items())}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Courbe d'apprentissage
# ─────────────────────────────────────────────────────────────────────────────
def courbe_apprentissage(X_entr: torch.Tensor, y_entr: torch.Tensor, X_val: torch.Tensor, y_val: torch.Tensor,
                         fabrique, tailles: list[int], erreur) -> list[dict]:
    r"""
    Erreur d'entraînement et erreur de validation selon le nombre de jours d'entraînement.

    Pour chaque taille n de la liste, le modèle est entraîné sur les n jours LES PLUS RÉCENTS
    de l'entraînement (ceux qui précèdent immédiatement la validation : c'est ce que ferait un
    service qui n'aurait que n jours d'historique), puis évalué :
      - sur ces mêmes n jours  → erreur d'entraînement (ce que le modèle a « appris par cœur ») ;
      - sur la période de validation, toujours la même → erreur de généralisation.

    Lecture du graphique :
      - les deux courbes se rapprochent quand n augmente : le modèle a assez de données ;
      - grand écart persistant : surapprentissage (le modèle colle trop à l'entraînement) ;
      - les deux courbes restent hautes : sous-apprentissage (modèle trop simple).
    La standardisation est réapprise à chaque taille, sur les n jours seulement (pas de fuite).

    `fabrique()` crée un modèle neuf ; `erreur(y, prévision)` renvoie un nombre (MAE, pinball…).
    """
    from .caracteristiques import Standardiseur          # import local : évite une dépendance circulaire

    resultats = []
    for n in tailles:
        n = min(n, len(y_entr))
        Xn, yn = X_entr[-n:], y_entr[-n:]                    # les n jours les plus récents
        std = Standardiseur(list(range(X_entr.shape[1]))).ajuster(Xn)
        modele = fabrique().entrainer(std.transformer(Xn), yn)
        resultats.append({"taille": n,
                          "erreur_entrainement": erreur(yn, modele.predire(std.transformer(Xn))),
                          "erreur_validation": erreur(y_val, modele.predire(std.transformer(X_val)))})
    return resultats


# ─────────────────────────────────────────────────────────────────────────────
# 8. Importance des variables par permutation
# ─────────────────────────────────────────────────────────────────────────────
def importance_permutation(modele, X: torch.Tensor, y: torch.Tensor, erreur, groupes: dict[str, list[int]],
                           repetitions: int = 5, graine: int = 0) -> dict[str, tuple[float, float]]:
    r"""
    Combien l'erreur augmente quand on « casse » une variable (ou un groupe de variables).

    Pour chaque groupe G de colonnes : on mélange au hasard l'ordre des lignes DANS ces colonnes
    seulement (la variable garde sa distribution mais perd tout lien avec la cible), on refait la
    prévision avec le MÊME modèle déjà entraîné, et on mesure
        importance(G) = erreur(données mélangées) − erreur(données d'origine)
    Une importance proche de 0 : le modèle n'utilise pas cette information.
    On répète le mélange `repetitions` fois et on rend (moyenne, écart-type) des augmentations.
    Méthode de Breiman (2001), valable pour n'importe quel modèle (« agnostique »).
    """
    gen = torch.Generator().manual_seed(graine)
    base = erreur(y, modele.predire(X))
    resultat = {}
    for nom, colonnes in groupes.items():
        hausses = []
        for _ in range(repetitions):
            Xp = X.clone()
            ordre = torch.randperm(X.shape[0], generator=gen)
            Xp[:, colonnes] = X[ordre][:, colonnes]              # mêmes lignes mélangées pour tout le groupe
            hausses.append(erreur(y, modele.predire(Xp)) - base)
        h = torch.tensor(hausses, dtype=TYPE)
        resultat[nom] = (float(h.mean()), float(h.std(unbiased=False)))
    return resultat


# ─────────────────────────────────────────────────────────────────────────────
# 9. Coût des décisions de lits
# ─────────────────────────────────────────────────────────────────────────────
def cout_decision(y: torch.Tensor, prevu: torch.Tensor, cout_penurie: float, cout_surcapacite: float) -> float:
    r"""
    Coût moyen par jour quand on prépare `prevu` lits et que `y` patients se présentent :
        coût = c_p · max(y − q, 0)  +  c_s · max(q − y, 0)
    c_p : coût d'un patient sans lit (pénurie) ; c_s : coût d'un lit préparé pour rien.
    La décision q qui minimise le coût moyen est le quantile τ* = c_p / (c_p + c_s) de y
    (c'est la perte pinball multipliée par c_p + c_s) : pour c_p = 4 c_s, τ* = 0,8.
    """
    y, q = torch.as_tensor(y, dtype=TYPE), torch.as_tensor(prevu, dtype=TYPE)
    return float((cout_penurie * (y - q).clamp(min=0) + cout_surcapacite * (q - y).clamp(min=0)).mean())


# ─────────────────────────────────────────────────────────────────────────────
# 10. Accord entre deux saisies (qualité de la transcription)
# ─────────────────────────────────────────────────────────────────────────────
def kappa_cohen(a: list, b: list) -> float:
    r"""
    Kappa de Cohen : accord entre deux personnes qui ont saisi les mêmes cases, corrigé du hasard.
        p_o = part des cases identiques
        p_e = Σ_c p_a(c) · p_b(c)    (accord attendu si chacun répondait au hasard selon ses fréquences)
        κ   = (p_o − p_e) / (1 − p_e)
    κ = 1 : accord parfait ; κ = 0 : pas mieux que le hasard. Repères usuels (Landis & Koch) :
    > 0,8 presque parfait, 0,6–0,8 bon, 0,4–0,6 moyen.
    """
    if len(a) != len(b) or not a:
        raise ValueError("Il faut deux listes de même longueur, non vides.")
    n = len(a)
    p_o = sum(x == y for x, y in zip(a, b)) / n
    categories = set(a) | set(b)
    p_e = sum((a.count(c) / n) * (b.count(c) / n) for c in categories)
    return 1.0 if p_e == 1 else (p_o - p_e) / (1 - p_e)
