"""
Vérification du code des modèles, sur de petits cas calculés à la main ou construits pour le test
(ce ne sont pas des données de l'étude).

Vérification des gradients par différences finies centrées :
    ∂J/∂θ_k ≈ [J(θ + δ e_k) − J(θ − δ e_k)] / (2δ)
Si le gradient écrit à la main est juste, les deux coïncident (à ~1e-6 près). On place les
paramètres loin des « coins » des pertes, où la dérivée n'existe pas.

Lancer :  ~/memoire-env/bin/python -m pytest tests -q
"""
import math

import pandas as pd
import pytest
import torch

from svr import metriques as M
from svr import pertes as P
from svr import references as R
from svr.caracteristiques import Standardiseur, construire
from svr.empilement import Empilement
from svr.modeles import Entrainement, Perte, SVRLineaire, SVRNoyau, SVRNoyauComposite
from svr.noyaux import NoyauComposite, NoyauRBF, distances_carrees, rbf
from svr.optimiseurs import Adam, DescenteGradient, Momentum
from svr.recherche import Dimension, essaim_particulaire, recherche_grille
from svr.validation import decoupage_final, decoupages_test_mensuels, origines_glissantes

T = torch.float64
GEN = torch.Generator().manual_seed(7)


def aleatoire(*forme):
    return torch.randn(*forme, generator=GEN, dtype=T)


# ── Pertes ────────────────────────────────────────────────────────────────

def test_epsilon_insensible_exemple_du_cours():
    y = torch.tensor([10.0, 10.0, 10.0], dtype=T)
    f = torch.tensor([10.5, 12.0, 7.0], dtype=T)
    v, g = P.epsilon_insensible(y, f, 1.0)
    assert v.tolist() == [0.0, 1.0, 2.0]
    assert g.tolist() == [0.0, 1.0, -1.0]          # surestimation → +1, sous-estimation → −1


def test_pinball_et_sa_version_epsilon():
    y, f = torch.tensor([10.0, 10.0], dtype=T), torch.tensor([8.0, 13.0], dtype=T)   # r = +2, −3
    v, g = P.pinball(y, f, 0.8)
    assert v.tolist() == pytest.approx([1.6, 0.6]) and g.tolist() == pytest.approx([-0.8, 0.2])
    v, g = P.pinball_epsilon(y, f, 0.8, 1.0)
    assert v.tolist() == pytest.approx([0.8, 0.4]) and g.tolist() == pytest.approx([-0.8, 0.2])


def test_tau_depuis_couts():
    assert P.tau_depuis_couts(4, 1) == pytest.approx(0.8)


def test_pinball_donne_le_quantile():
    # Minimiser la perte pinball moyenne sur une constante q donne le quantile τ de l'échantillon.
    y = torch.arange(1, 101, dtype=T)
    qs = torch.linspace(0, 101, 10101, dtype=T)
    pertes = torch.stack([P.pinball(y, torch.full_like(y, q), 0.9)[0].mean() for q in qs])
    assert float(qs[torch.argmin(pertes)]) == pytest.approx(90.0, abs=1.0)


# ── Exercice de la leçon : f(x) = x, ε = 1, C = 1 → J = 4,5 ───────────────

def test_exercice_de_la_lecon():
    X = torch.tensor([[10.0], [12.0], [11.0]], dtype=T)
    y = torch.tensor([12.0, 11.0, 15.0], dtype=T)
    m = SVRLineaire(C=1.0, perte=Perte("epsilon", 1.0))
    m.X, m.parametres = X, {"w": torch.tensor([1.0], dtype=T), "b": torch.tensor([0.0], dtype=T)}
    J, grads, _ = m.objectif_et_gradients(y)
    assert J == pytest.approx(4.5)                   # ½·1² + (1 + 0 + 3)
    # Jours 1 et 3 sous-estimés (g = −1), jour 2 sur le bord du tube (g = 0) :
    assert float(grads["w"][0]) == pytest.approx(1 - (10 + 11))   # w + C Σ g x
    assert float(grads["b"][0]) == pytest.approx(-2)


# ── Gradients écrits à la main contre différences finies ──────────────────

def differences_finies(modele, y, nom, delta=1e-6):
    p = modele.parametres[nom]
    estime = torch.zeros_like(p)
    for k in range(p.numel()):
        p.view(-1)[k] += delta
        jp, _, _ = modele.objectif_et_gradients(y)
        p.view(-1)[k] -= 2 * delta
        jm, _, _ = modele.objectif_et_gradients(y)
        p.view(-1)[k] += delta
        estime.view(-1)[k] = (jp - jm) / (2 * delta)
    return estime


@pytest.mark.parametrize("perte", [Perte("epsilon", 0.3), Perte("pinball", tau=0.8), Perte("pinball_epsilon", 0.3, 0.7)])
def test_gradient_svr_lineaire(perte):
    X, y = aleatoire(20, 4), aleatoire(20) * 5
    m = SVRLineaire(C=2.0, perte=perte)
    m.X, m.parametres = X, {"w": aleatoire(4), "b": aleatoire(1)}
    _, grads, _ = m.objectif_et_gradients(y)
    for nom in ("w", "b"):
        assert torch.allclose(grads[nom], differences_finies(m, y, nom), atol=1e-5)


