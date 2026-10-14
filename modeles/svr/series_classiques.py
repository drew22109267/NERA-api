r"""
Modèles de prévision de référence sur la série seule, écrits à la main : lissages exponentiels, méthode
Thêta, AR(p), SARIMA. Ce sont les mêmes modèles que l'outil de saisie (outil-saisie/statistiques.js),
réécrits ici pour le banc de comparaison, avec le MÊME protocole que les SVR.

Protocole (équitable avec les SVR)
----------------------------------
Pour chaque découpage de la validation glissante (origine O, bloc d'origines t ∈ [O, O + pas[) :
  1. les paramètres sont estimés sur y_0 … y_O seulement (ce qui est connu le soir du jour O) ;
  2. pour chaque origine t du bloc, l'état du modèle (niveau, tendance, saisons, innovations) est mis à
     jour avec y_0 … y_t — rien du futur —, puis on prévoit y_{t+h}.
Les paramètres sont donc réestimés à chaque origine de la validation glissante, comme les SVR sont
réentraînés.

Estimation : somme des carrés des erreurs à un pas, SSE = Σ_t (y_t − ŷ_{t|t−1})², minimisée par le
simplexe de Nelder-Mead. Les paramètres de lissage α, β, γ ∈ ]0, 1[ s'écrivent σ(u) = 1/(1 + e^{−u}) et
l'amortissement φ = 0,8 + 0,18 σ(u) ∈ ]0,8 ; 0,98[ : l'optimisation se fait sans contrainte.

Quantiles et intervalle
-----------------------
Un modèle de référence donne une prévision ponctuelle ŷ. Pour le juger sur la perte pinball au quantile τ
(comme le SVR quantile), on lui ajoute les quantiles empiriques de ses propres erreurs à h jours sur la
période d'apprentissage : q̂_τ = ŷ + Q_τ(e), e_s = y_{s+h} − ŷ_{s+h|s}, s + h ≤ O. Même idée que
l'« intervalle naïf » de la persistance (references.intervalle_persistance).

Modèles
-------
  naïf                ŷ_{t+h} = y_t
  moyenne historique  ŷ_{t+h} = (1/(t+1)) Σ_{s ≤ t} y_s
  lissage simple      l_t = α y_t + (1 − α) l_{t−1} ;  ŷ_{t+h} = l_t
  Holt linéaire       l_t = α y_t + (1 − α)(l_{t−1} + b_{t−1}) ;  b_t = β(l_t − l_{t−1}) + (1 − β) b_{t−1}
                      ŷ_{t+h} = l_t + h b_t
  Holt amorti         idem avec φ :  l_t = α y_t + (1 − α)(l + φb),  b_t = β(l_t − l_{t−1}) + (1 − β) φ b
                      ŷ_{t+h} = l_t + (φ + … + φ^h) b_t
  saisonnier simple   l_t = α(y_t − s_{t−m}) + (1 − α) l_{t−1} ;  s_t = γ(y_t − l_t) + (1 − γ) s_{t−m}
                      ŷ_{t+h} = l_t + s_{t+h−m(k+1)},  k = ⌊(h − 1)/m⌋,  m = 7
  Holt-Winters add.   niveau + tendance amortie + saison additive (voir classiques.py)
  Holt-Winters mult.  la saison multiplie :  ŷ_{t+h} = (l_t + Σ_{j≤h} φ^j b_t) · s_{t+h−m(k+1)}
  Thêta               lissage simple + demi-pente b̂ de la droite des moindres carrés :
                      ŷ_{t+h} = l_t + ½ b̂ (h − 1 + 1/α)   (Hyndman et Billah, 2003)
  AR(p)               y_t = c + Σ_{i=1..p} a_i y_{t−i} + ε_t, moindres carrés, p choisi par
                      AIC = n ln(SCE/n) + 2(p + 1) ; prévision récursive à h pas
  SARIMA              (1 − φ(B))(1 − Φ(B^m))(1 − B)^d (1 − B^m)^D y_t = c + (1 + θ(B))(1 + Θ(B^m)) ε_t
                      estimé par somme conditionnelle des carrés des innovations (CSS) ; paramètres passés
                      par tanh (stationnarité et inversibilité approchées) ; prévision récursive avec
                      innovations futures nulles. Ordre choisi UNE fois, sur l'apprentissage seulement :
                      meilleur BIC à (d, D) fixés, puis départage des (d, D) par l'erreur sur les 20 %
                      finaux de l'apprentissage (jamais sur la validation).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch

TYPE = torch.float64
SIG = lambda u: 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, u))))   # paramètre dans ]0, 1[
PHI = lambda u: 0.8 + 0.18 * SIG(u)                                  # amortissement dans ]0,8 ; 0,98[


# ─────────────────────────────────────────────────────────────────────────────
# Nelder-Mead (identique à statistiques.js)
# ─────────────────────────────────────────────────────────────────────────────
def nelder_mead(f, x0: list[float], pas: float = 0.1, iterations: int = 400, tol: float = 1e-9) -> tuple[list[float], float]:
    """Minimise f sur R^d : réflexion 1, expansion 2, contraction 1/2, réduction 1/2."""
    d = len(x0)
    simplexe = [list(x0)] + [[x0[j] + (pas if j == i else 0.0) for j in range(d)] for i in range(d)]
    valeurs = [f(x) for x in simplexe]
    for _ in range(iterations):
        ordre = sorted(range(d + 1), key=lambda i: valeurs[i])
        simplexe, valeurs = [simplexe[i] for i in ordre], [valeurs[i] for i in ordre]
        if abs(valeurs[-1] - valeurs[0]) < tol * (1 + abs(valeurs[0])):
            break
        c = [sum(simplexe[i][j] for i in range(d)) / d for j in range(d)]
        point = lambda k: [c[j] + k * (simplexe[-1][j] - c[j]) for j in range(d)]
        r = point(-1.0); vr = f(r)
        if vr < valeurs[0]:
            e = point(-2.0); ve = f(e)
            simplexe[-1], valeurs[-1] = (e, ve) if ve < vr else (r, vr)
        elif vr < valeurs[-2]:
            simplexe[-1], valeurs[-1] = r, vr
        else:
            k = point(0.5); vk = f(k)
            if vk < valeurs[-1]:
                simplexe[-1], valeurs[-1] = k, vk
            else:
                for i in range(1, d + 1):
                    simplexe[i] = [simplexe[0][j] + 0.5 * (simplexe[i][j] - simplexe[0][j]) for j in range(d)]
                    valeurs[i] = f(simplexe[i])
    i = min(range(d + 1), key=lambda i: valeurs[i])
    return simplexe[i], valeurs[i]


def _sse(y: list[float], p: list[float], debut: int) -> float:
    s = 0.0
    for t in range(debut, len(y)):
        if p[t] is not None:
            s += (y[t] - p[t]) ** 2
    return s if math.isfinite(s) else 1e300


# ─────────────────────────────────────────────────────────────────────────────
# Modèles : chaque classe sait (1) estimer ses paramètres sur un historique, (2) filtrer une série pour
# obtenir l'état après chaque jour t, (3) prévoir y_{t+h} depuis l'état du jour t.
# ─────────────────────────────────────────────────────────────────────────────
class ModeleSerie:
    nom = "?"
    debut = 1                         # premier jour où une prévision à un pas existe

    def ajuster(self, y: list[float]) -> "ModeleSerie":
        return self

    def prevoir(self, y: list[float], origines: list[int], h: int) -> list[float]:
        raise NotImplementedError


class Naif(ModeleSerie):
    nom = "Naïf (persistance)"

    def prevoir(self, y, origines, h):
        return [y[t] for t in origines]


class MoyenneHistorique(ModeleSerie):
    nom = "Moyenne historique"

    def prevoir(self, y, origines, h):
        cum, s = [], 0.0
        for v in y:
            s += v; cum.append(s)
        return [cum[t] / (t + 1) for t in origines]


class _Lissage(ModeleSerie):
    """Base des lissages : `etats(y, params)` renvoie (un_pas, etats), etat[t] = état après y_t."""
    x0: list[float] = []

    def etats(self, y, params):
        raise NotImplementedError

    def depuis_etat(self, etat, h, params):
        raise NotImplementedError

    def ajuster(self, y):
        if len(y) <= self.debut + 2:
            self.params = self.x0
            return self
        self.params, _ = nelder_mead(lambda u: _sse(y, self.etats(y, u)[0], self.debut), list(self.x0))
        return self

    def prevoir(self, y, origines, h):
        _, etats = self.etats(y, self.params)
        return [self.depuis_etat(etats[t], h, self.params) if etats[t] is not None else y[t] for t in origines]


class LissageSimple(_Lissage):
    nom, x0, debut = "Lissage exponentiel simple", [0.0], 1

    def etats(self, y, u):
        a = SIG(u[0]); l = y[0]; p, e = [None], [l]
        for t in range(1, len(y)):
            p.append(l); l = a * y[t] + (1 - a) * l; e.append(l)
        return p, e

    def depuis_etat(self, l, h, u):
        return l


class HoltLineaire(_Lissage):
    nom, x0, debut = "Holt linéaire", [0.0, -2.0], 2

    def etats(self, y, u):
        a, b = SIG(u[0]), SIG(u[1])
        if len(y) < 2:
            return [None] * len(y), [None] * len(y)
        l, tr = y[1], y[1] - y[0]; p, e = [None, None], [None, (l, tr)]
        for t in range(2, len(y)):
            p.append(l + tr); l0 = l
            l = a * y[t] + (1 - a) * (l + tr); tr = b * (l - l0) + (1 - b) * tr; e.append((l, tr))
        return p, e

    def depuis_etat(self, e, h, u):
        return e[0] + h * e[1]


class HoltAmorti(_Lissage):
    nom, x0, debut = "Holt amorti", [0.0, -2.0, 1.0], 2

    def etats(self, y, u):
        a, b, ph = SIG(u[0]), SIG(u[1]), PHI(u[2])
        if len(y) < 2:
            return [None] * len(y), [None] * len(y)
        l, tr = y[1], y[1] - y[0]; p, e = [None, None], [None, (l, tr)]
        for t in range(2, len(y)):
            p.append(l + ph * tr); l0 = l
            l = a * y[t] + (1 - a) * (l + ph * tr); tr = b * (l - l0) + (1 - b) * ph * tr; e.append((l, tr))
        return p, e

    def depuis_etat(self, e, h, u):
        ph = PHI(u[2])
        return e[0] + sum(ph ** j for j in range(1, h + 1)) * e[1]


class _Saisonnier(_Lissage):
    m = 7

    def _saison(self, s, t, h):
        k = (h - 1) // self.m
        return s[t + h - self.m * (k + 1)]


class SaisonnierSimple(_Saisonnier):
    nom, x0 = "Lissage saisonnier sans tendance", [0.0, -1.0]
    debut = 7

    def etats(self, y, u):
        a, g, m = SIG(u[0]), SIG(u[1]), self.m
        n = len(y)
        if n < 2 * m:
            return [None] * n, [None] * n
        l = sum(y[:m]) / m; s = [v - l for v in y[:m]]; p, e = [None] * m, [None] * m
        for t in range(m, n):
            p.append(l + s[t - m]); l = a * (y[t] - s[t - m]) + (1 - a) * l
            s.append(g * (y[t] - l) + (1 - g) * s[t - m]); e.append((l, s, t))
        return p, e

    def depuis_etat(self, e, h, u):
        l, s, t = e
        return l + self._saison(s, t, h)


class HoltWintersAdditif(_Saisonnier):
    nom, x0 = "Holt-Winters additif amorti", [0.0, -2.0, -1.0, 1.0]
    debut = 7

    def etats(self, y, u):
        a, b, g, ph, m = SIG(u[0]), SIG(u[1]), SIG(u[2]), PHI(u[3]), self.m
        n = len(y)
        if n < 2 * m:
            return [None] * n, [None] * n
        l = sum(y[:m]) / m; tr = (sum(y[m:2 * m]) / m - l) / m
        s = [v - l for v in y[:m]]; p, e = [None] * m, [None] * m
        for t in range(m, n):
            p.append(l + ph * tr + s[t - m]); l0 = l
            l = a * (y[t] - s[t - m]) + (1 - a) * (l + ph * tr); tr = b * (l - l0) + (1 - b) * ph * tr
            s.append(g * (y[t] - l) + (1 - g) * s[t - m]); e.append((l, tr, s, t))
        return p, e

    def depuis_etat(self, e, h, u):
        l, tr, s, t = e; ph = PHI(u[3])
        return l + sum(ph ** j for j in range(1, h + 1)) * tr + self._saison(s, t, h)


class HoltWintersMultiplicatif(_Saisonnier):
    nom, x0 = "Holt-Winters multiplicatif amorti", [0.0, -2.0, -1.0, 1.0]
    debut = 7

    def etats(self, y, u):
        a, b, g, ph, m = SIG(u[0]), SIG(u[1]), SIG(u[2]), PHI(u[3]), self.m
        n = len(y)
        if n < 2 * m or any(v <= 0 for v in y):
            return [None] * n, [None] * n
        l = sum(y[:m]) / m; tr = (sum(y[m:2 * m]) / m - l) / m
        s = [v / l for v in y[:m]]; p, e = [None] * m, [None] * m
        for t in range(m, n):
            p.append((l + ph * tr) * s[t - m]); l0 = l
            l = a * (y[t] / s[t - m]) + (1 - a) * (l + ph * tr); tr = b * (l - l0) + (1 - b) * ph * tr
            s.append(g * (y[t] / l) + (1 - g) * s[t - m]); e.append((l, tr, s, t))
        return p, e

    def depuis_etat(self, e, h, u):
        l, tr, s, t = e; ph = PHI(u[3])
        return (l + sum(ph ** j for j in range(1, h + 1)) * tr) * self._saison(s, t, h)


class Theta(_Lissage):
    nom, x0, debut = "Méthode Thêta", [0.0], 1

    def ajuster(self, y):
        n = len(y); tm = (n - 1) / 2; ym = sum(y) / n
        den = sum((t - tm) ** 2 for t in range(n))
        self.pente = sum((t - tm) * (y[t] - ym) for t in range(n)) / den if den else 0.0
        return super().ajuster(y)

    def etats(self, y, u):
        a = SIG(u[0]); b = getattr(self, "pente", 0.0); l = y[0]; p, e = [None], [l]
        for t in range(1, len(y)):
            p.append(l + 0.5 * b / a); l = a * y[t] + (1 - a) * l; e.append(l)
        return p, e

    def depuis_etat(self, l, h, u):
        return l + 0.5 * self.pente * (h - 1 + 1 / SIG(u[0]))


class AR(ModeleSerie):
    """AR(p) par moindres carrés, p ∈ [1, pmax] choisi par AIC sur l'historique d'estimation."""

    def __init__(self, pmax: int = 14):
        self.pmax, self.nom = pmax, "AR(p), p choisi par AIC"

    def ajuster(self, y):
        meilleur = None
        for p in range(1, min(self.pmax, len(y) // 4) + 1):
            X = torch.tensor([[1.0] + [y[t - 1 - i] for i in range(p)] for t in range(p, len(y))], dtype=TYPE)
            Y = torch.tensor(y[p:], dtype=TYPE)
            coef = torch.linalg.solve(X.T @ X + 1e-9 * torch.eye(p + 1, dtype=TYPE), X.T @ Y)   # équations normales
            sce = float(((Y - X @ coef) ** 2).sum()); n = len(Y)
            aic = n * math.log(max(sce, 1e-12) / n) + 2 * (p + 1)
            if meilleur is None or aic < meilleur[0]:
                meilleur = (aic, p, coef.tolist())
        self.aic, self.p, self.coef = meilleur
        self.nom = f"AR({self.p}) (ordre par AIC)"
        return self

    def prevoir(self, y, origines, h):
        c, p, sortie = self.coef, self.p, []
        for t in origines:
            hist = list(y[max(0, t - p + 1):t + 1])
            for _ in range(h):
                v = c[0] + sum(c[1 + i] * hist[-1 - i] for i in range(p) if i < len(hist))
                hist.append(v)
            sortie.append(hist[-1])
        return sortie


# ── SARIMA ───────────────────────────────────────────────────────────────────
def _mul(a, b):
    r = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, z in enumerate(b):
            r[i + j] += x * z
    return r


def _poly_saison(coefs, s, signe):
    p = [0.0] * (len(coefs) * s + 1); p[0] = 1.0
    for i, c in enumerate(coefs):
        p[(i + 1) * s] = signe * c
    return p


@dataclass
class OrdreSarima:
    p: int = 1; d: int = 0; q: int = 0; P: int = 0; D: int = 0; Q: int = 0; s: int = 7

    def __str__(self):
        return f"SARIMA({self.p},{self.d},{self.q})({self.P},{self.D},{self.Q}){self.s}"


class Sarima(ModeleSerie):
    def __init__(self, ordre: OrdreSarima):
        self.o = ordre; self.nom = str(ordre)

    def _polys(self, u):
        o = self.o; k = o.p + o.q + o.P + o.Q
        phi = [math.tanh(v) for v in u[:o.p]]; th = [math.tanh(v) for v in u[o.p:o.p + o.q]]
        Phi = [math.tanh(v) for v in u[o.p + o.q:o.p + o.q + o.P]]; Th = [math.tanh(v) for v in u[o.p + o.q + o.P:k]]
        ar = _mul([1.0] + [-c for c in phi], _poly_saison(Phi, o.s, -1))
        ma = _mul([1.0] + list(th), _poly_saison(Th, o.s, 1))
        for _ in range(o.d):
            ar = _mul(ar, [1.0, -1.0])
        for _ in range(o.D):
            ar = _mul(ar, _poly_saison([1.0], o.s, -1))
        return ar, ma, u[k]

    def _innovations(self, y, u):
        """Filtre CSS sur la série d'origine (AR complet = AR · (1 − B)^d (1 − B^s)^D) : innovations e_t."""
        ar, ma, c = self._polys(u)
        debut = max(len(ar), len(ma)) - 1
        e = [0.0] * len(y)
        for t in range(len(y)):
            if t < debut:
                continue
            v = c - sum(ar[i] * y[t - i] for i in range(1, len(ar))) + sum(ma[j] * e[t - j] for j in range(1, len(ma)))
            e[t] = y[t] - v
        return e, debut

    def ajuster(self, y):
        o = self.o; k = o.p + o.q + o.P + o.Q
        z = list(y)
        for _ in range(o.d):
            z = [z[t] - z[t - 1] for t in range(1, len(z))]
        for _ in range(o.D):
            z = [z[t] - z[t - o.s] for t in range(o.s, len(z))]
        x0 = [0.1] * k + [0.5 * sum(z) / max(1, len(z))]

        def css(u):
            e, debut = self._innovations(y, u)
            s = sum(v * v for v in e[debut:])
            return s if math.isfinite(s) else 1e300
        self.u, valeur = nelder_mead(css, x0, pas=0.3, iterations=60 * (k + 1))
        _, debut = self._innovations(y, self.u)
        m = max(1, len(y) - debut); self.sigma2 = valeur / m
        self.bic = m * math.log(max(self.sigma2, 1e-12)) + math.log(m) * (k + 2)
        return self

    def prevoir(self, y, origines, h):
        ar, ma, c = self._polys(self.u)
        e, _ = self._innovations(y, self.u)
        sortie = []
        for t in origines:
            yy, ee = list(y[:t + 1]), list(e[:t + 1])
            for _ in range(h):
                n = len(yy)
                v = c - sum(ar[i] * yy[n - i] for i in range(1, len(ar)) if n - i >= 0) \
                    + sum(ma[j] * ee[n - j] for j in range(1, len(ma)) if n - j >= 0)
                yy.append(v); ee.append(0.0)
            sortie.append(yy[-1])
        return sortie


