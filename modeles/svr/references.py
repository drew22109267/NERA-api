r"""
Niveau 0 — prévisions de référence (sans apprentissage).

Elles fixent la barre à battre : un SVR qui ne fait pas mieux que « demain = aujourd'hui »
n'apporte rien. Elles travaillent directement sur la série d'occupation y_t (jour t),
pour une prévision à l'horizon h (le jour t + h, faite le soir du jour t).

1. Persistance :            ŷ_{t+h} = y_t
2. Saisonnière hebdomadaire : ŷ_{t+h} = moyenne des k derniers jours ayant le même jour de
   la semaine que t + h et connus au jour t (t + h − 7, t + h − 14, … ≤ t).
3. Moyenne mobile :          ŷ_{t+h} = (1/k) Σ_{j=0}^{k−1} y_{t−j}

Pour une prévision par intervalle, la référence est le quantile empirique des erreurs passées
de la persistance (intervalle « naïf ») : voir intervalle_persistance.
"""
from __future__ import annotations

import torch

TYPE = torch.float64


def persistance(serie: torch.Tensor, origines: torch.Tensor, h: int) -> torch.Tensor:
    """ŷ_{t+h} = y_t pour chaque origine t (indices dans la série)."""
    return serie[origines].to(TYPE)


def saisonniere(serie: torch.Tensor, origines: torch.Tensor, h: int, semaines: int = 4) -> torch.Tensor:
    """Moyenne des `semaines` derniers jours de même jour de semaine que la cible, connus à l'origine."""
    previsions = []
    for t in origines.tolist():
        cible = t + h
        premiers = cible - 7 * ((h + 6) // 7)               # dernier jour de même jour de semaine ≤ t
        indices = [premiers - 7 * k for k in range(semaines) if premiers - 7 * k >= 0]
        previsions.append(serie[indices].to(TYPE).mean() if indices else serie[t].to(TYPE))
    return torch.stack(previsions)


def moyenne_mobile(serie: torch.Tensor, origines: torch.Tensor, h: int, k: int = 7) -> torch.Tensor:
    """Moyenne des k derniers jours connus à l'origine."""
    return torch.stack([serie[max(0, t - k + 1): t + 1].to(TYPE).mean() for t in origines.tolist()])


def intervalle_persistance(serie: torch.Tensor, origines: torch.Tensor, h: int,
                           niveau: float = 0.9, historique: int = 180) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Intervalle naïf : y_t + [quantile bas, quantile haut] des erreurs passées de la persistance
    (erreurs e_s = y_{s+h} − y_s pour s + h ≤ t, sur les `historique` derniers jours).
    """
    a = (1.0 - niveau) / 2.0
    bas, haut = [], []
    for t in origines.tolist():
        s = torch.arange(max(0, t - h - historique + 1), t - h + 1)
        if len(s) < 10:
            bas.append(serie[t].to(TYPE)); haut.append(serie[t].to(TYPE)); continue
        erreurs = (serie[s + h] - serie[s]).to(TYPE)
        bas.append(serie[t] + torch.quantile(erreurs, a)); haut.append(serie[t] + torch.quantile(erreurs, 1 - a))
    return torch.stack(bas), torch.stack(haut)