@pytest.mark.parametrize("perte", [Perte("epsilon", 0.3), Perte("pinball_epsilon", 0.3, 0.8)])
def test_gradient_svr_noyau(perte):
    X, y = aleatoire(15, 3), aleatoire(15) * 3
    m = SVRNoyau(NoyauRBF(0.5), C=1.5, perte=perte)
    m._initialiser(X, y)
    m.parametres = {"alpha": aleatoire(15) * 0.3, "b": aleatoire(1)}
    exact = m.gradient_exact(y)
    for nom in ("alpha", "b"):
        assert torch.allclose(exact[nom], differences_finies(m, y, nom), atol=1e-5)


def test_gradient_noyau_composite_y_compris_beta():
    X, y = aleatoire(15, 5), aleatoire(15) * 3
    m = SVRNoyauComposite(NoyauComposite([0, 1], [2, 3, 4], 0.4, 0.8), C=1.0, perte=Perte("pinball_epsilon", 0.2, 0.75))
    m._initialiser(X, y)
    m.parametres = {"alpha": aleatoire(15) * 0.3, "b": aleatoire(1), "theta": torch.tensor([0.4], dtype=T)}
    exact = m.gradient_exact(y)
    for nom in ("alpha", "b", "theta"):
        assert torch.allclose(exact[nom], differences_finies(m, y, nom), atol=1e-5)


def test_gradient_empilement():
    Pm, y = aleatoire(25, 3) * 4 + 20, aleatoire(25) * 4 + 20
    m = Empilement(lambda_=0.1, C=1.0, perte=Perte("pinball", tau=0.6))
    m._initialiser(Pm, y)
    m.parametres = {"u": aleatoire(3), "b": aleatoire(1)}
    _, grads, _ = m.objectif_et_gradients(y)
    for nom in ("u", "b"):
        assert torch.allclose(grads[nom], differences_finies(m, y, nom), atol=1e-5)


# ── Noyaux ────────────────────────────────────────────────────────────────

def test_distances_et_rbf():
    X = torch.tensor([[0.0, 0.0], [3.0, 4.0]], dtype=T)
    assert distances_carrees(X, X).tolist() == [[0.0, 25.0], [25.0, 0.0]]
    K = rbf(X, X, 0.1)
    assert torch.allclose(torch.diag(K), torch.ones(2, dtype=T)) and float(K[0, 1]) == pytest.approx(math.exp(-2.5))


# ── Optimiseurs ───────────────────────────────────────────────────────────

def test_premier_pas_adam():
    # Au premier pas, m̂ = g et v̂ = g² : θ₁ = θ₀ − η · g/(|g| + ε) ≈ θ₀ − η · signe(g).
    p, opt = {"x": torch.tensor([1.0, -2.0], dtype=T)}, Adam(taux=0.1)
    opt.pas(p, {"x": torch.tensor([3.0, -0.5], dtype=T)})
    assert p["x"].tolist() == pytest.approx([0.9, -1.9], abs=1e-6)


@pytest.mark.parametrize("opt", [DescenteGradient(0.1), Momentum(0.05), Adam(0.1, decroissance=200)])
def test_optimiseurs_minimisent_un_bol(opt):
    # J(x) = ½ ‖x − c‖², gradient x − c : le minimum est c.
    c = torch.tensor([3.0, -1.0], dtype=T)
    p = {"x": torch.zeros(2, dtype=T)}
    for _ in range(2000):
        opt.pas(p, {"x": p["x"] - c})
    assert torch.allclose(p["x"], c, atol=1e-3)


def test_entrainement_retrouve_une_droite():
    # y = 2x + 1 exactement : le SVR linéaire (C grand, ε petit) doit retrouver w ≈ 2, b ≈ 1.
    X = torch.linspace(-2, 2, 41, dtype=T).reshape(-1, 1)
    y = 2 * X[:, 0] + 1
    m = SVRLineaire(C=100.0, perte=Perte("epsilon", 0.01), entrainement=Entrainement(taux=0.05, iterations=6000))
    m.entrainer(X, y)
    assert float(m.parametres["w"][0]) == pytest.approx(2.0, abs=0.05)
    assert float(m.parametres["b"][0]) == pytest.approx(1.0, abs=0.05)


# ── Métriques ─────────────────────────────────────────────────────────────

def test_metriques_a_la_main():
    y, yp = [10, 20, 30], [12, 18, 33]
    assert M.mae(y, yp) == pytest.approx(7 / 3)
    assert M.rmse(y, yp) == pytest.approx(math.sqrt((4 + 4 + 9) / 3))
    assert M.mape(y, yp) == pytest.approx(100 * (0.2 + 0.1 + 0.1) / 3)
    assert M.couverture([5, 6, 7, 8], [4, 6, 8, 0], [6, 7, 9, 9]) == pytest.approx(0.75)
    assert M.phi(0.0) == pytest.approx(0.5) and M.phi(1.96) == pytest.approx(0.975, abs=1e-3)


