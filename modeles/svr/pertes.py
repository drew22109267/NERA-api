r"""
Fonctions de perte du SVR, écrites à la main, avec leur dérivée.

Notations communes
------------------
Pour un jour i :  y_i  l'occupation réelle,  f_i = f(x_i)  la prévision,
                  r_i = y_i − f_i  le résidu.
    r_i > 0 : on a prévu MOINS que la réalité  (sous-estimation → risque de manquer de lits)
    r_i < 0 : on a prévu PLUS que la réalité   (surestimation → lits réservés pour rien)

Chaque perte renvoie deux tenseurs de même taille que y :
    valeur  L(r_i)
    gradient  ∂L/∂f_i   (dérivée par rapport à la PRÉVISION, c'est elle que le modèle ajuste)
Comme r = y − f, on a  ∂r/∂f = −1  donc  ∂L/∂f = −L'(r).

Aux points anguleux (là où la fonction n'est pas dérivable : |r| = ε, r = 0), on utilise un
SOUS-GRADIENT : n'importe quelle pente comprise entre la pente de gauche et celle de droite
convient pour une fonction convexe. On prend la valeur 0 (le point est considéré « dans le tube »).


1. Perte ε-insensible  (SVR classique, niveaux 1 et 2)
------------------------------------------------------
    L_ε(r) = max(0, |r| − ε)

Le « tube » de demi-largeur ε : une erreur d'au plus ε lits ne coûte rien ; au-delà, le coût
croît linéairement avec la distance au tube.
Dérivée par morceaux :
    r >  ε :  L = r − ε     →  L'(r) = +1   →  ∂L/∂f = −1
    r < −ε :  L = −r − ε    →  L'(r) = −1   →  ∂L/∂f = +1
    |r| ≤ ε : L = 0         →  ∂L/∂f = 0
soit  ∂L/∂f = −signe(r) · 1{|r| > ε}.
Défaut pour les lits : symétrique — manquer 5 lits coûte autant qu'en réserver 5 de trop.


2. Perte pinball au quantile τ  (régression quantile)
-----------------------------------------------------
    ρ_τ(r) = τ · r          si r ≥ 0
             (τ − 1) · r    si r < 0           = max(τ r, (τ − 1) r),   τ ∈ ]0, 1[

Pourquoi elle donne le quantile : minimiser E[ρ_τ(Y − q)] en q donne
    dE/dq = −τ · P(Y > q) + (1 − τ) · P(Y < q) = 0   ⇔   P(Y < q) = τ.
La prévision optimale est donc le quantile τ de l'occupation : avec τ = 0,9, la réalité ne
dépasse la prévision que 10 % du temps.
Dérivée :  r > 0 : ∂ρ/∂f = −τ     r < 0 : ∂ρ/∂f = 1 − τ.
Lien avec le coût clinique (protocole 3.3, Document 5 § 6.3) :
    τ = c(pénurie) / (c(pénurie) + c(surcapacité)).
Une sous-estimation coûte τ par lit, une surestimation 1 − τ : avec τ = 0,8, manquer un lit
« coûte » 4 fois plus qu'en réserver un de trop.


3. Perte pinball ε-insensible  (SVR quantile révisé, niveau 3 — brique 1)
-------------------------------------------------------------------------
Combinaison des deux : un tube de tolérance ε, et une pente asymétrique hors du tube.
    L_{τ,ε}(r) = τ · max(0, r − ε) + (1 − τ) · max(0, −r − ε)
Dérivée :
    r >  ε :  ∂L/∂f = −τ
    r < −ε :  ∂L/∂f = 1 − τ
    sinon  :  0
Avec ε = 0 on retrouve la pinball ; avec τ = 1/2 on retrouve ½ · L_ε (symétrique).

ATTENTION — le tube déforme le quantile. En refaisant le calcul du § 2 avec le tube, la
prévision optimale q vérifie
    τ · P(Y > q + ε) = (1 − τ) · P(Y < q − ε)
et non plus P(Y < q) = τ : les jours à moins de ε de q ne « votent » plus. Pour une
occupation qui varie de quelques lits, un ε d'un lit suffit à rendre l'intervalle trop étroit
(vérifié : couverture de 81 % au lieu de 90 % avec ε = 1, de 90,7 % avec ε = 0). Pour un
intervalle de prévision calibré, on prend donc ε = 0 (ou un ε choisi par validation sur la
perte pinball et la couverture, jamais fixé a priori).


4. Perte hinge  (SVM de classification — module triage, plus tard)
------------------------------------------------------------------
Pour une étiquette y ∈ {−1, +1} et un score f :  m = y f  (marge),
    L(m) = max(0, 1 − m),   ∂L/∂f = −y · 1{m < 1}.
Coût asymétrique : on multiplie la perte d'un patient grave par C₊ et celle d'un non grave par C₋.
"""
from __future__ import annotations

import torch


def epsilon_insensible(y: torch.Tensor, f: torch.Tensor, epsilon: float) -> tuple[torch.Tensor, torch.Tensor]:
    """L = max(0, |y − f| − ε)  et  ∂L/∂f = −signe(r)·1{|r| > ε}."""
    r = y - f
    valeur = torch.clamp(r.abs() - epsilon, min=0.0)
    gradient = -torch.sign(r) * (r.abs() > epsilon).to(f.dtype)
    return valeur, gradient


def pinball(y: torch.Tensor, f: torch.Tensor, tau: float) -> tuple[torch.Tensor, torch.Tensor]:
    """ρ_τ(r) = max(τ r, (τ − 1) r)  et  ∂ρ/∂f = −τ si r > 0, 1 − τ si r < 0, 0 si r = 0."""
    _verifier_tau(tau)
    r = y - f
    valeur = torch.maximum(tau * r, (tau - 1.0) * r)
    gradient = torch.where(r > 0, torch.full_like(r, -tau),
                           torch.where(r < 0, torch.full_like(r, 1.0 - tau), torch.zeros_like(r)))
    return valeur, gradient


def pinball_epsilon(y: torch.Tensor, f: torch.Tensor, tau: float, epsilon: float) -> tuple[torch.Tensor, torch.Tensor]:
    """L = τ·max(0, r − ε) + (1 − τ)·max(0, −r − ε)  et sa dérivée par rapport à f."""
    _verifier_tau(tau)
    r = y - f
    valeur = tau * torch.clamp(r - epsilon, min=0.0) + (1.0 - tau) * torch.clamp(-r - epsilon, min=0.0)
    gradient = torch.where(r > epsilon, torch.full_like(r, -tau),
                           torch.where(r < -epsilon, torch.full_like(r, 1.0 - tau), torch.zeros_like(r)))
    return valeur, gradient


def hinge(y: torch.Tensor, f: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Classification, y ∈ {−1, +1} :  L = max(0, 1 − y f),  ∂L/∂f = −y·1{y f < 1}."""
    m = y * f
    return torch.clamp(1.0 - m, min=0.0), -y * (m < 1).to(f.dtype)


def tau_depuis_couts(cout_penurie: float, cout_surcapacite: float) -> float:
    """τ = c(pénurie) / (c(pénurie) + c(surcapacité))  — protocole 3.3."""
    if cout_penurie <= 0 or cout_surcapacite <= 0:
        raise ValueError("Les deux coûts doivent être strictement positifs.")
    return cout_penurie / (cout_penurie + cout_surcapacite)


def _verifier_tau(tau: float) -> None:
    if not 0.0 < tau < 1.0:
        raise ValueError(f"τ doit être strictement entre 0 et 1 (reçu {tau}).")
