r"""
Modèle de survie en temps discret : probabilité qu'un enfant hospitalisé sorte aujourd'hui (J0),
demain (J1) ou après-demain (J2) — protocole, variable cible « probabilité de sortie à j, j+1, j+2
par patient hospitalisé », et Document 5 (écran « sorties probables »).

1. Le tableau « patient-jour »
------------------------------
Chaque séjour est découpé en jours : une ligne par jour passé à l'hôpital, avec
    k          l'ancienneté du séjour ce jour-là (0 = jour d'entrée, 1 = lendemain…) ;
    événement  1 si l'enfant sort CE jour-là, 0 sinon ;
    poids      1 en général (voir sorties non écrites ci-dessous).
Un séjour de 3 nuits (entrée le 1er, sortie le 4) donne 4 lignes : k = 0, 1, 2 (événement 0) et
k = 3 (événement 1). Un séjour encore en cours à la fin des données (censuré) donne des lignes
toutes à 0 : on sait seulement qu'il n'est pas sorti ces jours-là — c'est ainsi que le temps
discret traite la censure, sans rien inventer.

Sorties non écrites (nera.occupation) : la sortie est au jour n − 1 avec la probabilité p
(ligne inclusive) ou au jour n avec 1 − p. On écrit alors au jour n − 1 deux lignes, « sort »
avec le poids p et « reste » avec le poids 1 − p, puis au jour n une ligne « sort » de poids
1 − p : c'est l'espérance de la vraisemblance sur les deux possibilités.

2. Le hasard h(k, x) et les probabilités J0, J1, J2
---------------------------------------------------
    h(k, x) = P(sortir le jour d | être présent au début du jour d, ancienneté k, variables x)
Pour un enfant présent ce matin (ancienneté k), les jours suivants ont pour variables x₀, x₁, x₂
(le jour de la semaine change, l'ancienneté augmente) :
    P(J0) = h₀
    P(J1) = (1 − h₀) · h₁
    P(J2) = (1 − h₀)(1 − h₁) · h₂
Le nombre attendu de sorties d'un jour = Σ des probabilités des enfants présents : c'est
l'« agrégation par somme de fonctions de survie individuelles » du protocole.

3. Risques concurrents
----------------------
Un séjour se termine par une sortie à domicile, un transfert, un décès, une sortie contre avis…
Hasard spécifique de la cause c : h_c(k, x) = P(sortir par c ce jour | présent). Les autres causes
arrêtent le séjour (plus de lignes ensuite) et comptent 0 pour c. Hasard total h = Σ_c h_c.
P(sortie par c le jour J1) = (1 − h₀) · h_{c,1}, etc.

4. Références (sans variables du patient)
-----------------------------------------
  Table de survie : h(k) = Σ poids des sorties à l'ancienneté k / Σ poids des présents à k
                    (estimateur actuariel ; les anciennetés ≥ k_max sont regroupées).
  Loi gamma (protocole : durée asymétrique, mieux décrite par une gamma que par une loi
                    symétrique) : durée T ~ Gamma(forme a, échelle θ), ajustée par la méthode
                    des moments (a = m²/v, θ = v/m) ; la sortie a lieu le jour ⌊T⌋, donc
                    h(k) = [F(k + 1) − F(k)] / [1 − F(k)], F = fonction de répartition gamma :
                    F(x) = P(a, x/θ), fonction gamma incomplète régularisée, calculée à la main
                    (série si x < a + 1, fraction continue de Lentz sinon).
"""
from __future__ import annotations

import math

import pandas as pd
import torch