GRILLE_SARIMA = [OrdreSarima(p, d, q, P, D, Q) for d in (0, 1) for D in (0, 1)
                 for p, q in ((1, 0), (0, 1), (1, 1), (2, 0), (2, 1)) for P, Q in ((0, 0), (1, 0), (0, 1))]


def choisir_ordre_sarima(y: list[float], part_controle: float = 0.2, grille=GRILLE_SARIMA) -> tuple[OrdreSarima, list[dict]]:
    """
    Ordre choisi sur l'APPRENTISSAGE seulement : meilleur BIC à (d, D) fixés sur les (1 − part) premiers jours,
    puis départage des quatre (d, D) par la MAE à un pas sur les `part` derniers jours de l'apprentissage.
    """
    coupure = int(len(y) * (1 - part_controle))
    essais, par_diff = [], {}
    for o in grille:
        try:
            m = Sarima(o).ajuster(y[:coupure])
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if not math.isfinite(m.bic):
            continue
        essais.append({"ordre": str(o), "bic": round(m.bic, 2)})
        cle = (o.d, o.D)
        if cle not in par_diff or m.bic < par_diff[cle].bic:
            par_diff[cle] = m
    def mae_controle(m):
        p = m.prevoir(y, list(range(coupure - 1, len(y) - 1)), 1)
        return sum(abs(y[t + 1] - v) for t, v in zip(range(coupure - 1, len(y) - 1), p)) / len(p)
    meilleur = min(par_diff.values(), key=mae_controle)
    return meilleur.o, sorted(essais, key=lambda e: e["bic"])


