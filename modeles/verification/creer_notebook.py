"""
Crée (ou recrée) le notebook modeles/pipeline.ipynb : toute la chaîne du mémoire, cellule par cellule,
avec les explications en français. Le notebook est enregistré SANS sorties : les résultats calculés sur les
vraies données restent sur l'ordinateur (avant tout envoi sur GitHub : « Effacer toutes les sorties »).

    ~/memoire-env/bin/python verification/creer_notebook.py
"""
from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cellules = [
    md(r"""# Chaîne complète du mémoire — de la saisie à la prévision

Prévision de l'occupation des lits de pédiatrie par SVR quantile (PyTorch, écrit à la main).

Ce notebook rejoue **toute la chaîne** sur la dernière version du fichier exporté par l'outil de saisie. Il est à relancer
à chaque nouvelle version de la saisie (les corrections de dates, les trous comblés…) : *Exécuter tout*.

| Étape | Ce qu'elle fait | Durée |
|---|---|---|
| 0 | Réglages | — |
| 1 | Vérification de tous les calculs sur des données fictives (outil = Python = calcul direct) | 1 min |
| 2 | Conversion du CSV de l'outil vers le format NERA, corrections de dates | quelques s |
| 3 | Occupation selon les trois méthodes de comptage, pic de la journée, loi de Little | 1 min |
| 4 | Capacité incertaine : scénarios de 15 à 20 lits | 1 min |
| 5 | Entraînement des niveaux 0 à 5 (SVR) | long |
| 6 | Bancs d'essai : choix (D1–D11), prétraitement (P1–P8), paramètres | très long |
| 7 | Figures et rapports | — |

**Données sensibles** : rien ne sort de l'ordinateur. `donnees/` et `resultats/` ne vont jamais sur GitHub, et ce notebook doit
être envoyé **sans sorties** (menu *Modifier → Effacer toutes les sorties*).

Lancement, dans un terminal Ubuntu (WSL) :
```
cd /mnt/c/Users/User/Desktop/backend/modeles
~/memoire-env/bin/jupyter lab pipeline.ipynb
```"""),
    md(r"""## 0. Réglages

- `SOURCE` : le CSV exporté de l'outil de saisie (tous les mois).
- `LITS` : capacité de référence. `LITS_FICHIER` : fichier `date_debut;lits` si la date du passage de 15 à 20 lits est connue.
- `COMPTAGES` : méthodes de comptage étudiées (voir l'étape 3).
- `HEURES` : heures typiques pour la méthode pondérée (entrée, sortie, durée d'un séjour du même jour).
- `LANCER_LONG` : `False` saute les étapes longues (5 et 6) ; mettre `True` pour les lancer d'ici.
- `RAPIDE` : version courte des bancs d'essai (moins d'itérations), pour un premier essai."""),
    code(r"""import subprocess, sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Markdown, Image, display

SOURCE = "/mnt/c/Users/User/Desktop/MEMOIRE/saisie_ia/registre-ped-tous-les-mois.csv"
LITS = 20
LITS_FICHIER = None                  # par exemple "donnees/lits_PED.csv"
COMPTAGES = ["minuit", "journee", "pondere"]
HEURES = (12, 11, 8)                 # heure d'entrée, heure de sortie, durée (h) d'un séjour du même jour
HORIZONS = [1, 7]
LANCER_LONG = False
RAPIDE = True

PY = sys.executable
EXPORT = "donnees/export_outil_PED.csv"
Path("donnees").mkdir(exist_ok=True); Path("resultats").mkdir(exist_ok=True)

def lancer(*args):
    # Lance un script de la chaîne et affiche sa sortie au fil de l'eau.
    p = subprocess.Popen([PY, *map(str, args)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for ligne in p.stdout:
        print(ligne, end="")
    if p.wait():
        raise RuntimeError(f"échec : {' '.join(map(str, args))}")

def rapport(nom):
    # Affiche un rapport Markdown de resultats/ s'il existe.
    f = Path("resultats") / nom
    display(Markdown(f.read_text(encoding="utf-8")) if f.exists() else Markdown(f"*{nom} : pas encore produit.*"))

capacite = ["--lits-fichier", LITS_FICHIER] if LITS_FICHIER else ["--lits", LITS]"""),
    md(r"""## 1. Vérification de tous les calculs

Avant de regarder les résultats, on vérifie que **les calculs sont justes**, sur un registre **inventé** (aucune donnée du stage) :

- **A. Occupation** — le vrai code de l'outil de saisie (JavaScript, exécuté par Node), la chaîne Python et un calcul direct
  écrit à partir des définitions (séjour par séjour, jour par jour) doivent donner les mêmes nombres chaque jour, pour les trois
  méthodes de comptage, la fourchette, le pic de la journée et une capacité qui passe de 15 à 20 lits.
- **B. Statistiques de l'outil** — chaque fonction de `statistiques.js` (lois de probabilité, tests, régression, ACP, séries
  temporelles, modèles de prévision, métriques) est comparée à scipy, statsmodels et numpy, utilisés seulement comme juges.
- **C. Cas calculés à la main.**

Un seul « ÉCART » doit faire arrêter l'analyse et corriger le calcul concerné."""),
    code(r"""lancer("-m", "verification.verifier_calculs")"""),
    md(r"""## 2. Conversion du CSV de l'outil

`nera.depuis_outil` applique **les mêmes règles que l'import de NERA** : dates lues (un « ? » final est ignoré), nombre de jours
plausible (au plus 90), issue harmonisée (sortie, SCAM, décès, transfert, évasion), entrée déduite si illisible.

Garde-fou supplémentaire : une date d'entrée à plus de 30 jours avant (ou 10 jours après) la date d'enregistrement est une faute
de frappe sur l'année ou le mois. Elle est corrigée **et listée** dans `donnees/corrections_dates_PED.csv` : ces lignes sont à
corriger dans l'outil de saisie, la source doit rester juste."""),
    code(r"""lancer("-m", "nera.depuis_outil", SOURCE, "--service", "PED", "--sortie", EXPORT)
corr = Path("donnees/corrections_dates_PED.csv")
if corr.exists():
    display(pd.read_csv(corr, sep=";")[["ligne", "numero_ordre", "date_enregistrement", "entree_ecrite", "entree_retenue", "correction"]])"""),
    md(r"""## 3. Occupation selon les trois méthodes de comptage

Pour un séjour d'entrée $e$ et de sortie $S$ (en jours), avec les heures typiques $h_e$ (entrée), $h_s$ (sortie) et $m$
(durée d'un séjour du même jour) :

| Méthode | Présence le jour $d$ | Loi de Little : durée $W$ |
|---|---|---|
| Recensement de minuit | $\mathbb 1[e \le d < S]$ | $n$ nuits |
| Présence dans la journée | $\mathbb 1[e \le d \le S]$ | $n + 1$ |
| Pondérée par le temps | $1 - h_e/24$ le jour d'entrée, $1$ les jours pleins, $h_s/24$ le jour de sortie, $m/24$ si $e = S$ | $n + (h_s - h_e)/24$, ou $m/24$ |

Le **taux d'occupation** de la période est $\mathrm{TOM} = \sum_d \text{présents}_d \,/\, \sum_d \text{lits}_d$ (capacité du jour).

Le **pic de la journée** (plus grand nombre d'enfants présents en même temps) est encadré **exactement**, sans hypothèse d'heure :
$\max(\text{minuit}_{d-1}, \text{minuit}_d) \le \text{pic}_d \le \text{journée}_d$.

Une sortie seulement calculée (entrée + nombre de jours) est ambiguë : $n$ nuits ou $n$ jours entrée et sortie comprises. Elle
compte pour $p$ (part de lignes inclusives mesurée) sur $e + n - 1$ et $1 - p$ sur $e + n$ ; la **fourchette** donne $p = 1$ (bas)
et $p = 0$ (haut)."""),
    code(r"""for c in COMPTAGES:
    print(f"\n════════ {c} ════════")
    lancer("rapport_occupation.py", EXPORT, "--service", "PED", *capacite, "--inconnues", "estimee",
           "--fenetre-censure", "p95", "--rodage-debut", "--comptage", c,
           "--heure-entree", HEURES[0], "--heure-sortie", HEURES[1], "--duree-meme-jour", HEURES[2],
           "--scenarios-lits", 15, 16, 17, 18, 19, 20)"""),
    md(r"""### Les trois méthodes côte à côte

Lecture : si les trois courbes racontent la même histoire (mêmes pics, même saison), la conclusion ne dépend pas de la façon
de compter. En général : journée ≥ minuit ≈ pondérée. La bande grise est l'encadrement du pic de la journée."""),
    code(r"""from lancer_niveaux import etiquette
occ = {c: pd.read_csv(f"resultats/occupation_{etiquette('PED', c)}.csv", sep=";", index_col=0, parse_dates=True) for c in COMPTAGES}
m = {c: o["presents"].resample("MS").mean() for c, o in occ.items()}
fig, ax = plt.subplots(figsize=(12, 4.5))
o = occ[COMPTAGES[0]]
ax.fill_between(o.index, o["pic_bas"].rolling(7, center=True).mean(), o["pic_haut"].rolling(7, center=True).mean(),
                color="0.85", label="pic de la journée (encadrement, moyenne 7 j)")
for c, couleur in zip(COMPTAGES, ["#1f77b4", "#d62728", "#2ca02c"]):
    ax.plot(occ[c].index, occ[c]["presents"].rolling(7, center=True).mean(), color=couleur, label=f"{c} (moyenne 7 j)")
if "lits" in o:
    ax.step(o.index, o["lits"], where="post", color="k", ls="--", lw=1, label="lits")
ax.set_ylabel("enfants présents"); ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=.3)
plt.show()

tab = pd.DataFrame({c: {"présents moyens": o["presents"].mean(), "TOM (%)": 100 * o["presents"].sum() / o["lits"].sum() if "lits" in o else None,
                        "jours > lits": int((o["presents"] > o["lits"]).sum()) if "lits" in o else None,
                        "pic : borne basse moyenne": o["pic_bas"].mean(), "pic : borne haute moyenne": o["pic_haut"].mean()}
                    for c, o in occ.items()}).round(2)
tab"""),
    md(r"""### Loi de Little (garde-fou de cohérence)

$L = \lambda W$ : présents moyens = admissions par jour × durée moyenne, avec la durée **qui correspond à la méthode**
(tableau ci-dessus). Un écart de plus de 10 % signale un problème de données (sorties oubliées, dates fausses)."""),
    code(r"""from nera.chargement import lire_export, preparer_sejours
from nera.garde_fous import verifier_little
from nera.occupation import HeuresPresence
from nera.verrou import DATE_VERROU
df = lire_export(EXPORT)
sejours, _ = preparer_sejours(df, "PED", DATE_VERROU, "p95", "estimee")
h = HeuresPresence(*HEURES)
pd.DataFrame({c: verifier_little(occ[c], sejours, comptage=c, heures=h) for c in COMPTAGES}).T"""),
    md(r"""## 4. Capacité incertaine : de 15 à 20 lits

Le service est passé de 15 à 20 lits entre 2024 et 2026, à une date inconnue, et tous ne sont peut-être pas opérationnels.
Tant que la date n'est pas confirmée, le taux est présenté comme une **plage** : avec 15 lits (borne haute du taux) et avec
20 lits (borne basse). Dès que la date est connue, remplir `LITS_FICHIER` (étape 0) et relancer."""),
    code(r"""pd.concat({c: pd.read_csv(f"resultats/scenarios_lits_{etiquette('PED', c)}.csv", sep=";", index_col=0) for c in COMPTAGES})"""),
    md(r"""## 5. Entraînement des niveaux 0 à 5

| Niveau | Modèle | Ce qu'il ajoute |
|---|---|---|
| 0 | persistance, saisonnier, moyenne mobile | la barre à battre, sans apprentissage |
| 1 | SVR linéaire, perte ε-insensible | un hyperplan $f(x) = w \cdot x + b$ et son tube $\pm\varepsilon$ |
| 2 | SVR à noyau RBF | des relations non linéaires |
| 3 | SVR quantile (perte pinball) | les coûts asymétriques ($\tau = 0{,}8$) et l'intervalle à 90 % |
| 4 | SVR quantile à noyau composite | deux blocs de variables mélangés par un poids $\beta$ appris |
| 5 | empilement | combinaison apprise des niveaux 3, 4 et de la persistance |

- Fonction minimisée (forme primale) : $J(w, b) = \tfrac12\lVert w\rVert^2 + C \sum_i L\big(y_i - f(x_i)\big)$, ou avec un noyau
  $J(\alpha, b) = \tfrac12\alpha^\top K\alpha + C \sum_i L(y_i - f_i)$, $f = K\alpha + b$.
- Perte $L$ : ε-insensible (niveaux 1-2), pinball ε-insensible $\tau\max(0, r - \varepsilon) + (1 - \tau)\max(0, -r - \varepsilon)$
  (niveaux 3-4).
- Minimisation : descente de gradient (gradients dérivés à la main, vérifiés par différences finies), Adam, direction
  préconditionnée pour les noyaux. Tout est écrit en PyTorch, sans scikit-learn.
- $\tau = 0{,}8$ : prévoir assez de lits 8 jours sur 10 (une pénurie coûte 4 fois un lit vide).
- Validation glissante (origines toutes les 2 semaines) ; **septembre et octobre 2026 ne sont jamais lus** avant la validation
  finale.

Détails et justification de chaque choix : `README.md` (section 10) et `METHODE.md`."""),
    code(r"""if LANCER_LONG:
    for c in COMPTAGES:
        lancer("lancer_niveaux.py", "--service", "PED", "--horizons", *HORIZONS, "--tau", 0.8, "--recherche", "grille", "--comptage", c)
else:
    print("Étape longue sautée (LANCER_LONG = False). Dans un terminal : COMPTAGES=\"minuit journee pondere\" ETAPES=2 bash lancer_tout.sh")"""),
    md(r"""## 6. Bancs d'essai : tout est comparé

- **D1 à D11** (choix de conception) : 23 modèles (références naïves, lissages, Thêta, AR, SARIMA, forêts, boosting, MLP, LSTM,
  SVR), noyau, perte, $\tau$, variables… Chaque variante est comparée au choix retenu par le test de Diebold-Mariano.
- **P1 à P8** (prétraitement) : méthode de comptage, durées inconnues, rodage, censure, convention des jours, transformation…
- **Paramètres** : erreur selon chaque paramètre (C, ε, γ, nombre de caractéristiques, pas d'Adam…), valeur retenue cerclée.

Lecture de la colonne « vs choix retenu » : *équivalent* (choix défendable), *moins bon* (argument pour le choix),
*meilleur* (**choix à revoir**)."""),
    code(r"""if LANCER_LONG:
    r = ["--rapide"] if RAPIDE else []
    for c in COMPTAGES:
        lancer("benchmark_choix.py", "--service", "PED", "--horizons", *HORIZONS, "--comptage", c, *r)
        lancer("benchmark_parametres.py", "--service", "PED", "--horizons", *HORIZONS, "--comptage", c, *r)
    lancer("benchmark_pretraitement.py", EXPORT, "--service", "PED", "--lits", LITS, "--horizons", *HORIZONS, *r)
else:
    print("Étape longue sautée (LANCER_LONG = False). Dans un terminal : ETAPES=\"3 4 5\" bash lancer_tout.sh")
for nom in ("benchmark_PED.md", "pretraitement_PED.md", "parametres_PED.md"):
    rapport(nom)"""),
    md(r"""## 7. Figures

Chaque figure est expliquée dans `outil-saisie/INTERPRETER-LES-GRAPHES.md` (section 9)."""),
    code(r"""if LANCER_LONG:
    for c in COMPTAGES:
        lancer("visualisations.py", "--service", "PED", "--comptage", c, *(["--rapide"] if RAPIDE else []))
for f in sorted(Path("resultats").glob("figures_*/*.png"))[:40]:
    print(f); display(Image(filename=str(f), width=700))"""),
    md(r"""## Validation finale (une seule fois, à la fin)

Septembre 2026 = mois de test ; le modèle est réentraîné avec septembre, puis testé sur octobre (réentraînement mensuel).
Elle se lance **à part**, une seule fois, avec la confirmation demandée par le verrou (voir `README.md`, section validation
finale). Elle n'est volontairement pas dans ce notebook."""),
]
nb = nbf.v4.new_notebook(cells=cellules, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                                   "language_info": {"name": "python"}})
chemin = Path(__file__).resolve().parent.parent / "pipeline.ipynb"
nbf.write(nb, chemin)
print("notebook écrit :", chemin)