TYPE = torch.float64
TRANCHES_ANCIENNETE = [0, 1, 2, 3, 4, 5, 6, 7, 9, 12, 16]           # bornes basses : 0,1,…,6, 7–8, 9–11, 12–15, 16+
CAUSES = {"Sortie": "domicile", "Décès": "décès", "Transfert interne": "transfert", "Transfert externe": "transfert",
          "Sortie contre avis médical": "autre", "Évasion": "autre"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tableau patient-jour
# ─────────────────────────────────────────────────────────────────────────────
def lignes_patient_jour(sejours: pd.DataFrame, extraction) -> pd.DataFrame:
    """Une ligne par séjour et par jour de présence (voir l'en-tête). Séjours « inconnue » exclus."""
    extraction = pd.Timestamp(extraction).normalize()
    attributs = [c for c in ("age_mois", "sexe", "ancien_nouveau", "diagnostic_entree") if c in sejours]
    lignes = []
    for i, s in sejours[sejours["statut"] != "inconnue"].iterrows():
        e = s["entree"]
        base = {"sejour": i, **{c: s[c] for c in attributs}}
        cause = CAUSES.get(s.get("issue"), "autre")
        if pd.isna(s["sortie"]):                                           # censuré : présent jusqu'à la veille de l'extraction
            for k in range((extraction - e).days):
                lignes.append({**base, "jour": e + pd.Timedelta(days=k), "k": k, "evenement": 0, "poids": 1.0, "cause": None})
            continue
        n = (s["sortie"] - e).days
        ambigu = s["statut"] == "calculee" and s["sortie_basse"] < s["sortie"]
        p = float(s["p_inclusif"]) if ambigu else 0.0
        for k in range(n + 1):
            jour = e + pd.Timedelta(days=k)
            if ambigu and k == n - 1:                                      # sortie possible ce jour (ligne inclusive)
                lignes.append({**base, "jour": jour, "k": k, "evenement": 1, "poids": p, "cause": cause})
                lignes.append({**base, "jour": jour, "k": k, "evenement": 0, "poids": 1 - p, "cause": None})
            elif k == n:
                if not ambigu or 1 - p > 0:
                    lignes.append({**base, "jour": jour, "k": k, "evenement": 1, "poids": 1 - p if ambigu else 1.0, "cause": cause})
            else:
                lignes.append({**base, "jour": jour, "k": k, "evenement": 0, "poids": 1.0, "cause": None})
    t = pd.DataFrame(lignes)
    return t[t["poids"] > 0].reset_index(drop=True)


def tranche(k: int) -> int:
    """Indice de la tranche d'ancienneté de k (voir TRANCHES_ANCIENNETE)."""
    return max(i for i, borne in enumerate(TRANCHES_ANCIENNETE) if k >= borne)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Encodage des variables (appris sur l'entraînement seulement)
# ─────────────────────────────────────────────────────────────────────────────
class EncodeurVariables:
    r"""
    Variables d'une ligne patient-jour :
      ancienneté (11 tranches 0/1) — c'est la « forme de base » du hasard, comme une table de survie ;
      jour de la semaine du jour concerné (7) et jour férié — on sort moins le dimanche et les fériés ;
      mois en sinus/cosinus ; âge (log(1 + mois)) et indicatrice « âge inconnu » ; sexe masculin ;
      « ancien » patient ; les `n_diagnostics` diagnostics d'entrée les plus fréquents (+ « autre ») ;
      pression sur les lits : taux d'occupation de la veille (connu le matin), si fourni.
    La liste des diagnostics et l'âge de remplacement sont appris sur l'ENTRAÎNEMENT seulement.
    """

    def __init__(self, feries: set | None = None, occupation_veille: pd.Series | None = None, n_diagnostics: int = 10):
        self.feries, self.occupation, self.n_diag = feries or set(), occupation_veille, n_diagnostics

    def ajuster(self, lignes: pd.DataFrame) -> "EncodeurVariables":
        diag = lignes.drop_duplicates("sejour").get("diagnostic_entree")
        self.diagnostics = (list(diag.dropna().astype(str).str.lower().str.strip().value_counts().index[: self.n_diag])
                            if diag is not None else [])
        ages = lignes.drop_duplicates("sejour").get("age_mois")
        self.age_median = float(ages.median()) if ages is not None and ages.notna().any() else 0.0
        return self

    def noms(self) -> list[str]:
        return ([f"anciennete_{b}+" for b in TRANCHES_ANCIENNETE] + [f"jour_{j}" for j in range(7)]
                + ["ferie", "mois_sin", "mois_cos", "log_age", "age_inconnu", "garcon", "ancien"]
                + [f"diag:{d}" for d in self.diagnostics] + ["diag:autre"]
                + (["occupation_veille"] if self.occupation is not None else []))

    def transformer(self, lignes: pd.DataFrame) -> torch.Tensor:
        n, colonnes = len(lignes), []
        t = torch.tensor([tranche(int(k)) for k in lignes["k"]], dtype=torch.long)
        colonnes.append(torch.nn.functional.one_hot(t, len(TRANCHES_ANCIENNETE)).to(TYPE))
        jours = pd.DatetimeIndex(lignes["jour"])
        colonnes.append(torch.nn.functional.one_hot(torch.as_tensor(jours.dayofweek.to_numpy(), dtype=torch.long), 7).to(TYPE))
        angle = 2 * math.pi * (jours.month.to_numpy() - 1) / 12
        age = pd.to_numeric(lignes.get("age_mois", pd.Series([None] * n)), errors="coerce").to_numpy()
        age_inconnu = pd.isna(age)
        sexe = lignes.get("sexe", pd.Series([None] * n)).to_numpy()
        ancien = lignes.get("ancien_nouveau", pd.Series([None] * n)).to_numpy()
        colonnes.append(torch.tensor([[1.0 if d.date() in self.feries else 0.0, math.sin(a), math.cos(a),
                                       math.log1p(self.age_median if inc else float(ag)), float(inc),
                                       1.0 if sx == "M" else 0.0, 1.0 if an == "Ancien" else 0.0]
                                      for d, a, ag, inc, sx, an in zip(jours, angle, age, age_inconnu, sexe, ancien)], dtype=TYPE))
        diag = lignes.get("diagnostic_entree", pd.Series([None] * n)).astype(str).str.lower().str.strip().to_numpy()
        connus = {d: j for j, d in enumerate(self.diagnostics)}
        indice = torch.tensor([connus.get(d, len(self.diagnostics)) for d in diag], dtype=torch.long)
        colonnes.append(torch.nn.functional.one_hot(indice, len(self.diagnostics) + 1).to(TYPE))
        if self.occupation is not None:
            veille = self.occupation.reindex(jours - pd.Timedelta(days=1))
            colonnes.append(torch.tensor(veille.ffill().bfill().fillna(0.0).to_numpy(), dtype=TYPE)[:, None])
        return torch.cat(colonnes, dim=1)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Références : table de survie et loi gamma
# ─────────────────────────────────────────────────────────────────────────────
def table_de_survie(lignes: pd.DataFrame, k_max: int = 30) -> torch.Tensor:
    """h(k) pour k = 0 … k_max (k_max regroupe toutes les anciennetés ≥ k_max)."""
    kk = lignes["k"].clip(upper=k_max).to_numpy()
    sorties = torch.zeros(k_max + 1, dtype=TYPE); presents = torch.zeros(k_max + 1, dtype=TYPE)
    for k, ev, w in zip(kk, lignes["evenement"].to_numpy(), lignes["poids"].to_numpy()):
        presents[k] += w
        sorties[k] += w * ev
    return torch.where(presents > 0, sorties / presents.clamp(min=1e-12), torch.zeros_like(presents))


def gamma_incomplete_reguliere(a: float, x: float) -> float:
    """P(a, x) = γ(a, x)/Γ(a), fonction de répartition d'une Gamma(a, 1) en x."""
    if x <= 0:
        return 0.0
    prefacteur = math.exp(-x + a * math.log(x) - math.lgamma(a))
    if x < a + 1:                                                         # série : Σ xⁿ / (a(a+1)…(a+n))
        terme = somme = 1.0 / a
        ap = a
        for _ in range(1000):
            ap += 1
            terme *= x / ap
            somme += terme
            if abs(terme) < abs(somme) * 1e-15:
                break
        return min(1.0, somme * prefacteur)
    # Fraction continue de Q(a, x) = 1 − P(a, x), méthode de Lentz modifiée.
    petit = 1e-300
    b = x + 1 - a; c = 1 / petit; d = 1 / b; h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b; d = petit if abs(d) < petit else d
        c = b + an / c; c = petit if abs(c) < petit else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return max(0.0, 1.0 - prefacteur * h)


def ajuster_gamma(durees: torch.Tensor, poids: torch.Tensor | None = None) -> tuple[float, float]:
    """Méthode des moments pondérée : a = m²/v, θ = v/m (durées en nuits, + 0,5 : milieu du jour de sortie)."""
    x = torch.as_tensor(durees, dtype=TYPE) + 0.5
    w = torch.ones_like(x) if poids is None else torch.as_tensor(poids, dtype=TYPE)
    m = float((w * x).sum() / w.sum())
    v = float((w * (x - m) ** 2).sum() / w.sum())
    return m * m / v, v / m


def hasard_gamma(k_max: int, forme: float, echelle: float) -> torch.Tensor:
    """h(k) = [F(k+1) − F(k)] / [1 − F(k)] pour k = 0 … k_max."""
    F = [gamma_incomplete_reguliere(forme, j / echelle) for j in range(k_max + 2)]
    return torch.tensor([(F[k + 1] - F[k]) / max(1e-12, 1 - F[k]) for k in range(k_max + 1)], dtype=TYPE)


# ─────────────────────────────────────────────────────────────────────────────
# 4. J0, J1, J2 pour les enfants présents un matin
# ─────────────────────────────────────────────────────────────────────────────
def presents_le_matin(lignes: pd.DataFrame, jour: pd.Timestamp) -> pd.DataFrame:
    """Enfants à risque ce jour-là et déjà là la veille (k ≥ 1) : une ligne par séjour."""
    t = lignes[(lignes["jour"] == jour) & (lignes["k"] >= 1)]
    return t.drop_duplicates("sejour")


def lignes_futures(presents: pd.DataFrame, decalage: int) -> pd.DataFrame:
    """Les mêmes enfants, `decalage` jours plus tard (ancienneté + décalage, jour + décalage)."""
    f = presents.copy()
    f["k"] = f["k"] + decalage
    f["jour"] = f["jour"] + pd.Timedelta(days=decalage)
    return f


def probabilites_j012(hasard, presents: pd.DataFrame) -> torch.Tensor:
    """
    `hasard(lignes) → tenseur` ; renvoie un tableau n × 3 : P(J0), P(J1), P(J2) par enfant.
    P(J0) = h₀ ; P(J1) = (1 − h₀) h₁ ; P(J2) = (1 − h₀)(1 − h₁) h₂.
    """
    h = [hasard(lignes_futures(presents, j)).clamp(0.0, 1.0) for j in range(3)]
    return torch.stack([h[0], (1 - h[0]) * h[1], (1 - h[0]) * (1 - h[1]) * h[2]], dim=1)


def sorties_observees(lignes: pd.DataFrame, presents: pd.DataFrame, jour: pd.Timestamp, decalage: int) -> float:
    """Nombre (pondéré) des enfants présents ce matin qui sortent réellement au jour + décalage."""
    cible = jour + pd.Timedelta(days=decalage)
    t = lignes[lignes["sejour"].isin(presents["sejour"]) & (lignes["jour"] == cible) & (lignes["evenement"] == 1)]
    return float(t["poids"].sum())