# ─────────────────────────────────────────────────────────────────────────────
# Évaluation dans la validation glissante, alignée sur svr.validation.evaluer
# ─────────────────────────────────────────────────────────────────────────────
def evaluer_serie(fabrique, serie: torch.Tensor, origines_par_bloc: list[list[int]], h: int,
                  taus: tuple[float, ...] = (0.05, 0.8, 0.95), erreurs_max: int = 180) -> dict:
    """
    `fabrique()` crée un modèle neuf. Pour chaque bloc (liste d'origines t, toutes ≥ O = premier t du bloc) :
    estimation sur y_0 … y_O, prévision ponctuelle de y_{t+h} pour chaque t, et quantiles empiriques des
    erreurs à h jours de l'apprentissage (cibles ≤ O, `erreurs_max` derniers jours).
    Renvoie {0.5: point, τ: quantile…} dans l'ordre des blocs (comme evaluer).
    """
    y = [float(v) for v in serie]
    sortie = {0.5: []} | {t: [] for t in taus}
    for bloc in origines_par_bloc:
        O = min(bloc)
        modele = fabrique().ajuster(y[:O + 1])
        point = modele.prevoir(y[:max(bloc) + 1], bloc, h)
        passes = list(range(max(modele.debut, O - h - erreurs_max + 1), O - h + 1))
        erreurs = sorted(y[s + h] - v for s, v in zip(passes, modele.prevoir(y[:O + 1], passes, h))) if passes else [0.0]
        sortie[0.5].extend(point)
        for tau in taus:
            pos = tau * (len(erreurs) - 1); b = int(pos)
            q = erreurs[b] + (pos - b) * (erreurs[min(b + 1, len(erreurs) - 1)] - erreurs[b])
            sortie[tau].extend(v + q for v in point)
    return {k: torch.tensor(v, dtype=TYPE) for k, v in sortie.items()}


def modeles_de_reference(ordre_sarima: OrdreSarima | None = None) -> dict[str, object]:
    """Toutes les références du banc, nom → fabrique."""
    f = {"Moyenne historique": MoyenneHistorique, "Lissage exponentiel simple": LissageSimple,
         "Méthode Thêta": Theta, "Holt linéaire": HoltLineaire, "Holt amorti": HoltAmorti,
         "Lissage saisonnier sans tendance": SaisonnierSimple, "Holt-Winters additif amorti": HoltWintersAdditif,
         "Holt-Winters multiplicatif amorti": HoltWintersMultiplicatif, "AR(p) par AIC": lambda: AR(14)}
    if ordre_sarima is not None:
        f[f"{ordre_sarima} (ordre choisi sur l'apprentissage)"] = lambda: Sarima(ordre_sarima)
    return f
