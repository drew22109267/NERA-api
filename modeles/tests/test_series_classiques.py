"""Modèles de référence sur la série (svr/series_classiques.py) : cas exacts et absence de fuite."""
import math

import torch

from svr import series_classiques as SC


def test_nelder_mead_trouve_le_minimum():
    x, v = SC.nelder_mead(lambda u: (u[0] - 3) ** 2 + 2 * (u[1] + 1) ** 2, [0.0, 0.0], iterations=2000, tol=1e-14)
    assert abs(x[0] - 3) < 1e-4 and abs(x[1] + 1) < 1e-4 and v < 1e-7


def test_lissage_simple_serie_constante():
    y = [5.0] * 40
    m = SC.LissageSimple().ajuster(y)
    assert m.prevoir(y, [20, 39], 3) == [5.0, 5.0]


def test_holt_lineaire_retrouve_une_droite():
    y = [2.0 + 0.5 * t for t in range(60)]
    m = SC.HoltLineaire().ajuster(y)
    p = m.prevoir(y, [40, 59], 4)
    assert abs(p[0] - y[44]) < 1e-3 and abs(p[1] - (2.0 + 0.5 * 63)) < 1e-3


def test_holt_winters_retrouve_une_semaine_exacte():
    motif = [10, 12, 15, 14, 11, 8, 9]
    y = [float(motif[t % 7]) for t in range(10 * 7)]
    m = SC.HoltWintersAdditif().ajuster(y)
    for h in (1, 3, 7, 9):
        assert abs(m.prevoir(y, [60], h)[0] - motif[(60 + h) % 7]) < 1e-2


def test_ar_retrouve_les_coefficients():
    g = torch.Generator().manual_seed(0)                       # bruit de test, graine fixe
    bruit = torch.randn(1500, generator=g, dtype=torch.float64).tolist()
    y = [4.0]
    for e in bruit:
        y.append(2.0 + 0.5 * y[-1] + e)                         # AR(1) : c = 2, a = 0,5
    m = SC.AR(pmax=1).ajuster(y)
    assert m.p == 1 and abs(m.coef[1] - 0.5) < 0.05 and abs(m.coef[0] - 2.0) < 0.25


def test_aucune_fuite_du_futur():
    """La prévision faite au jour t ne change pas si l'on modifie les jours après t."""
    base = [20 + 3 * math.sin(2 * math.pi * t / 7) + 0.05 * t for t in range(120)]
    modifiee = base[:91] + [v + 50 for v in base[91:]]
    blocs = [[80, 81, 82, 83], [84, 85, 86, 87, 88, 89, 90]]
    for nom, fab in SC.modeles_de_reference(SC.OrdreSarima(1, 0, 0)).items():
        a = SC.evaluer_serie(fab, torch.tensor(base), blocs, h=3)
        b = SC.evaluer_serie(fab, torch.tensor(modifiee), blocs, h=3)
        for tau in a:
            assert torch.allclose(a[tau], b[tau]), nom


def test_quantiles_ordonnes():
    y = torch.tensor([20 + 3 * math.sin(2 * math.pi * t / 7) + (t % 5) for t in range(150)], dtype=torch.float64)
    r = SC.evaluer_serie(SC.LissageSimple, y, [[100, 101, 102], [103, 104]], h=2)
    assert bool((r[0.05] <= r[0.8]).all()) and bool((r[0.8] <= r[0.95]).all())


def test_sarima_ar1_et_choix_d_ordre():
    g = torch.Generator().manual_seed(1)
    y = [7.5]
    for e in torch.randn(400, generator=g, dtype=torch.float64).tolist():
        y.append(3.0 + 0.6 * y[-1] + e)                         # AR(1) : φ = 0,6, moyenne 7,5
    m = SC.Sarima(SC.OrdreSarima(1, 0, 0)).ajuster(y)
    assert abs(math.tanh(m.u[0]) - 0.6) < 0.1
    ordre, essais = SC.choisir_ordre_sarima(y, grille=SC.GRILLE_SARIMA[:6])
    assert isinstance(ordre, SC.OrdreSarima) and len(essais) >= 1
