r"""
Vérification complète des calculs — sur des données FICTIVES (jamais les données du stage).

Trois contrôles indépendants, chacun avec un verdict « JUSTE » ou « ÉCART » :

  A. Occupation (les trois méthodes de comptage, la fourchette, le pic de la journée, la capacité variable) :
       1. l'outil de saisie (le vrai code JavaScript de saisie.html, exécuté par Node) ;
       2. la chaîne Python (nera.depuis_outil → nera.chargement → nera.occupation) ;
       3. un calcul « à la force brute » écrit ici, jour par jour et séjour par séjour, directement à partir des
          définitions (aucun tableau de différences, aucune somme cumulée) ;
     les trois doivent donner les mêmes nombres, jour par jour (tolérance 1e-9).
  B. La bibliothèque statistique de l'outil (statistiques.js) contre les bibliothèques de référence
     (scipy, statsmodels, numpy), utilisées ICI SEULEMENT comme juges : lois de probabilité, statistiques
     descriptives, corrélations, tests, régression, ACP, séries temporelles, modèles de prévision, métriques.
  C. Des cas calculés à la main (valeurs exactes écrites dans ce fichier).

Lancement (depuis backend/modeles, dans WSL) :
    ~/memoire-env/bin/python -m verification.verifier_calculs
Le rapport est écrit dans verification/rapport_verification.md ; le code de sortie vaut 1 s'il y a un écart.
Node (node, node.exe, ou C:\Program Files\nodejs\node.exe vu de WSL) doit être installé.
"""
from __future__ import annotations

import json
import shutil
import warnings
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import special, stats
from statsmodels.regression.linear_model import OLS
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.proportion import proportion_confint
from statsmodels.tools import add_constant
from statsmodels.tsa.ar_model import AutoReg
from statsmodels.tsa.stattools import acf as sm_acf, adfuller, kpss as sm_kpss, pacf as sm_pacf

warnings.filterwarnings("ignore")                   # avertissements de version de statsmodels, sans objet ici
ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from nera.chargement import preparer_sejours  # noqa: E402
from nera.depuis_outil import convertir  # noqa: E402
from nera.occupation import HeuresPresence, reconstituer_occupation  # noqa: E402

RESULTATS: list[tuple[str, str, str, bool]] = []      # (partie, calcul, détail, juste)


def noter(partie: str, calcul: str, juste: bool, detail: str = "") -> None:
    RESULTATS.append((partie, calcul, detail, bool(juste)))
    print(f"  {'JUSTE' if juste else 'ÉCART'}  {calcul}{'  — ' + detail if detail else ''}")


