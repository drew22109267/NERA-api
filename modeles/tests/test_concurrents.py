"""Concurrents du SVR (svr/concurrents.py) : gradients par différences finies, cas exacts, interface."""
import math

import torch

from svr import concurrents as C

T = torch.float64


def _donnees(n=120, p=4, graine=0):
    g = torch.Generator().manual_seed(graine)                  # données de test, graine fixe
    X = torch.randn(n, p, generator=g, dtype=T)
    y = 2 * X[:, 0] - X[:, 1] + 0.3 * torch.randn(n, generator=g, dtype=T)
    return X, y


def _verifier_gradients(modele, X, y, eps=1e-6, tol=1e-5):
    gen = torch.Generator().manual_seed(3)
    P = modele._initialiser(X.shape[1], gen)
    for nom in P:                                               # petite perturbation : évite les points anguleux
        P[nom] = P[nom] + 0.01 * torch.randn(P[nom].shape, generator=gen, dtype=T)
    _, grads = modele.objectif_et_gradients(X, y, P)
    for nom, v in P.items():
        plat = v.reshape(-1)
        for k in range(0, plat.numel(), max(1, plat.numel() // 7)):
            orig = float(plat[k])
            plat[k] = orig + eps; jp, _ = modele.objectif_et_gradients(X, y, P)
            plat[k] = orig - eps; jm, _ = modele.objectif_et_gradients(X, y, P)
            plat[k] = orig
            num = (jp - jm) / (2 * eps)
            assert abs(num - float(grads[nom].reshape(-1)[k])) < tol * (1 + abs(num)), (nom, k, num)


def test_gradients_mlp_par_differences_finies():
    X, y = _donnees(40, 3)
    _verifier_gradients(C.PerceptronQuantile(couches=(5, 4), lambda_=1e-2), X, y)


def test_gradients_lstm_par_differences_finies():
    X, y = _donnees(30, 5)                                      # 3 retards + 2 variables exogènes
    _verifier_gradients(C.LSTMQuantile(retards=3, cache=4, lambda_=1e-2), X, y)


def test_arbre_retrouve_une_marche():
    X = torch.linspace(0, 1, 100, dtype=T)[:, None]
    y = torch.where(X[:, 0] <= 0.5, torch.tensor(1.0, dtype=T), torch.tensor(5.0, dtype=T))
    a = C.Arbre(profondeur_max=3, min_feuille=5).construire(X, y)
    p = a.predire(torch.tensor([[0.2], [0.8]], dtype=T))
    assert torch.allclose(p, torch.tensor([1.0, 5.0], dtype=T))


def test_foret_quantiles_ordonnes_et_plausibles():
    X, y = _donnees(150, 3)
    f = C.ForetAleatoireQuantile(taus=(0.05, 0.5, 0.95), arbres=40).entrainer(X, y)
    q = f.predire(X[:20])
    assert bool((q[0.05] <= q[0.5]).all()) and bool((q[0.5] <= q[0.95]).all())
    couverture = float(((y[:20] >= q[0.05]) & (y[:20] <= q[0.95])).to(T).mean())
    assert couverture >= 0.8                                      # sur l'entraînement, l'intervalle couvre


def test_boosting_fait_baisser_la_perte():
    X, y = _donnees(150, 3)
    m0 = C.GradientBoostingQuantile(tau=0.5, etapes=1, taux=0.1).entrainer(X, y)
    m1 = C.GradientBoostingQuantile(tau=0.5, etapes=150, taux=0.1).entrainer(X, y)
    t = torch.tensor([0.5], dtype=T)
    p0, _ = C.pinball_et_gradient(y, m0.predire(X)[:, None], t)
    p1, _ = C.pinball_et_gradient(y, m1.predire(X)[:, None], t)
    assert p1 < 0.5 * p0


def test_interface_commune_et_tri():
    X, y = _donnees(80, 9)
    hp = C.HyperConcurrents(arbres=10, etapes=20, epoques=60, patience=20, graines=1)
    for nom in C.CONCURRENTS:
        m = C.fabrique_concurrent(nom, hp, retards=7)().entrainer(X, y)
        q = m.predire(X[:10])
        assert set(q) == set(hp.quantiles()), nom
        cles = sorted(q)
        for a, b in zip(cles, cles[1:]):
            assert bool((q[a] <= q[b]).all()), nom              # pas de croisement des quantiles
        assert all(bool(torch.isfinite(v).all()) for v in q.values()), nom
