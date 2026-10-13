r"""
Métriques d'évaluation, écrites à la main (protocole, étape 4.2).

Prévision ponctuelle (y réel, ŷ prévu, n jours) :
    MAE  = (1/n) Σ |y − ŷ|                       erreur moyenne, en lits
    RMSE = √[(1/n) Σ (y − ŷ)²]                    pénalise davantage les grosses erreurs
    MAPE = (100/n) Σ |y − ŷ| / y   (jours y > 0)  erreur relative, en %
    Biais = (1/n) Σ (ŷ − y)                       > 0 : le modèle surestime en moyenne
    Sous-estimations = part des jours où ŷ < y    (risque de manquer de lits)

Prévision quantile et intervalle :
    Perte pinball moyenne au quantile τ : (1/n) Σ ρ_τ(y − ŷ_τ) — la métrique « propre » d'un
        quantile (plus petite = meilleure).
    Couverture = part des jours où  bas ≤ y ≤ haut.  Un intervalle à 90 % bien calibré couvre
        ≈ 90 % des jours ; moins, il est trop étroit (dangereux) ; plus, trop large (inutile).
    Largeur moyenne = (1/n) Σ (haut − bas) : à couverture égale, plus étroit = plus utile.

Test de Diebold-Mariano (comparer deux modèles, et non deux chiffres)
---------------------------------------------------------------------
Deux modèles A et B, mêmes jours. Différence de perte jour par jour :
    d_t = L(e_t^A) − L(e_t^B)     (L = valeur absolue ou carré de l'erreur)
H₀ : E[d_t] = 0 (même précision). Statistique :
    DM = d̄ / √(V̂ / n),   V̂ = γ̂₀ + 2 Σ_{k=1}^{h−1} γ̂_k
γ̂_k est l'autocovariance de d au décalage k : pour un horizon h, des prévisions faites à des
jours voisins partagent des jours futurs, leurs erreurs sont corrélées jusqu'au décalage h − 1.
Correction de Harvey, Leybourne et Newbold (1997) pour petits échantillons :
    DM* = DM · √[(n + 1 − 2h + h(h − 1)/n) / n]
p-valeur bilatérale par la loi normale : p = 2 · (1 − Φ(|DM*|)),  Φ(z) = ½ [1 + erf(z/√2)].
DM* < 0 et p < 0,05 : A est significativement plus précis que B.
"""
from __future__ import annotations

import math

import torch

TYPE = torch.float64


def _t(x):
    return torch.as_tensor(x, dtype=TYPE)


def mae(y, yp) -> float:
    return float((_t(y) - _t(yp)).abs().mean())


def rmse(y, yp) -> float:
    return math.sqrt(float(((_t(y) - _t(yp)) ** 2).mean()))


def mape(y, yp) -> float:
    y, yp = _t(y), _t(yp)
    garder = y > 0
    return float(100.0 * ((y[garder] - yp[garder]).abs() / y[garder]).mean()) if garder.any() else float("nan")


def biais(y, yp) -> float:
    return float((_t(yp) - _t(y)).mean())


def part_sous_estimations(y, yp) -> float:
    return float((_t(yp) < _t(y)).to(TYPE).mean())


def pinball_moyenne(y, yq, tau: float) -> float:
    r = _t(y) - _t(yq)
    return float(torch.maximum(tau * r, (tau - 1.0) * r).mean())


def couverture(y, bas, haut) -> float:
    y = _t(y)
    return float(((y >= _t(bas)) & (y <= _t(haut))).to(TYPE).mean())


def largeur_moyenne(bas, haut) -> float:
    return float((_t(haut) - _t(bas)).mean())


def phi(z: float) -> float:
    """Fonction de répartition de la loi normale centrée réduite."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def diebold_mariano(y, prev_a, prev_b, h: int = 1, perte: str = "absolue") -> dict:
    """Compare A et B. Renvoie DM* (corrigé HLN), la p-valeur et le modèle le plus précis."""
    y = _t(y)
    ea, eb = y - _t(prev_a), y - _t(prev_b)
    d = (ea.abs() - eb.abs()) if perte == "absolue" else (ea ** 2 - eb ** 2)
    n = len(d)
    if n < 2 * h + 2:
        raise ValueError("Trop peu de jours pour le test de Diebold-Mariano.")
    d_barre = float(d.mean())
    dc = d - d_barre
    gammas = [float((dc[k:] * dc[: n - k]).sum()) / n for k in range(h)]
    variance = gammas[0] + 2.0 * sum(gammas[1:])
    if variance <= 0:
        # Erreurs identiques chaque jour (même prévision) : aucune différence à tester.
        return {"dm": float("nan"), "p_valeur": float("nan"), "plus_precis": "indéterminé", "significatif_5pc": False}
    dm = d_barre / math.sqrt(variance / n)
    dm_hln = dm * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    p = 2.0 * (1.0 - phi(abs(dm_hln)))
    return {"dm": round(dm_hln, 3), "p_valeur": round(p, 4),
            "plus_precis": "A" if dm_hln < 0 else "B", "significatif_5pc": p < 0.05}


def resume_ponctuel(y, yp) -> dict:
    return {"MAE": round(mae(y, yp), 3), "RMSE": round(rmse(y, yp), 3), "MAPE_%": round(mape(y, yp), 2),
            "biais": round(biais(y, yp), 3), "sous_estimations_%": round(100 * part_sous_estimations(y, yp), 1)}


def resume_intervalle(y, bas, median, haut, taus=(0.05, 0.5, 0.95)) -> dict:
    return {**resume_ponctuel(y, median),
            "couverture_%": round(100 * couverture(y, bas, haut), 1),
            "largeur_moyenne": round(largeur_moyenne(bas, haut), 2),
            "pinball_bas": round(pinball_moyenne(y, bas, taus[0]), 4),
            "pinball_median": round(pinball_moyenne(y, median, taus[1]), 4),
            "pinball_haut": round(pinball_moyenne(y, haut, taus[2]), 4)}