def proche(a, b, tol=1e-6) -> tuple[bool, float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape:
        return False, float("inf")
    e = float(np.nanmax(np.abs(a - b) / np.maximum(1.0, np.abs(b)))) if a.size else 0.0
    return bool(e <= tol and np.array_equal(np.isnan(a), np.isnan(b))), e


# ── Node : le vrai code de l'outil ─────────────────────────────────────────────────────────
def node() -> str:
    for c in ("node", "node.exe", "/mnt/c/Program Files/nodejs/node.exe"):
        if shutil.which(c) or Path(c).exists():
            return c
    sys.exit("Node introuvable : installez Node.js (https://nodejs.org) pour exécuter le code de l'outil.")


def outil(demande: dict) -> dict:
    # cwd = ce dossier, script en chemin relatif : fonctionne aussi pour node.exe appelé depuis WSL.
    r = subprocess.run([node(), "outil_node.mjs"], cwd=ICI, input=json.dumps(demande), capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode:
        sys.exit("Erreur dans le code de l'outil :\n" + r.stderr)
    return json.loads(r.stdout)


# ── Données fictives ───────────────────────────────────────────────────────────────────────
def registre_fictif(graine: int = 7) -> str:
    """
    Registre de pédiatrie INVENTÉ (9 mois, environ 3 admissions par jour), avec tous les cas difficiles :
    sorties écrites ; nombre de jours seul (sortie calculée, convention nuits / inclusive inconnue) ;
    les deux, avec 40 % de lignes inclusives ; séjours du même jour (MEO) ; départ écrit sans durée ; enfants
    encore hospitalisés à la fin ; décès et SCAM. Aucune colonne d'identité.
    """
    rng = np.random.default_rng(graine)
    debut, fin = date(2025, 1, 1), date(2025, 9, 30)
    lignes, numero, mois = [], 0, None
    j = debut
    while j <= fin:
        for _ in range(rng.poisson(3.0 if j.month not in (6, 7) else 4.5)):
            if j.month != mois:
                mois, numero = j.month, 0
            numero += 1
            nuits = 0 if rng.random() < 0.08 else int(min(30, rng.geometric(0.3)))
            sortie = j + timedelta(days=nuits)
            obs = rng.choice(["Sortie", "Sortie", "Sortie", "SCAM", "Décédé", "Référé"], p=[.3, .3, .26, .08, .03, .03])
            obs = "MEO" if nuits == 0 else obs
            cas = rng.random()
            inclusive = rng.random() < 0.4
            nb = nuits + (1 if inclusive else 0)
            date_sortie, nb_jours = f"{sortie:%d/%m/%y}", str(nb)
            if sortie >= fin - timedelta(days=3) or (fin - j).days < 6 and cas < 0.5:
                date_sortie, nb_jours, obs = "", "", ""                      # encore hospitalisé
            elif cas < 0.55:
                pass                                                         # sortie écrite + nombre de jours
            elif cas < 0.75:
                date_sortie = ""                                             # sortie calculée
            elif cas < 0.92:
                nb_jours = ""                                                # sortie écrite seule
            else:
                date_sortie, nb_jours = "", ""                               # départ écrit, durée inconnue
            lignes.append([str(numero), f"{j:%d/%m/%y}", f"{j:%d/%m/%y}", date_sortie, nb_jours, "7500", obs])
        j += timedelta(days=1)
    entete = ["N° d'ordre", "Date (enregistrement)", "Date d'entrée", "Date de sortie", "Nbre de jours", "Prix", "Observation"]
    return "\n".join(";".join(x) for x in [entete, *lignes]) + "\n"


# ── A. Occupation ──────────────────────────────────────────────────────────────────────────
def force_brute(sejours: pd.DataFrame, jours: pd.DatetimeIndex, extraction: pd.Timestamp, comptage: str,
                scenario: str, h: HeuresPresence) -> np.ndarray:
    """Présence de chaque jour, séjour par séjour, par la définition (aucune astuce de calcul)."""
    a, b, m = h.entree / 24, h.sortie / 24, h.meme_jour / 24
    res = np.zeros(len(jours))
    for x in sejours[sejours["statut"] != "inconnue"].itertuples():
        e = x.entree
        if x.statut == "calculee" and x.sortie_basse < x.sortie:
            w = {"attendue": x.p_inclusif, "basse": 1.0, "haute": 0.0}[scenario]
            fins = [(x.sortie_basse, w, True), (x.sortie, 1 - w, True)]
        elif pd.isna(x.sortie):
            fins = [(extraction, 1.0, False)]                       # encore hospitalisé à l'extraction
        else:
            fins = [(x.sortie, 1.0, True)]
        for f, poids, reelle in fins:
            if poids == 0:
                continue
            for i, d in enumerate(jours):
                if comptage == "minuit":
                    v = 1.0 if e <= d < f else 0.0
                elif comptage == "journee":
                    v = 1.0 if e <= d <= f else 0.0
                else:                                                # pondérée par le temps
                    if d < e or d > f:
                        v = 0.0
                    elif reelle and e == f == d:
                        v = m
                    elif d == e:
                        v = 1 - a
                    elif reelle and d == f:
                        v = b
                    else:
                        v = 1.0
                res[i] += poids * v
    return res


def partie_occupation() -> None:
    print("\nA. OCCUPATION — outil (JavaScript) / Python / force brute, jour par jour")
    texte = registre_fictif()
    chemin = ICI / "sortie" / "registre_fictif.csv"
    chemin.parent.mkdir(exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    h = HeuresPresence(entree=9, sortie=15, meme_jour=6)             # heures volontairement non standard
    capacites, lits0 = "01/05/25=20", 15                             # capacité variable : 15 puis 20 lits
    js = outil({"tache": "occupation", "csv": texte, "lits": lits0, "capacites": capacites,
                "comptages": ["minuit", "journee", "pondere"], "heures": [h.entree, h.sortie, h.meme_jour]})
    df, _ = convertir(chemin, "PED", aujourdhui=date(2026, 10, 14))
    lits = pd.Series([lits0, 20], index=pd.to_datetime(["2000-01-01", "2025-05-01"]))
    for comptage in ("minuit", "journee", "pondere"):
        r = js[comptage]
        if "message" in r:
            noter("A", f"{comptage} : calcul de l'outil", False, r["message"]); continue
        extraction = pd.Timestamp(date(1970, 1, 1) + timedelta(days=r["extraction"]))
        sejours, _ = preparer_sejours(df, "PED", extraction)
        occ = {sc: reconstituer_occupation(sejours, extraction, lits, r["debut"], sc, comptage, h)
               for sc in ("attendue", "basse", "haute")}
        jours = occ["attendue"].index
        ok, e = proche(len(jours), len(r["presents"]))
        noter("A", f"{comptage} : même période ({r['debut']} → {r['fin']})", ok and str(jours[-1].date()) == r["fin"])
        for sc, cle in (("attendue", "presents"), ("basse", "bas"), ("haute", "haut")):
            py = occ[sc]["presents"].to_numpy()
            fb = force_brute(sejours, jours, extraction, comptage, sc, h)
            ok1, e1 = proche(r[cle], py, 1e-9)
            ok2, e2 = proche(py, fb, 1e-9)
            noter("A", f"{comptage} : présents ({sc}) outil = Python = force brute", ok1 and ok2,
                  f"écart max {max(e1, e2):.1e} sur {len(py)} jours")
        att = occ["attendue"]
        fb_min = force_brute(sejours, jours, extraction, "minuit", "attendue", h)
        fb_jour = force_brute(sejours, jours, extraction, "journee", "attendue", h)
        pic_bas = np.maximum(fb_min, np.r_[fb_min[0], fb_min[:-1]])
        ok1, _ = proche(r["picBas"], att["pic_bas"].to_numpy(), 1e-9)
        ok2, _ = proche(att["pic_bas"].to_numpy(), pic_bas, 1e-9)
        ok3, _ = proche(r["picHaut"], att["pic_haut"].to_numpy(), 1e-9)
        ok4, _ = proche(att["pic_haut"].to_numpy(), fb_jour, 1e-9)
        noter("A", f"{comptage} : bornes du pic de la journée", ok1 and ok2 and ok3 and ok4)
        noter("A", f"{comptage} : pic bas ≤ pic haut chaque jour", bool(np.all(att["pic_bas"] <= att["pic_haut"] + 1e-12)))
        ok, _ = proche(r["adm"], att["admissions"].to_numpy(), 0)
        noter("A", f"{comptage} : admissions du jour", ok)
        ok, _ = proche(r["litsJour"], att["lits"].to_numpy(), 0)
        noter("A", f"{comptage} : capacité de chaque jour (15 puis 20 lits au 01/05/25)", ok)
        tom = 100 * att["presents"].sum() / att["lits"].sum()
        noter("A", f"{comptage} : taux d'occupation = Σ présents ÷ Σ lits", abs(r["total"]["tom"] - round(tom, 1)) < 1e-9,
              f"outil {r['total']['tom']} %, Python {tom:.2f} %")
        sur = int((att["presents"] > att["lits"]).sum())
        noter("A", f"{comptage} : jours en sureffectif", r["total"]["sur"] == sur, f"{sur} jours")
    # Ordre attendu des trois méthodes : pondérée ≤ journée et minuit ≤ journée (chaque jour).
    p = {c: np.asarray(js[c]["presents"]) for c in ("minuit", "journee", "pondere")}
    noter("A", "minuit ≤ journée et pondérée ≤ journée, chaque jour",
          bool(np.all(p["minuit"] <= p["journee"] + 1e-12) and np.all(p["pondere"] <= p["journee"] + 1e-12)))


# ── B. statistiques.js contre scipy / statsmodels / numpy ─────────────────────────────────
def partie_statistiques() -> None:
    print("\nB. BIBLIOTHÈQUE STATISTIQUE DE L'OUTIL (statistiques.js) — juges : scipy, statsmodels, numpy")
    rng = np.random.default_rng(11)
    n = 120
    x = rng.normal(10, 3, n).round(6)
    y = (0.6 * x + rng.normal(0, 2, n)).round(6)
    z = (rng.gamma(2.0, 2.0, n)).round(6)
    g = [rng.normal(5, 1, 25).round(6).tolist(), rng.normal(5.6, 1.4, 31).round(6).tolist(), rng.normal(6.1, 0.9, 22).round(6).tolist()]
    q1 = rng.choice(["A", "B", "C"], 300, p=[.5, .3, .2]).tolist()
    q2 = [("oui" if (c == "A" and rng.random() < .6) or (c != "A" and rng.random() < .35) else "non") for c in q1]
    t = np.arange(400)
    serie = (10 + 2 * np.sin(2 * np.pi * t / 7) + np.cumsum(rng.normal(0, .3, 400)) * .2 + rng.normal(0, 1, 400)).round(6)
    X = np.c_[x, z, rng.normal(0, 1, n).round(6)]
    ar = [5.0, 5.2]
    for _ in range(298):
        ar.append(1.5 + 0.55 * ar[-1] + 0.2 * ar[-2] + rng.normal(0, 1))
    ar = np.round(ar, 6)
    lois = [("lnGamma", [v], special.gammaln(v)) for v in (0.3, 1.0, 4.5, 37.2)]
    lois += [("gammaP", [a, v], special.gammainc(a, v)) for a, v in ((0.5, 0.2), (3, 2.5), (10, 14.1))]
    lois += [("betaI", [a, b, v], special.betainc(a, b, v)) for a, b, v in ((2, 3, .4), (.5, 7, .1), (15, 4, .8))]
    lois += [("phi", [v], stats.norm.cdf(v)) for v in (-3.1, -1, 0, 0.5, 1.96, 4)]
    lois += [("qnorm", [v], stats.norm.ppf(v)) for v in (.001, .025, .3, .5, .9, .999)]
    lois += [("pStudentBilat", [v, d], 2 * stats.t.sf(abs(v), d)) for v, d in ((2.1, 5), (-1.3, 30), (4.2, 118.5))]
    lois += [("tCritique", [d], stats.t.ppf(.975, d)) for d in (3, 12, 119)]
    lois += [("pKhi2", [v, k], stats.chi2.sf(v, k)) for v, k in ((3.2, 1), (11.07, 5), (40, 30))]
    lois += [("pFisher", [v, a, b], stats.f.sf(v, a, b)) for v, a, b in ((2.5, 3, 40), (1.1, 10, 200), (6, 1, 12))]
    appels = [{"id": f"loi{i}", "f": f, "args": a} for i, (f, a, _) in enumerate(lois)]
    appels += [
        {"id": "wilson", "f": "wilson", "args": [37, 140, float(stats.norm.ppf(.975))]},
        {"id": "wilson196", "f": "wilson", "args": [37, 140]},
        {"id": "desc", "f": "descriptif", "args": [z.tolist()]},
        {"id": "pearson", "f": "pearson", "args": [x.tolist(), y.tolist()]},
        {"id": "spearman", "f": "spearman", "args": [x.tolist(), z.tolist()]},
        {"id": "kendall", "f": "kendall", "args": [x.tolist(), y.tolist()]},
        {"id": "khi2", "f": "khi2", "args": [q1, q2]},
        {"id": "welch", "f": "welch", "args": [g[0], g[1]]},
        {"id": "anova", "f": "anova", "args": [g]},
        {"id": "kruskal", "f": "kruskal", "args": [g]},
        {"id": "mw", "f": "mannWhitney", "args": [g[0], g[2]]},
        {"id": "reg", "f": "regression", "args": [X.tolist(), y.tolist(), ["x", "z", "u"]]},
        {"id": "jacobi", "f": "jacobi", "args": [np.corrcoef(X.T).tolist()]},
        {"id": "acp", "f": "acp", "args": [X.tolist(), ["x", "z", "u"], {"permutations": 5}]},
        {"id": "acf", "f": "acf", "args": [serie.tolist(), 20]},
        {"id": "pacf", "f": "pacf", "args": [serie.tolist(), 20]},
        {"id": "lb", "f": "ljungBox", "args": [serie.tolist(), 14]},
        {"id": "adf", "f": "adf", "args": [serie.tolist(), 7]},
        {"id": "kpss", "f": "kpss", "args": [serie.tolist()]},
        {"id": "perio", "f": "periodogramme", "args": [serie[:64].tolist()]},
        {"id": "met", "f": "metriques", "args": [serie[300:].tolist(), serie[299:-1].tolist(), 1.3]},
        {"id": "dm", "f": "dieboldMariano", "args": [(serie[300:] - serie[299:-1]).tolist(), (serie[300:] - serie[293:-7]).tolist()]},
        {"id": "ses", "f": "modeles.ses", "args": [serie.tolist(), 300]},
        {"id": "ar", "f": "modeles.ar", "args": [ar.tolist(), 300, 6]},
        {"id": "sarima", "f": "sarima", "args": [ar.tolist(), {"p": 1, "q": 1, "d": 0}]},
    ]
    r = outil({"tache": "statistiques", "appels": appels})

    for i, (f, a, ref) in enumerate(lois):
        ok, e = proche(r[f"loi{i}"], ref, 1e-7)
        noter("B", f"{f}({', '.join(map(str, a))})", ok, f"outil {r[f'loi{i}']:.10g}, référence {ref:.10g}")
    lo, hi = proportion_confint(37, 140, method="wilson")
    noter("B", "intervalle de Wilson 37/140 (z exact)", proche(r["wilson"], [lo, hi], 1e-9)[0], f"[{lo:.4f} ; {hi:.4f}]")
    # L'outil prend z = 1,96 (arrondi usuel) au lieu de 1,959964 : écart sur la 5e décimale, sans effet à l'affichage.
    noter("B", "intervalle de Wilson avec z = 1,96 (réglage de l'outil)", proche(r["wilson196"], [lo, hi], 1e-4)[0],
          f"[{r['wilson196'][0]:.5f} ; {r['wilson196'][1]:.5f}]")

    d = r["desc"]
    ref = {"moyenne": z.mean(), "mediane": np.median(z), "variance": z.var(ddof=1), "ecart": z.std(ddof=1),
           "asymetrie": stats.skew(z, bias=False), "aplatissement": stats.kurtosis(z, bias=False),
           "q1": np.quantile(z, .25), "q3": np.quantile(z, .75), "p5": np.quantile(z, .05), "p95": np.quantile(z, .95),
           "jb": stats.jarque_bera(z).statistic, "pJb": stats.jarque_bera(z).pvalue,
           "icBas": stats.t.interval(.95, n - 1, z.mean(), stats.sem(z))[0], "icHaut": stats.t.interval(.95, n - 1, z.mean(), stats.sem(z))[1],
           "mad": np.median(np.abs(z - np.median(z)))}
    for k, v in ref.items():
        noter("B", f"descriptif : {k}", proche(d[k], v, 1e-7)[0], f"{d[k]:.6g} / {v:.6g}")

    pr = stats.pearsonr(x, y)
    noter("B", "Pearson r et p", proche([r["pearson"]["r"], r["pearson"]["p"]], [pr.statistic, pr.pvalue], 1e-7)[0])
    sp = stats.spearmanr(x, z)
    noter("B", "Spearman ρ et p", proche([r["spearman"]["r"], r["spearman"]["p"]], [sp.statistic, sp.pvalue], 1e-7)[0])
    kd = stats.kendalltau(x, y, method="asymptotic")
    noter("B", "Kendall τ-b et p (asymptotique)", proche([r["kendall"]["tau"], r["kendall"]["p"]], [kd.statistic, kd.pvalue], 1e-7)[0])
    tab = pd.crosstab(pd.Series(q1), pd.Series(q2))
    c2 = stats.chi2_contingency(tab, correction=False)
    v = np.sqrt(c2.statistic / (len(q1) * (min(tab.shape) - 1)))
    noter("B", "khi-deux, p et V de Cramér", proche([r["khi2"]["chi2"], r["khi2"]["p"], r["khi2"]["v"]], [c2.statistic, c2.pvalue, v], 1e-7)[0])
    w = stats.ttest_ind(g[0], g[1], equal_var=False)
    noter("B", "t de Welch et p", proche([r["welch"]["t"], r["welch"]["p"]], [w.statistic, w.pvalue], 1e-7)[0])
    an = stats.f_oneway(*g)
    noter("B", "ANOVA F et p", proche([r["anova"]["f"], r["anova"]["p"]], [an.statistic, an.pvalue], 1e-7)[0])
    kw = stats.kruskal(*g)
    noter("B", "Kruskal-Wallis H et p (sans ex æquo)", proche([r["kruskal"]["h"], r["kruskal"]["p"]], [kw.statistic, kw.pvalue], 1e-7)[0])
    mw = stats.mannwhitneyu(g[0], g[2], method="asymptotic", use_continuity=False)
    noter("B", "Mann-Whitney U et p", proche([r["mw"]["u"], r["mw"]["p"]], [mw.statistic, mw.pvalue], 1e-7)[0])

    ols = OLS(y, add_constant(X)).fit()
    rg = r["reg"]
    noter("B", "régression : coefficients", proche([c["b"] for c in rg["coef"]], ols.params, 1e-7)[0])
    noter("B", "régression : erreurs-types", proche([c["se"] for c in rg["coef"]], ols.bse, 1e-7)[0])
    noter("B", "régression : p-valeurs", proche([c["p"] for c in rg["coef"]], ols.pvalues, 1e-6)[0])
    noter("B", "régression : R², R² ajusté, F, p(F)", proche([rg["r2"], rg["r2a"], rg["f"], rg["pF"]], [ols.rsquared, ols.rsquared_adj, ols.fvalue, ols.f_pvalue], 1e-7)[0])

    R = np.corrcoef(X.T)
    noter("B", "valeurs propres (Jacobi)", proche(r["jacobi"]["valeurs"], np.sort(np.linalg.eigvalsh(R))[::-1], 1e-9)[0])
    acp = r["acp"]
    lam = np.sort(np.linalg.eigvalsh(R))[::-1]
    p = R.shape[0]
    bart = -(n - 1 - (2 * p + 5) / 6) * np.log(np.linalg.det(R))
    inv = np.linalg.inv(R)
    part = -inv / np.sqrt(np.outer(np.diag(inv), np.diag(inv)))
    hors = ~np.eye(p, dtype=bool)
    kmo = (R[hors] ** 2).sum() / ((R[hors] ** 2).sum() + (part[hors] ** 2).sum())
    noter("B", "ACP : valeurs propres, Bartlett, KMO", proche([*acp["valeurs"], acp["bartlett"]["chi2"], acp["kmo"]], [*lam, bart, kmo], 1e-8)[0])
    Z = (X - X.mean(0)) / X.std(0, ddof=1)
    sc = Z @ np.array(acp["vecteurs"]).T
    noter("B", "ACP : coordonnées des individus", proche(np.abs(acp["scores"]), np.abs(sc), 1e-8)[0])

    noter("B", "ACF", proche(r["acf"], sm_acf(serie, nlags=20, fft=False), 1e-9)[0])
    noter("B", "PACF (Durbin-Levinson)", proche(r["pacf"], sm_pacf(serie, nlags=20, method="ldb"), 1e-8)[0])
    lb = acorr_ljungbox(serie, lags=[14])
    noter("B", "Ljung-Box Q et p", proche([r["lb"]["q"], r["lb"]["p"]], [lb["lb_stat"].iloc[0], lb["lb_pvalue"].iloc[0]], 1e-8)[0])
    noter("B", "ADF (statistique, 7 retards)", proche(r["adf"]["stat"], adfuller(serie, maxlag=7, autolag=None, regression="c")[0], 1e-8)[0])
    noter("B", "KPSS (statistique)", proche(r["kpss"]["stat"], sm_kpss(serie, regression="c", nlags=r["kpss"]["retards"])[0], 1e-8)[0])
    s64 = serie[:64]
    four = np.abs(np.fft.fft(s64 - s64.mean())) ** 2 / 64
    noter("B", "périodogramme", proche([c["puissance"] for c in r["perio"]], four[1:33], 1e-8)[0])

    yv, pv = serie[300:], serie[299:-1]
    e = yv - pv
    ref = [np.abs(e).mean(), np.sqrt((e ** 2).mean()), 100 * np.mean(np.abs(e / yv)), 100 * np.mean(2 * np.abs(e) / (np.abs(yv) + np.abs(pv))), np.abs(e).mean() / 1.3, e.mean()]
    m = r["met"]
    noter("B", "MAE, RMSE, MAPE, sMAPE, MASE, biais", proche([m["mae"], m["rmse"], m["mape"], m["smape"], m["mase"], m["biais"]], ref, 1e-10)[0])
    d_ = e ** 2 - (serie[300:] - serie[293:-7]) ** 2
    dm = d_.mean() / np.sqrt(d_.var() / len(d_)) * np.sqrt((len(d_) - 1) / len(d_))
    noter("B", "Diebold-Mariano (Harvey-Leybourne-Newbold)", proche([r["dm"]["stat"], r["dm"]["p"]], [dm, 2 * stats.t.sf(abs(dm), len(d_) - 1)], 1e-9)[0])

    # Modèles : l'outil doit atteindre le minimum de sa fonction de coût (somme des carrés des erreurs un pas
    # en avant sur l'apprentissage). Juge : une recherche exhaustive fine (lissage) ou statsmodels (AR).
    def sse_ses(a, yy, fin):
        l, s = yy[0], 0.0
        for t_ in range(1, fin):
            s += (yy[t_] - l) ** 2
            l = a * yy[t_] + (1 - a) * l
        return s
    a_outil = r["ses"]["params"]["alpha"]
    grille = np.linspace(0.001, 0.999, 999)
    a_ref = grille[np.argmin([sse_ses(a, serie, 300) for a in grille])]
    noter("B", "lissage exponentiel : α minimise la somme des carrés", sse_ses(a_outil, serie, 300) <= sse_ses(a_ref, serie, 300) * (1 + 1e-6),
          f"α outil {a_outil:.4f}, recherche exhaustive {a_ref:.3f}")
    p_ar = len(r["ar"]["coef"]) - 1
    ref_ar = AutoReg(ar[:300], lags=p_ar, trend="c").fit().params
    noter("B", f"AR({p_ar}) : coefficients des moindres carrés", proche(r["ar"]["coef"], ref_ar, 1e-7)[0])
    noter("B", "AR : ordre choisi = vrai ordre (2) ou voisin", p_ar in (2, 3), f"ordre {p_ar}")
    ph, th, c = r["sarima"]["params"]["phi"][0], r["sarima"]["params"]["theta"][0], r["sarima"]["params"]["c"]

    def css(phi, theta, cc):
        e_, s = np.zeros(len(ar)), 0.0
        for t_ in range(1, len(ar)):
            e_[t_] = ar[t_] - (cc + phi * ar[t_ - 1] + theta * e_[t_ - 1])
            s += e_[t_] ** 2
        return s
    meilleur = min(css(a, b, cc) for a in np.linspace(.5, .95, 46) for b in np.linspace(-.5, .5, 51) for cc in np.linspace(.2, 3.2, 31))
    noter("B", "ARMA(1,1) par CSS : minimum atteint (Nelder-Mead contre grille)", css(ph, th, c) <= meilleur * (1 + 1e-6),
          f"CSS outil {css(ph, th, c):.3f}, meilleure grille {meilleur:.3f}")


# ── C. Cas calculés à la main ──────────────────────────────────────────────────────────────
def partie_main() -> None:
    print("\nC. CAS CALCULÉS À LA MAIN")
    # Un séjour du 01 au 04 (3 nuits), entrée 9 h, sortie 15 h :
    #   minuit  : 1, 1, 1, 0     (nuits du 01, 02, 03)
    #   journée : 1, 1, 1, 1
    #   pondéré : 1 − 9/24 = 0,625 ; 1 ; 1 ; 15/24 = 0,625 ; total 3,25 = 3 + (15 − 9)/24 (loi de Little : W = n + b − a)
    s = pd.DataFrame({"entree": pd.to_datetime(["2025-03-01"]), "sortie": pd.to_datetime(["2025-03-04"]),
                      "sortie_basse": pd.to_datetime(["2025-03-04"]), "statut": ["observee"], "p_inclusif": [0.0], "issue": ["Sortie"]})
    h = HeuresPresence(9, 15, 6)
    att = {"minuit": [1, 1, 1, 0], "journee": [1, 1, 1, 1], "pondere": [0.625, 1, 1, 0.625]}
    for c, v in att.items():
        occ = reconstituer_occupation(s, "2025-03-06", debut="2025-03-01", comptage=c, heures=h)
        noter("C", f"séjour de 3 nuits, {c}", proche(occ["presents"].to_numpy()[:4], v, 1e-12)[0], f"attendu {v}")
    # Même jour (MEO de 6 h) : minuit 0, journée 1, pondéré 6/24 = 0,25.
    s2 = s.assign(sortie=pd.to_datetime(["2025-03-01"]), sortie_basse=pd.to_datetime(["2025-03-01"]))
    for c, v in {"minuit": 0, "journee": 1, "pondere": 0.25}.items():
        occ = reconstituer_occupation(s2, "2025-03-03", debut="2025-03-01", comptage=c, heures=h)
        noter("C", f"séjour du même jour, {c}", abs(occ["presents"].iloc[0] - v) < 1e-12, f"attendu {v}")
    # Sortie calculée ambiguë (n = 2 jours, part inclusive p = 0,4) : fins possibles le 02 (poids 0,4) et le 03 (0,6).
    #   minuit : 01 → 1 ; 02 → 0,6 ; 03 → 0     journée : 1 ; 1 ; 0,6
    s3 = s.assign(sortie=pd.to_datetime(["2025-03-03"]), sortie_basse=pd.to_datetime(["2025-03-02"]),
                  statut=["calculee"], p_inclusif=[0.4])
    for c, v in {"minuit": [1, .6, 0], "journee": [1, 1, .6]}.items():
        occ = reconstituer_occupation(s3, "2025-03-05", debut="2025-03-01", comptage=c)
        noter("C", f"sortie calculée ambiguë (p = 0,4), {c}", proche(occ["presents"].to_numpy()[:3], v, 1e-12)[0], f"attendu {v}")
    # Wilson 0/10 : [0 ; 0,2775] ; Little : 3 admissions par jour × 4 nuits = 12 présents.
    lo, hi = proportion_confint(0, 10, method="wilson")
    noter("C", "Wilson 0 sur 10 = [0 ; 0,2775]", abs(lo) < 1e-12 and abs(hi - 0.27753) < 1e-4)


def rapport() -> int:
    ecarts = [x for x in RESULTATS if not x[3]]
    titres = {"A": "A. Occupation : outil (JavaScript) = Python = force brute",
              "B": "B. Bibliothèque statistique de l'outil contre scipy, statsmodels, numpy",
              "C": "C. Cas calculés à la main"}
    lignes = ["# Rapport de vérification des calculs", "",
              "Produit par `verification/verifier_calculs.py` sur des **données fictives** (registre inventé, séries simulées).",
              "Les bibliothèques de référence ne servent qu'à juger : aucun calcul de l'outil ni des modèles ne les utilise.", "",
              f"**{len(RESULTATS) - len(ecarts)} calculs justes sur {len(RESULTATS)}**" + (f", {len(ecarts)} écart(s)." if ecarts else "."), ""]
    for k, t in titres.items():
        lignes += [f"## {t}", "", "| Calcul | Verdict | Détail |", "|---|---|---|"]
        lignes += [f"| {c} | {'juste' if ok else '**ÉCART**'} | {d} |" for p, c, d, ok in RESULTATS if p == k]
        lignes.append("")
    (ICI / "rapport_verification.md").write_text("\n".join(lignes), encoding="utf-8")
    print(f"\n{len(RESULTATS) - len(ecarts)} calculs justes sur {len(RESULTATS)}. Rapport : verification/rapport_verification.md")
    return 1 if ecarts else 0


if __name__ == "__main__":
    partie_occupation()
    partie_statistiques()
    partie_main()
    sys.exit(rapport())
