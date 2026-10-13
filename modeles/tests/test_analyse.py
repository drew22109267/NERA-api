"""Statistiques codées à la main (svr/analyse.py) : cas vérifiables à la main."""
import torch
import pytest

from svr import analyse as A

T = torch.float64


def test_pearson_droites_et_constante():
    x = torch.arange(10, dtype=T)
    X = torch.stack([x, 2 * x + 3, -x, torch.ones(10, dtype=T)], dim=1)
    R = A.matrice_pearson(X)
    assert R[0, 1] == pytest.approx(1.0) and R[0, 2] == pytest.approx(-1.0)   # droites croissante / décroissante
    assert torch.isnan(R[3, 0]) and torch.isnan(R[0, 3])                     # colonne constante : non définie
    assert torch.allclose(torch.diagonal(R)[:3], torch.ones(3, dtype=T))


def test_pearson_formule_a_la_main():
    a = torch.tensor([1.0, 2.0, 4.0, 7.0], dtype=T)
    b = torch.tensor([2.0, 1.0, 5.0, 6.0], dtype=T)
    ca, cb = a - a.mean(), b - b.mean()
    r = (ca * cb).sum() / torch.sqrt((ca ** 2).sum() * (cb ** 2).sum())
    assert A.matrice_pearson(torch.stack([a, b], dim=1))[0, 1] == pytest.approx(float(r))


def test_rangs_ex_aequo():
    assert A.rangs(torch.tensor([10.0, 30.0, 20.0, 30.0])).tolist() == [1.0, 3.5, 2.0, 3.5]


def test_spearman_invariant_par_transformation_croissante():
    x = torch.tensor([0.3, 1.2, 2.5, 3.1, 4.8, 6.0], dtype=T)
    S = A.matrice_spearman(torch.stack([x, x ** 3], dim=1))
    assert S[0, 1] == pytest.approx(1.0)                                       # Spearman = 1 même si la relation est courbe
    assert A.matrice_pearson(torch.stack([x, x ** 3], dim=1))[0, 1] < 1.0


def test_acf_et_pacf():
    x = torch.tensor([1.0, 3.0, 2.0, 5.0, 4.0, 6.0], dtype=T)
    c = x - x.mean()
    rho1 = (c[:-1] * c[1:]).sum() / (c * c).sum()
    rho = A.acf(x, 3)
    assert rho[0] == pytest.approx(1.0) and rho[1] == pytest.approx(float(rho1))
    phi = A.pacf(x, 3)
    assert phi[1] == pytest.approx(float(rho[1]))                               # φ₁₁ = ρ(1)
    phi22 = (rho[2] - rho[1] ** 2) / (1 - rho[1] ** 2)                           # formule fermée pour k = 2
    assert phi[2] == pytest.approx(float(phi22))


def test_calibration_et_profils():
    y = torch.tensor([1.0, 2.0, 3.0, 4.0], dtype=T)
    cal = A.calibration_quantiles(y, {0.5: torch.full((4,), 2.5, dtype=T)})
    assert cal[0.5] == 0.5                                                      # 2 jours sur 4 sous 2,5
    m, s = A.moyenne_par_groupe(y, torch.tensor([0, 0, 1, 1]), 3)
    assert m[:2].tolist() == [1.5, 3.5] and torch.isnan(m[2])
