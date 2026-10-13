"""Moyenne de Polyak, classifieur SVM, Platt, survie J0/J1/J2 et conversion en taux : cas vérifiables."""
import math

import pandas as pd
import pytest
import torch

from svr import survie as S
from svr.classification import CalibrationPlatt, SVMLineaireClassifieur, auc, brier
from svr.modeles import Entrainement, Perte, SVRLineaire
from svr.niveaux import Hyperparametres
from transfert import hp_en_taux

T = torch.float64


def test_polyak_meme_apres_un_arret_anticipe():
    # Problème simple qui s'arrête bien avant la moitié des pas : la moyenne des derniers points est essayée.
    X = torch.linspace(-1, 1, 50, dtype=T)[:, None]
    y = 2 * X[:, 0] + 1
    m = SVRLineaire(C=1.0, perte=Perte("epsilon", 0.1), entrainement=Entrainement(iterations=20000, moyenne_polyak=0.5))
    m.entrainer(X, y)
    assert len(m.historique) < 10000                                    # arrêt anticipé, avant le début prévu de la moyenne
    assert m.origine_solution in ("meilleur point rencontré",) or m.origine_solution.startswith("moyenne de Polyak sur 100")
    assert m.objectif_final <= min(m.historique) + 1e-12              # jamais pire que le meilleur point visité


def test_gradient_du_svm_par_differences_finies():
    g = torch.Generator().manual_seed(0)
    X = torch.randn(30, 3, generator=g, dtype=T)
    y = torch.where(X[:, 0] + 0.3 * torch.randn(30, generator=g, dtype=T) > 0, 1.0, -1.0).to(T)
    m = SVMLineaireClassifieur(3.0, 1.0)
    m.poids = torch.rand(30, generator=g, dtype=T) + 0.5
    m.C_exemple = m.poids * torch.where(y > 0, 3.0, 1.0).to(T)
    m._initialiser(X, y)
    m.parametres = {"w": torch.randn(3, generator=g, dtype=T) * 0.3, "b": torch.tensor([0.1], dtype=T)}
    J, grad, _ = m.objectif_et_gradients(y)
    h = 1e-6
    for nom in ("w", "b"):
        for i in range(len(m.parametres[nom])):
            m.parametres[nom][i] += h; Jp, _, _ = m.objectif_et_gradients(y)
            m.parametres[nom][i] -= 2 * h; Jm, _, _ = m.objectif_et_gradients(y)
            m.parametres[nom][i] += h
            assert (Jp - Jm) / (2 * h) == pytest.approx(float(grad[nom][i]), abs=1e-4)


def test_platt_retrouve_la_sigmoide():
    g = torch.Generator().manual_seed(1)
    s = torch.randn(20000, generator=g, dtype=T)
    p = 1 / (1 + torch.exp(-2.0 * s + 0.5))                             # vrais A = −2, B = 0,5
    y = (torch.rand(20000, generator=g, dtype=T) < p).to(T)
    c = CalibrationPlatt(iterations=4000).ajuster(s, y)
    assert c.A == pytest.approx(-2.0, abs=0.15) and c.B == pytest.approx(0.5, abs=0.15)


def test_auc_et_brier_a_la_main():
    assert auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)   # 3 paires bien rangées sur 4
    assert auc([0.5, 0.5], [0, 1]) == pytest.approx(0.5)                     # ex æquo : moitié
    assert brier([0.2, 0.9], [0, 1]) == pytest.approx((0.04 + 0.01) / 2)


def test_gamma_incomplete():
    for x in (0.3, 1.0, 4.0, 12.0):                                     # forme 1 = loi exponentielle
        assert S.gamma_incomplete_reguliere(1.0, x) == pytest.approx(1 - math.exp(-x), abs=1e-12)
    for a, x in ((2.5, 3.0), (2.5, 8.0), (4.0, 1.5)):                    # P(a+1, x) = P(a, x) − xᵃe⁻ˣ/Γ(a+1)
        gauche = S.gamma_incomplete_reguliere(a + 1, x)
        droite = S.gamma_incomplete_reguliere(a, x) - math.exp(a * math.log(x) - x - math.lgamma(a + 1))
        assert gauche == pytest.approx(droite, abs=1e-10)


def test_lignes_patient_jour_et_table_de_survie():
    sejours = pd.DataFrame({
        "entree": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-05"]),
        "sortie": pd.to_datetime(["2026-01-04", "2026-01-04", None]),
        "sortie_basse": pd.to_datetime(["2026-01-04", "2026-01-03", None]),
        "statut": ["observee", "calculee", "censuree"], "p_inclusif": [0.0, 0.4, 0.0], "issue": ["Sortie", "Décès", None]})
    L = S.lignes_patient_jour(sejours, "2026-01-08")
    a = L[L["sejour"] == 0]
    assert a["k"].tolist() == [0, 1, 2, 3] and a["evenement"].tolist() == [0, 0, 0, 1]
    b = L[L["sejour"] == 1]                                             # sortie au jour 2 (p = 0,4) ou 3 (0,6)
    assert b[["k", "evenement", "poids"]].values.tolist() == [[0, 0, 1.0], [1, 0, 1.0], [2, 1, 0.4], [2, 0, 0.6], [3, 1, 0.6]]
    assert b["cause"].dropna().unique().tolist() == ["décès"]
    c = L[L["sejour"] == 2]                                             # censuré : présent les 5, 6, 7 sans sortie
    assert c["k"].tolist() == [0, 1, 2] and c["evenement"].sum() == 0
    h = S.table_de_survie(L, k_max=5)
    assert float(h[2]) == pytest.approx(0.4 / 3.0)                      # 0,4 sortie pour 1 + 1 + 1 présents pondérés à k = 2
    assert float(h[3]) == pytest.approx((1 + 0.6) / (1 + 0.6))


def test_probabilites_j012_hasard_constant():
    presents = pd.DataFrame({"sejour": [0], "k": [2], "jour": pd.to_datetime(["2026-01-03"])})
    P = S.probabilites_j012(lambda L: torch.full((len(L),), 0.5, dtype=T), presents)
    assert P[0].tolist() == [0.5, 0.25, 0.125]


def test_conversion_des_hyperparametres_en_taux():
    hp = hp_en_taux(Hyperparametres(C=2.0, epsilon=1.0, epsilon_quantile=0.0), 20)
    assert hp.C == pytest.approx(0.1) and hp.epsilon == pytest.approx(0.05) and hp.gamma == Hyperparametres().gamma