def test_diebold_mariano_detecte_le_meilleur():
    y = aleatoire(200) * 3 + 20
    bon, mauvais = y + aleatoire(200) * 0.5, y + aleatoire(200) * 3
    r = M.diebold_mariano(y, bon, mauvais, h=1)
    assert r["plus_precis"] == "A" and r["significatif_5pc"]


# ── Variables, validation sans fuite ─────────────────────────────────────

def petite_serie(jours=300):
    """Série construite pour le test (forme hebdomadaire + saison), pas des données de l'étude."""
    idx = pd.date_range("2025-01-01", periods=jours, freq="D")
    t = torch.arange(jours, dtype=T)
    presents = (20 + 3 * torch.sin(2 * math.pi * t / 7) + 5 * torch.sin(2 * math.pi * t / 365)).round()
    return pd.DataFrame({"presents": presents.int().numpy(), "admissions": 4, "sorties_sortie": 4}, index=idx)


def test_variables_sans_fuite():
    occ = petite_serie()
    tab = construire(occ, h=3)
    i = 10
    t = int(tab.origines[i])
    assert float(tab.X[i, 0]) == occ["presents"].iloc[t]          # occ_j-0 = jour t
    assert float(tab.X[i, 6]) == occ["presents"].iloc[t - 6]      # occ_j-6
    assert float(tab.y[i]) == occ["presents"].iloc[t + 3]         # cible = t + h
    assert (tab.dates_cible - tab.dates_origine).days.unique().tolist() == [3]


def test_validation_glissante_respecte_le_temps():
    tab = construire(petite_serie(), h=7)
    for d in origines_glissantes(tab, "2025-08-01", "2025-10-15", pas=14):
        assert tab.dates_cible[d.entrainement.numpy()].max() <= d.origine            # cibles connues à l'origine
        assert tab.dates_origine[d.evaluation.numpy()].min() >= d.origine
    final = decoupage_final(tab, "2025-10-01")
    assert tab.dates_cible[final.entrainement.numpy()].max() < pd.Timestamp("2025-10-01")


def test_test_final_mensuel_reentraine_chaque_mois():
    tab = construire(petite_serie(), h=7)
    blocs = decoupages_test_mensuels(tab, "2025-09-01")
    assert [b.origine for b in blocs][:2] == [pd.Timestamp("2025-09-01"), pd.Timestamp("2025-10-01")]
    # Premier mois : exactement le découpage final classique (rien du test n'est connu).
    assert torch.equal(blocs[0].entrainement, decoupage_final(tab, "2025-09-01").entrainement)
    for b in blocs:
        debut, fin = b.origine, b.origine + pd.DateOffset(months=1)
        assert tab.dates_cible[b.entrainement.numpy()].max() < debut                 # aucune cible future
        o = tab.dates_origine[b.evaluation.numpy()]
        assert o.min() >= debut and o.max() < fin                                    # un mois par bloc
    # Le mois suivant apprend aussi sur le mois de test écoulé.
    assert len(blocs[1].entrainement) > len(blocs[0].entrainement)
    # Les blocs couvrent tout le test, sans recouvrement.
    tous = torch.cat([b.evaluation for b in blocs])
    assert len(tous) == len(set(tous.tolist())) == len(decoupage_final(tab, "2025-09-01").evaluation)


def test_standardiseur_appris_sur_l_entrainement_seulement():
    X = torch.tensor([[1.0, 0.0], [3.0, 1.0], [100.0, 0.0]], dtype=T)
    s = Standardiseur([0]).ajuster(X[:2])
    Z = s.transformer(X)
    assert Z[:2, 0].tolist() == [-1.0, 1.0] and Z[:, 1].tolist() == [0.0, 1.0, 0.0]


def test_references():
    serie = torch.arange(30, dtype=T)
    orig = torch.tensor([20, 25])
    assert R.persistance(serie, orig, 3).tolist() == [20.0, 25.0]
    assert R.moyenne_mobile(serie, orig, 1, k=3).tolist() == [19.0, 24.0]
    assert R.saisonniere(serie, orig, 1, semaines=2).tolist() == [(14 + 7) / 2, (19 + 12) / 2]


# ── Recherche d'hyperparamètres ───────────────────────────────────────────

def test_grille_et_essaim_trouvent_le_minimum():
    f = lambda c: (math.log10(c["C"]) - 0.5) ** 2 + (c["e"] - 1.2) ** 2
    g = recherche_grille({"C": [1, 3.16, 10], "e": [0.0, 1.2, 2.0]}, f)["meilleur"]
    assert g["C"] == 3.16 and g["e"] == 1.2
    p = essaim_particulaire({"C": Dimension(0.1, 100, "log"), "e": Dimension(0, 3)}, f, particules=10, iterations=40)["meilleur"]
    assert math.log10(p["C"]) == pytest.approx(0.5, abs=0.05) and p["e"] == pytest.approx(1.2, abs=0.05)
