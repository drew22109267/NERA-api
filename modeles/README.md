# Prévision de l'occupation des lits hospitaliers par machines à vecteurs de support

*Code du mémoire : application des SVM aux projets de santé au Cameroun. Prévision de l'occupation
des lits d'un service de pédiatrie par une architecture SVR révisée : coûts asymétriques
(régression quantile), noyau composite à poids appris, empilement de modèles.*

Ce dossier contient tout le code d'analyse et de modélisation du mémoire, ainsi que l'outil de
saisie des registres papier. Ce document est écrit pour qu'une personne qui reprend le travail
puisse, sans autre aide :

1. installer et lancer chaque partie ;
2. comprendre le parcours des données, du registre papier jusqu'à la prévision ;
3. retrouver **toutes les formules mathématiques** utilisées, avec leur justification ;
4. savoir quel fichier fait quoi, dans quel ordre lancer les scripts et comment lire les résultats ;
5. savoir ce qui reste à faire.

Tous les calculs sont écrits à la main. Les modèles utilisent PyTorch uniquement comme
bibliothèque de tenseurs : les gradients sont dérivés analytiquement, les optimiseurs (descente
de gradient, momentum, Adam) et les métriques sont codés dans le dépôt. **Aucune importation de
scikit-learn, statsmodels ou bibliothèque statistique.** pandas sert à lire les fichiers et à
manipuler les dates, matplotlib à dessiner. L'outil de saisie est en JavaScript sans aucune
dépendance externe.

Les nombres cités en exemple dans les parties mathématiques sont **fictifs** : ils illustrent la
lecture des formules et ne sont pas des résultats du mémoire.

---

## Sommaire

1. [Organisation du dépôt](#1-organisation-du-dépôt)
2. [Installation et lancement](#2-installation-et-lancement)
3. [Le parcours des données](#3-le-parcours-des-données)
4. [Confidentialité et période de test verrouillée](#4-confidentialité-et-période-de-test-verrouillée)
5. [Mathématiques A : reconstitution de l'occupation](#5-mathématiques-a--reconstitution-de-loccupation)
6. [Mathématiques B : validation de l'occupation](#6-mathématiques-b--validation-de-loccupation)
7. [Mathématiques C : statistiques descriptives et tests](#7-mathématiques-c--statistiques-descriptives-et-tests)
8. [Mathématiques D : séries temporelles](#8-mathématiques-d--séries-temporelles)
9. [Mathématiques E : modèles de prévision de référence](#9-mathématiques-e--modèles-de-prévision-de-référence)
10. [Mathématiques F : le SVR](#10-mathématiques-f--le-svr)
11. [Mathématiques G : évaluation et comparaison des modèles](#11-mathématiques-g--évaluation-et-comparaison-des-modèles)
12. [Mathématiques H : survie, classification et transfert](#12-mathématiques-h--survie-classification-et-transfert)
13. [Outils numériques internes](#13-outils-numériques-internes)
14. [Fichier par fichier](#14-fichier-par-fichier)
15. [Les scripts, dans l'ordre](#15-les-scripts-dans-lordre)
16. [Les figures et leur lecture](#16-les-figures-et-leur-lecture)
17. [Tests](#17-tests)
18. [État d'avancement et suite du travail](#18-état-davancement-et-suite-du-travail)
19. [Références](#19-références)

---

## 1. Organisation du dépôt

```
modeles/
├── README.md                  ce document
├── nera/                      des registres à l'occupation (lecture, statuts, recensement, indicateurs)
├── svr/                       les modèles, écrits à la main (pertes, noyaux, optimiseurs, SVR, validation…)
├── tests/                     tests automatiques (pytest)
├── outil-saisie/              outil web de saisie et d'analyse des registres (HTML + JavaScript)
├── rapport_occupation.py      étape 1 : export → occupation et indicateurs
├── lancer_niveaux.py          étape 2 : ablation des niveaux 0 à 5
├── sensibilite.py             étape 3 : sensibilité à la convention des jours
├── benchmark_choix.py         étape 3 bis : banc de comparaison de chaque choix (D1 à D10)
├── visualisations.py          étape 4 : toutes les figures
├── validation_finale.py       étape 5 : test final sur la période verrouillée (une seule fois)
├── modele_survie.py           étape 6 : probabilités de sortie J0 / J1 / J2
├── transfert.py               étape 7 : services à historique court et total de l'hôpital
├── qualite_saisie.py          contrôle de la double saisie
└── demo_entrainement.py       démonstration pas à pas de l'entraînement d'un SVR
```

Deux dossiers sont créés à l'usage et **ne sont jamais versionnés** (données de patients) :
`donnees/` (fichiers d'entrée) et `resultats/` (sorties). Le `.gitignore` du dépôt les exclut,
ainsi que toutes les photos, tous les CSV et tous les JSON de l'outil de saisie.

Le reste du dépôt (`HopitalApi/`) est l'API .NET de l'application hospitalière ; son
fonctionnement est décrit dans le `README.md` à la racine.

---

## 2. Installation et lancement

### 2.1 Les modèles Python

Les scripts s'exécutent sous Linux. Sous Windows, ils tournent dans **WSL (Ubuntu)** : la
politique de sécurité de Windows (Smart App Control) bloque les bibliothèques compilées de
PyTorch lancées directement depuis Windows.

Installation une seule fois, dans un terminal Ubuntu :

```bash
python3 -m venv ~/memoire-env
~/memoire-env/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
~/memoire-env/bin/pip install pandas matplotlib pytest
```

Toutes les commandes se lancent depuis ce dossier :

```bash
cd /mnt/c/Users/<utilisateur>/Desktop/backend/modeles
~/memoire-env/bin/python <script>.py <options>
```

Tous les calculs sont faits en double précision (`torch.float64`) sur processeur.

### 2.2 L'outil de saisie

Aucune installation. Ouvrir `outil-saisie/saisie.html` dans Chrome ou Edge (double-clic), ou le
servir par un petit serveur local depuis le dossier `Desktop` :

```bash
python3 -m http.server 8765
```

puis ouvrir `http://localhost:8765/backend/modeles/outil-saisie/saisie.html`. Le mode d'emploi
complet de l'outil (saisie, raccourcis, contrôle qualité, sauvegarde, ajout d'un service) est
dans [`outil-saisie/LISEZMOI.md`](outil-saisie/LISEZMOI.md).

Les données saisies restent dans le navigateur (stockage local) et dans les fichiers de
sauvegarde `.json` que l'on télécharge à chaque séance. Rien n'est envoyé sur internet.

### 2.3 L'API

Voir le `README.md` à la racine du dépôt (.NET 8, PostgreSQL).

---

## 3. Le parcours des données

```
Registre papier (photos masquées : noms, téléphones, médecin, facture cachés)
    │  outil-saisie/saisie.html     recopie ligne par ligne, contrôle qualité, analyses en direct
    ▼
CSV du registre  ──(import dans l'application NERA)──►  base PostgreSQL
                                                          │
                                         export « dataset harmonisé » (CSV séparé par « ; »)
                                                          ▼
donnees/<export>.csv
    │  nera/chargement.py      lecture, période verrouillée, statut de chaque sortie, convention des jours
    │  nera/imputation.py      durées inconnues : exclues ou estimées (prix, issue)
    ▼
séjours (entrée, sortie, sortie basse, part inclusive p, statut, issue, durée)
    │  nera/occupation.py      recensement de minuit : enfants présents chaque soir
    ▼
occupation jour par jour (attendue, borne basse, borne haute)       ← rapport_occupation.py
    │  svr/caracteristiques.py une ligne par jour : 7 retards, flux, calendrier → cible au jour t + h
    ▼
tableau X (variables), y (occupation du jour cible)
    │  svr/validation.py       découpages dans le temps (validation glissante, sans fuite)
    │  svr/modeles.py          entraînement des SVR (gradients à la main, Adam)
    ▼
prévisions → svr/metriques.py (MAE, pinball, couverture, Diebold-Mariano)   ← lancer_niveaux.py
```

L'outil de saisie refait en JavaScript, à l'identique, la reconstitution de l'occupation et les
indicateurs : on peut donc contrôler les résultats pendant la saisie, avant tout export.

---

## 4. Confidentialité et période de test verrouillée

**Confidentialité.** Les registres contiennent des données de patients. Règles appliquées :

- les photos sont masquées avant toute recopie (noms, téléphones, médecin, facture) ;
- ces informations ne sont jamais recopiées ;
- aucune photo, aucun CSV, aucune sauvegarde n'est versionné (voir `.gitignore`) ;
- le code ne contient aucune donnée simulée : toutes les analyses portent sur les registres réels.

**Période verrouillée (coffre-fort).** Les données vont de juillet 2024 à octobre 2026. À partir
du 01/09/2026, rien n'est lu pendant le développement (`nera/verrou.py`) :

- les séjours admis après le verrou sont retirés ;
- les sorties postérieures au verrou sont effacées : le séjour est « encore en cours » au verrou.

Seul `validation_finale.py` (et `transfert.py` avec la même confirmation) ouvre le coffre, avec une
phrase de confirmation obligatoire ; chaque ouverture est inscrite dans
`resultats/coffre_ouvertures.log`. C'est la garantie que le test final mesure ce que le modèle
ferait sur des jours **jamais vus** pendant les choix de modélisation.

---

## 5. Mathématiques A : reconstitution de l'occupation

Code : `nera/chargement.py`, `nera/imputation.py`, `nera/occupation.py`, `nera/indicateurs.py`,
et la fonction `calculerIndicateurs` de `outil-saisie/saisie.html` (mêmes formules).

### 5.1 Notations et statuts d'un séjour

Pour chaque séjour i : e_i la date d'entrée, S_i la date de sortie, n_i le « nombre de jours »
écrit dans le registre. Les dates sont converties en numéros de jour entiers.

| Statut | Situation | Traitement |
|---|---|---|
| observée | date de sortie écrite | S_i = date écrite |
| calculée | pas de date de sortie, nombre de jours écrit | S_i = e_i + n_i ou e_i + n_i − 1 (section 5.3) |
| censurée | ni sortie ni départ écrit, entrée récente (dans la fenêtre de censure avant l'extraction) | présent jusqu'à la date d'extraction |
| estimée (imputée) | ni sortie ni nombre de jours, départ écrit ou entrée ancienne | durée estimée (section 5.5), ou séjour exclu selon le réglage |
| inconnue | rien d'exploitable | exclu et dénombré à part |

Un enfant dont le départ est écrit (sortie, SCAM, décès, référé, évadé, mise en observation)
n'est jamais « encore hospitalisé », même entré récemment.

Durée maximale plausible : un séjour de plus de `MAX_NUITS` nuits est considéré comme une erreur
de saisie de la date de sortie (sortie ignorée, séjour signalé).

### 5.2 Recensement de minuit

Un enfant compte dans l'occupation du jour d s'il est présent à minuit :

```
P_d = Σ_i 1(e_i ≤ d < S_i)
```

Il occupe un lit la nuit de son entrée, mais plus la nuit de sa sortie. Un séjour de 3 nuits
(entrée le 1er, sortie le 4) compte les 1er, 2 et 3. Un enfant entré et sorti le même jour
n'apparaît pas dans l'occupation de minuit, mais compte dans les admissions.

**Calcul par tableau de différences.** On ajoute +1 au jour e_i et −w au jour de chaque sortie
possible (w = poids de cette sortie, section 5.4), puis on fait la somme cumulée. Les séjours
entrés avant le premier jour de la période sont cumulés dans la valeur de départ. Complexité :
O(nombre de séjours + nombre de jours).

L'occupation **n'est pas plafonnée** au nombre de lits : un dépassement est un sureffectif réel
(lit d'appoint, deux enfants par lit) et c'est une information à garder.

### 5.3 Convention du nombre de jours : estimation de p avec rétrécissement

Quand la sortie n'est pas écrite, « n jours » peut vouloir dire :

- n **nuits** : S = e + n ;
- n jours **entrée et sortie comprises** (ligne inclusive) : S = e + n − 1.

Les deux pratiques coexistent selon le médecin. On mesure la part p de lignes inclusives sur les
lignes où **la date de sortie et le nombre de jours sont tous deux écrits** : une ligne est
inclusive si S − e − n = −1, en nuits si S − e − n = 0 (les autres écarts sont des incohérences,
ignorées).

Estimation mois par mois avec **rétrécissement vers la moyenne globale** (estimateur bayésien
empirique) :

```
p_M = (k_M + 10 · p̂) / (n_M + 10)
```

- k_M : lignes inclusives du mois M ; n_M : lignes mesurables du mois M ;
- p̂ = Σ k_M / Σ n_M : part globale ;
- 10 : nombre de « pseudo-lignes » (poids de l'a priori).

Exemple fictif : 30 lignes inclusives sur 40 et p̂ = 0,5 donnent (30 + 5)/(40 + 10) = 0,70 au lieu
de 0,75. Un mois avec 2 lignes mesurables, toutes inclusives, donne (2 + 5)/(2 + 10) = 0,58 au lieu
de 1 : un mois pauvre en données est tiré vers la moyenne au lieu de prendre une valeur extrême.

Si aucune ligne n'est mesurable, p = 0,5.

### 5.4 Trois scénarios : attendu, bas, haut

Pour un séjour calculé, les deux sorties possibles ne diffèrent que d'une nuit, celle du jour
d* = e + n − 1 :

```
P(e ≤ d < S) = 1        pour e ≤ d < d*
             = 1 − p    pour d = d*
             = 0        pour d > d*
```

- **Scénario attendu** : E[P_d] = Σ_i P(e_i ≤ d < S_i). Par linéarité de l'espérance, c'est exact
  sans aucune hypothèse d'indépendance entre séjours. La nuit incertaine compte pour 1 − p. Les
  sorties sont pondérées de même : poids p le jour e + n − 1, poids 1 − p le jour e + n.
- **Scénario bas** : toutes les lignes calculées sont inclusives (p = 1).
- **Scénario haut** : toutes sont en nuits (p = 0).

Comme P_d est croissant en chaque S_i, toute répartition réelle des deux conventions donne une
série comprise entre les scénarios bas et haut : c'est un **encadrement exact** (si seules ces
deux conventions existent), pas un intervalle de confiance. Pour les durées estimées (section
5.5), le scénario bas utilise le 1er quartile et le scénario haut le 3e quartile.

### 5.5 Durées inconnues estimées

Pour un séjour sans sortie ni nombre de jours, trois réglages :

- `exclure` : le séjour n'entre pas dans l'occupation ;
- `mediane` : durée médiane des séjours connus du service ;
- `estimee` (défaut) : durée médiane des séjours connus **de même prix** (au moins 5 séjours) ;
  à défaut, de même issue ; à défaut, médiane du service.

Le prix payé suit la durée (tarification à la journée) : c'est le meilleur substitut disponible.
L'incertitude est gardée : 1er et 3e quartile de la classe (bornes des scénarios bas et haut).
Les durées estimées n'entrent ni dans la DMS ni dans les sorties par issue.

**Validation de l'estimation** (`nera/imputation.py`, `valider_estimation`) : validation croisée
en k plis sur les séjours connus. On cache la durée, on la prédit, on mesure l'erreur absolue
moyenne et la part des prédictions à ±1 nuit, pour chaque méthode.

### 5.6 Rodage, fenêtre de censure, fin de série

- **Rodage** = max(14, p95 des durées connues) jours. Les enfants entrés avant le premier jour
  saisi occupent des lits mais n'apparaissent pas dans les lignes : on attend que la plupart
  soient sortis avant de commencer le calcul.
- **Fenêtre de censure** : un séjour sans sortie est « encore hospitalisé » si son entrée est
  dans les max(7, p95) derniers jours avant l'extraction (réglage `p95`), ou dans un nombre de
  jours fixe (réglage `seuil`).
- **Trou final** : si les derniers numéros d'ordre manquent (pages pas encore saisies), le calcul
  s'arrête avant.
- **Délai d'inscription** = date d'enregistrement − date d'entrée. Son 95e centile (borné entre
  2 et 10 jours) fixe le nombre de derniers jours retirés de la série de modélisation : ces jours
  manquent d'enfants pas encore inscrits.

### 5.7 Indicateurs hospitaliers

Pour une période de J jours et un service de N lits :

| Indicateur | Formule | Lecture |
|---|---|---|
| Journées d'hospitalisation | JH = Σ_d P_d | nombre total de nuits passées à l'hôpital |
| Taux d'occupation moyen | TOM = JH / (N · J) × 100 | part des lits réellement occupés ; > 100 % = sureffectif |
| Présents moyens | L = JH / J | |
| Durée moyenne de séjour | DMS = Σ w · nuits / Σ w (séjours terminés dans la période) | les séjours en cours ne comptent pas |
| Rotation des lits | sorties / N | nombre de patients par lit sur la période |
| Intervalle de rotation | (N · J − JH) / sorties | jours moyens de lit vide entre deux patients ; négatif = sureffectif |
| Mortalité hospitalière | décès / sorties × 100 | |
| Jours en sureffectif | #{d : P_d > N} | |

Les sorties sont pondérées par leurs poids w (section 5.4) : sorties = Σ w, décès = Σ w·1(décès).
Ce sont les espérances des sommes ; la DMS est le rapport des deux.

**Fourchette du TOM** : TOM_bas ≤ TOM ≤ TOM_haut, mois par mois, puisque JH est croissant en chaque
date de sortie.

**Capacité variable** (lits ajoutés ou fermés) : N · J est remplacé par Σ_d N_d ; la rotation
utilise le nombre moyen de lits.

### 5.8 Loi de Little et Erlang B (garde-fous)

Code : `nera/garde_fous.py` et la section « Loi de Little et file d'attente » de l'outil.

**Loi de Little.** Dans tout système stable :

```
L = λ · W
```

L : présents moyens ; λ : admissions par jour ; W : durée moyenne de séjour en nuits. Elle ne
dépend d'aucune hypothèse sur la forme des arrivées ou des durées. Un écart de plus de 10 % entre
L mesuré et λW signale un problème de données (page manquante, dates fausses, sorties non
saisies) ou une période trop courte ou non stationnaire.

**Erlang B (file M/G/c/c, modèle à perte).** Arrivées de Poisson, durées quelconques, c lits,
pas de file d'attente. Probabilité qu'un enfant arrive alors que les c lits sont pleins :

```
B(c, a) = (a^c / c!) / Σ_{k=0..c} a^k / k!        a = λ · W = charge offerte en lits
```

Calcul stable par récurrence : B(0) = 1, puis B(k) = a·B(k−1) / (k + a·B(k−1)). On en déduit le
nombre de lits nécessaire pour une saturation inférieure à 5 % ou à 1 %.

| Charge a (exemple fictif) | B(10 lits) | B(20 lits) | Lits pour B ≤ 5 % | Lits pour B ≤ 1 % |
|---|---|---|---|---|
| 8 | 12 % | < 0,1 % | 12 | 15 |
| 12 | 30 % | 1 % | 17 | 20 |

On dimensionne un service sur ses pics, pas sur sa moyenne. Erlang B suppose qu'un patient refusé
est perdu ; dans un service qui ajoute des lits, la saturation observée peut dépasser B.

**Lien avec la perte quantile du SVR.** Sous-estimer un pic coûte plus que le surestimer. Si
c_p est le coût d'un lit manquant et c_s celui d'un lit vide, le quantile optimal à prévoir est

```
τ = c_p / (c_p + c_s)
```

τ = 0,8 revient à dire qu'une pénurie coûte 4 fois plus qu'un lit vide.

---

## 6. Mathématiques B : validation de l'occupation

Code : `outil-saisie/occupation-validation.js` (rubrique « Occupation » de l'outil). Quatre
méthodes indépendantes pour contrôler la reconstitution.

### 6.1 Bilan des flux et recalage sur des comptages réels

L'occupation est traitée comme un stock :

```
P_t = P_{t−1} + A_t − S_t
```

A_t : entrées du jour t ; S_t : sorties du jour t (une sortie calculée compte pour p le jour
e + n − 1 et pour 1 − p le jour e + n).

**Équivalence avec le recensement.** En déroulant la récurrence, P_t = P_0 + Σ_{u≤t} (A_u − S_u).
Chaque séjour ajoute +1 à son entrée et −1 à sa sortie : la somme cumulée compte les séjours
entrés et pas encore sortis, c'est-à-dire Σ 1(e ≤ t < S). L'écart entre les deux calculs doit
être 0 : ce contrôle vérifie le programme, pas le registre.

**Recalage.** Un comptage réel C_k fait le jour τ_k (cahier de garde, relève, comptage sur place)
est une donnée indépendante du registre. L'outil calcule :

- l'écart e_k = C_k − P_{τ_k} ;
- la série recalée P̃_t = P_t + e_k pour τ_k ≤ t < τ_{k+1} ;
- le biais ē = (1/K) Σ e_k et l'écart absolu moyen (1/K) Σ |e_k|.

**Test du signe.** Si le registre était juste, chaque écart serait positif ou négatif avec une
chance sur deux. La probabilité que K écarts soient tous du même signe vaut 2 · 0,5^K (bilatéral).
Exemple fictif : 8 écarts tous positifs, moyenne +3,25 : p = 0,008. Le registre sous-estime
l'occupation d'environ 3 enfants par nuit ; avec 8 présents moyens et 20 lits, le TOM passe de
40 % à 56 %. Avec moins de 5 comptages, aucune conclusion n'est possible (2 · 0,5⁵ = 0,06).

Précautions : un comptage fait le matin n'est pas un comptage de minuit (sorties du matin) ; il
ne doit compter ni les accompagnants ni les lits d'autres services.

### 6.2 Simulation de Monte-Carlo

On tire au hasard tout ce qui est incertain, N fois (100, 300 ou 1 000), et on refait le
recensement à chaque tirage r :

| Type de séjour | Traitement à chaque tirage |
|---|---|
| sortie écrite | fixe |
| sortie calculée | loi de Bernoulli : avec la probabilité p_M, S = e + n − 1, sinon S = e + n |
| durée inconnue | bootstrap : une durée tirée avec remise parmi les séjours connus de même prix (au moins 5), sinon de même issue, sinon de tout le service |
| encore hospitalisé | présent jusqu'à la fin de la période |

Pour chaque tirage : présents moyens L^(r), TOM^(r) = L^(r)/N, jours en sureffectif, maximum.

- **Intervalle de confiance à 95 % par percentiles** : [θ_(2,5 %) ; θ_(97,5 %)] des N valeurs.
- **Bande quotidienne** : 5e et 95e centiles de P_t^(r) pour chaque jour t.
- **P(au moins un jour > lits)** = part des tirages qui contiennent un sureffectif.

**Pourquoi l'intervalle est plus étroit que la fourchette basse / haute.** La fourchette met
toutes les lignes incertaines du même côté en même temps. La simulation tire chaque séjour
indépendamment : avec m séjours d'écart-type σ, la fourchette varie comme m·σ, l'écart-type de
la somme comme √m · σ. Exemple fictif : 200 séjours, σ = 2 nuits, 20 lits, 600 jours : écart-type
des JH ≈ 2 √200 ≈ 28 journées, soit ± 0,5 point de TOM à 95 %, contre ± 3,3 points pour la
fourchette.

**Précision de la simulation.** Une probabilité estimée sur N tirages a une erreur d'environ
√(p(1 − p)/N) : ± 2,9 points pour N = 300, ± 1,6 point pour N = 1 000. Le générateur pseudo-aléatoire
(mulberry32) a une graine fixe : le résultat est reproductible.

**Limite.** La simulation suppose que les durées manquantes ressemblent aux durées connues de la
même classe (hypothèse MAR, *missing at random*). Elle ne voit pas les enfants absents du
registre : seul le recalage sur des comptages réels (6.1) le peut.

### 6.3 Analyse de survie : Kaplan-Meier et log-rank

T = durée de séjour en nuits ; S(t) = P(T > t) est la part des enfants encore hospitalisés après
t nuits. Un enfant encore présent à la fin de la saisie est **censuré à droite** : on sait
seulement que T dépasse sa durée observée.

**Estimateur de Kaplan-Meier.** À chaque durée t_i où au moins une sortie a lieu, n_i est le
nombre d'enfants encore à risque juste avant t_i, d_i le nombre de sorties à t_i :

```
Ŝ(t) = Π_{t_i ≤ t} (1 − d_i / n_i)
```

Un censuré compte dans les n_i jusqu'à sa censure, puis disparaît sans créer de sortie. Un
censuré à la même durée qu'une sortie est encore à risque à cette durée.

Exemple fictif, 10 enfants de durées 1, 2, 2, 3, 3+, 4, 5, 5, 6+, 8 (+ = censuré) :

| t_i | n_i | d_i | Ŝ(t_i) |
|---|---|---|---|
| 1 | 10 | 1 | 0,90 |
| 2 | 9 | 2 | 0,70 |
| 3 | 7 | 1 | 0,60 |
| 4 | 5 | 1 | 0,48 |
| 5 | 4 | 2 | 0,24 |
| 8 | 1 | 1 | 0 |

Médiane = première durée où Ŝ ≤ 0,5, soit 4 nuits. En jetant les censurés, on trouverait 3,5 nuits :
biais vers le bas. Quartiles : Q1 = première durée où Ŝ ≤ 0,75, Q3 = première durée où Ŝ ≤ 0,25.

**Variance de Greenwood et intervalle à 95 %.**

```
Var[Ŝ(t)] ≈ Ŝ(t)² · Σ_{t_i ≤ t} d_i / (n_i (n_i − d_i))        IC = Ŝ ± 1,96 √Var
```

Exemple fictif à t = 2 : Σ = 1/90 + 2/63 = 0,0429 ; écart-type 0,70 · √0,0429 = 0,145 ;
IC [0,42 ; 0,98].

**Durée moyenne restreinte à 30 nuits** : ∫_0^30 Ŝ(t) dt = E[min(T, 30)], calculable même si la
courbe ne descend pas à 0. Lien avec la loi de Little : E[T] = ∫_0^∞ S(t) dt, donc Kaplan-Meier
donne un W qui tient compte des censures.

**Test du log-rank (forme de Peto).** À chaque durée t de sortie, le groupe g recevrait, sans
différence entre groupes, une part des d_t sorties proportionnelle à son effectif à risque :
E_{g,t} = d_t · n_{g,t} / n_t. Avec O_g = Σ_t d_{g,t} et E_g = Σ_t E_{g,t} :

```
χ² = Σ_g (O_g − E_g)² / E_g        k − 1 degrés de liberté
```

Cette forme est un peu prudente (elle rejette un peu moins souvent que la forme à variance
complète). Hypothèses : censure non informative ; les enfants partis sans date ni durée ne sont
pas des censurés (durée inconnue) et sont exclus de Kaplan-Meier.

### 6.4 Modèle de file M/G/∞

Hypothèses : arrivées de Poisson de taux λ, durées indépendantes de loi quelconque G de moyenne
W, nombre de lits illimité (en pédiatrie, un enfant en surplus est couché quand même).

**Théorème.** En régime stable, le nombre de présents suit une loi de Poisson de moyenne λW,
quelle que soit la loi des durées :

```
P(N = k) = e^{−λW} (λW)^k / k!        E[N] = Var[N] = λW
```

Idée de la preuve : un enfant arrivé il y a u jours est encore là avec la probabilité S(u) ; un
processus de Poisson dont on garde chaque point avec la probabilité S(u) reste de Poisson, de
moyenne λ ∫ S(u) du = λW. Version non stationnaire : N_t suit une loi de Poisson de moyenne
Σ_k λ_{t−k} S(k).

**Indice de dispersion** D = variance / moyenne des présents observés : D ≈ 1 conforme au hasard,
D > 1 surdispersion (arrivées par vagues), D < 1 régularité. Le test (n − 1)·D ~ χ²(n − 1)
n'est pas valide ici, les présents d'un jour à l'autre étant fortement corrélés : D se lit comme
un indicateur.

**Mélange de Poisson par mois** : P(N = k) = Σ_m w_m · Poisson(k ; μ_m), w_m = part des jours du
mois m, μ_m = moyenne du mois. Par la loi de la variance totale, Var(N) = E[μ] + Var(μ) : la
saison crée à elle seule de la surdispersion. Exemple fictif : μ = 6 et μ = 10 à parts égales
donnent une moyenne 8, une variance 12, D = 1,5.

**Binomiale négative** (mélange Poisson-gamma), ajustée par les moments (si v > m) :

```
r = m² / (v − m)    q = m / v    P(N = k) = Γ(k + r) / (Γ(r) k!) · q^r (1 − q)^k
```

**Queues de distribution** (exemple fictif, 20 lits, 8 présents en moyenne) :

| Loi | Variance | P(N ≥ 17) | P(N ≥ 21) |
|---|---|---|---|
| Poisson(8) | 8 | 0,37 % | 0,009 % |
| mélange μ = 6 / 10 | 12 | 1,4 % | 0,08 % |
| binomiale négative | 16 | 3,2 % | 0,6 % |

À même moyenne, ignorer la surdispersion fait sous-estimer les pics. C'est l'argument de la perte
quantile τ = 0,8 pour le SVR.

### 6.5 Quelle méthode répond à quelle question

| Question | Méthode | Ce qu'elle ne voit pas |
|---|---|---|
| Le calcul est-il juste ? | bilan des flux (écart nul) | les erreurs du registre |
| Le registre est-il complet ? | recalage sur comptages réels | rien, si les comptages sont fiables |
| Les données manquantes changent-elles le résultat ? | Monte-Carlo | les enfants absents du registre |
| Combien de temps reste un enfant, selon le groupe ? | Kaplan-Meier, log-rank | les durées des enfants partis sans date |
| Le service est-il souvent plein ? | M/G/∞ | le plafond physique des lits |
| Combien de lits faudrait-il ? | Erlang B | le surnombre (il suppose le refus) |

---

## 7. Mathématiques C : statistiques descriptives et tests

Code : `outil-saisie/statistiques.js` et `outil-saisie/indicateurs.js` (rubriques de l'outil),
`svr/analyse.py` (figures Python).

### 7.1 Règles de lecture communes

- **p-valeur** : probabilité d'observer un écart au moins aussi grand si l'hypothèse nulle (aucun
  lien, aucune différence) était vraie. On rejette l'hypothèse nulle si p < 0,05. Une p-valeur ne
  mesure pas l'importance d'un effet : il faut toujours lire la **taille d'effet** à côté.
- **Comparaisons multiples** : sur 100 tests à 5 %, environ 5 sortent significatifs par hasard.
  Correction de Bonferroni : seuil = 0,05 / nombre de tests.
- **Paramétrique ou non** : si une variable n'est pas normale (Jarque-Bera), préférer les tests
  sur les rangs (Spearman, Kendall, Mann-Whitney, Kruskal-Wallis).

### 7.2 Une variable numérique

| Indicateur | Formule |
|---|---|
| Moyenne | x̄ = Σx / n |
| Médiane, quantiles | quantile de type 7 : position h = (n − 1)q, interpolation linéaire entre x_(⌊h⌋) et x_(⌊h⌋+1) |
| Variance | s² = Σ(x − x̄)² / (n − 1) |
| Erreur-type | s / √n |
| IC 95 % de la moyenne | x̄ ± t_{0,975}(n − 1) · s / √n |
| Coefficient de variation | CV = 100 · s / x̄ |
| Écart interquartile | IQR = Q3 − Q1 |
| Écart absolu médian | MAD = médiane(|x − médiane|) |
| Asymétrie | G1 = √(n(n − 1)) / (n − 2) · m₃ / m₂^{3/2}, m_k = (1/n) Σ(x − x̄)^k |
| Aplatissement (excès) | G2, nul pour une loi normale |
| Jarque-Bera | JB = n/6 · (g1² + g2²/4) ~ χ²(2) |
| Valeurs atypiques (Tukey) | x < Q1 − 1,5 IQR ou x > Q3 + 1,5 IQR |
| Largeur des classes (Freedman-Diaconis) | h = 2 · IQR · n^{−1/3} |
| Droite de Henry | abscisse Φ⁻¹((i − ½)/n), ordonnée valeur centrée réduite |

### 7.3 Variables qualitatives

- **Intervalle de Wilson** d'une proportion, z = 1,96 :
  (p̂ + z²/2n ± z √(p̂(1 − p̂)/n + z²/4n²)) / (1 + z²/n). Il reste dans [0 ; 1] et fiable pour les
  petits effectifs.
- **Entropie normalisée** : H = −Σ p_i ln p_i / ln k, entre 0 (une seule modalité) et 1
  (modalités également fréquentes).

### 7.4 Corrélations

| Coefficient | Formule | Mesure |
|---|---|---|
| Pearson | r = Σ(x − x̄)(y − ȳ) / √(Σ(x − x̄)² Σ(y − ȳ)²) ; test t = r √(n − 2) / √(1 − r²) ~ Student(n − 2) | lien linéaire |
| Spearman | Pearson sur les rangs (ex æquo au rang moyen) | lien monotone |
| Kendall τ-b | (C − D) / √((n₀ − n₁)(n₀ − n₂)), C et D paires concordantes et discordantes | lien monotone, gère les ex æquo |
| Point-bisériale | Pearson avec une variable 0/1 | différence de moyennes |

Force de |r| : < 0,1 négligeable, < 0,3 faible, < 0,5 modéré, < 0,7 fort, au-delà très fort.
r² = part de variance commune. En Python, la matrice de Pearson se calcule R = ZᵀZ / n sur les
variables centrées réduites.

### 7.5 Tableaux croisés : χ² et V de Cramér

```
χ² = Σ (O − E)² / E      E = total ligne × total colonne / n      ddl = (l − 1)(c − 1)
V = √(χ² / (n (min(l, c) − 1)))
```

Résidus standardisés (O − E)/√E : > 2 case sur-représentée, < −2 sous-représentée. Si plus de 20 %
des cases ont E < 5, regrouper des modalités avant de citer le test.

### 7.6 Comparer des groupes

| Test | Formule | Taille d'effet |
|---|---|---|
| Mann-Whitney | U = R₁ − n₁(n₁ + 1)/2 ; z = (U − n₁n₂/2) / √(n₁n₂(n₁ + n₂ + 1)/12) | r = |z| / √n |
| t de Welch | t = (x̄₁ − x̄₂) / √(s₁²/n₁ + s₂²/n₂), ddl de Welch-Satterthwaite | d de Cohen |
| Kruskal-Wallis | H = 12 / (n(n + 1)) Σ R_j²/n_j − 3(n + 1) ~ χ²(k − 1) | ε² = H / (n − 1) |
| ANOVA | F = (SCE_inter/(k − 1)) / (SCE_intra/(n − k)) | η² = SCE_inter / SCE_totale |

Repères : r ≈ 0,1 / 0,3 / 0,5 ; ε² ou η² ≈ 0,01 / 0,06 / 0,14 ; d ≈ 0,2 / 0,5 / 0,8 (petit /
moyen / grand).

### 7.7 Régression linéaire multiple (moindres carrés)

```
y = β₀ + β₁x₁ + … + β_k x_k + ε        β̂ = (XᵀX)⁻¹ Xᵀ y
σ̂² = SCE / (n − k − 1)                 se(β̂_j) = √(σ̂² [(XᵀX)⁻¹]_jj)
t_j = β̂_j / se ~ Student(n − k − 1)    IC 95 % = β̂_j ± t_{0,975} · se
R² = 1 − SCE/SCT                       R²_ajusté = 1 − (1 − R²)(n − 1)/(n − k − 1)
F = ((SCT − SCE)/k) / σ̂²               RMSE = √(SCE / n)
β standardisé = β · s_x / s_y          VIF_j = 1 / (1 − R_j²)
```

VIF > 5 : colinéarité, coefficient instable. Résidus en entonnoir : hétéroscédasticité ; résidus
en courbe : lien non linéaire (argument pour un noyau RBF).

### 7.8 Analyse en composantes principales (ACP normée)

1. Variables positives très asymétriques (|G1| > 1) transformées en log(1 + x).
2. Centrage-réduction z_ij = (x_ij − x̄_j)/s_j, matrice des corrélations R = ZᵀZ / (n − 1).
3. Diagonalisation R = U Λ Uᵀ par la **méthode de Jacobi** (rotations qui annulent le plus grand
   terme hors diagonale, jusqu'à 10⁻¹²). λ_k = variance de l'axe k, Σλ = p, inertie = λ_k / p.
4. Coordonnées F_ik = Σ_j z_ij u_jk ; corrélation variable-axe r_jk = u_jk √λ_k ; cos² = r_jk² ;
   contribution = u_jk² × 100 % (une variable « fait » l'axe au-delà de 100/p %).
5. **Test de Bartlett** : χ² = −(n − 1 − (2p + 5)/6) · ln|R|, ddl p(p − 1)/2 ; p < 0,05 nécessaire.
6. **KMO** = Σr² / (Σr² + Σa²), a_ij = −R⁻¹_ij / √(R⁻¹_ii R⁻¹_jj) (corrélations partielles) ; échelle
   de Kaiser de 0,5 (médiocre) à 0,9 (excellent) ; MSA = même indice par variable.
7. **Nombre d'axes** : analyse parallèle de Horn (100 permutations indépendantes des colonnes,
   95e centile des valeurs propres, graine fixe) ; bâton brisé b_k = (1/p) Σ_{i=k..p} 1/i ;
   critère de Kaiser λ > 1 (affiché pour mémoire).
8. **Valeur-test** d'un groupe de n_g individus de barycentre ḡ_k sur l'axe k :
   v = ḡ_k / √(λ_k / n_g · (n − n_g)/(n − 1)) ; |v| > 1,96 : groupe significativement d'un côté.
9. **Ellipses** : en 2D, ellipse de confiance à 95 % du barycentre (covariance / n_g, rayon
   √5,991) ; en 3D, ellipse à 1,5 écart-type des points projetés.

### 7.9 Calendrier camerounais

- **Pâques** (algorithme de Meeus/Jones/Butcher, divisions entières) : a = Y mod 19 ; b = Y div 100,
  c = Y mod 100 ; d = b div 4, e = b mod 4 ; f = (b + 8) div 25 ; g = (b − f + 1) div 3 ;
  h = (19a + b − d − g + 15) mod 30 ; i = c div 4, k = c mod 4 ; l = (32 + 2e + 2i − h − k) mod 7 ;
  m = (a + 11h + 22l) div 451 ; mois = (h + l − 7m + 114) div 31 ; jour = ((h + l − 7m + 114) mod 31) + 1.
- Vendredi saint = Pâques − 2 jours ; Ascension = Pâques + 39 jours.
- Fêtes fixes : 1er janvier, 11 février, 1er mai, 20 mai, 15 août, 25 décembre. Fêtes musulmanes
  (Aïd el-Fitr, Tabaski) lues dans `donnees/feries_supplementaires.csv` d'après les annonces
  officielles ; vacances scolaires dans `donnees/vacances_scolaires.csv`.
- **Observé / attendu d'un férié** = admissions des fériés / Σ (moyenne des jours ordinaires du
  même jour de la semaine) : neutralise l'effet du jour de la semaine.
- **Écart vacances − classe à mois égal** = Σ_m n_vac,m (ȳ_vac,m − ȳ_classe,m) / Σ_m n_vac,m :
  neutralise la saison.

### 7.10 Contrôle qualité de la saisie

- Numéro d'ordre daté hors de ses voisins (n − 3 à n + 3) : plus tôt ou plus tard que la médiane
  des précédents et que celle des suivants, d'au moins 4 jours.
- Enregistré avant l'entrée, ou plus de 10 jours après ; date illisible.
- Doublons probables : même date d'entrée, même sexe, même âge, même quartier.
- Numéros d'ordre manquants entre deux numéros d'un même mois.
- **Double saisie** (`qualite_saisie.py`) : accord par colonne, kappa de Cohen
  κ = (p_o − p_e) / (1 − p_e), p_o accord observé, p_e accord attendu par hasard.

---

## 8. Mathématiques D : séries temporelles

### 8.1 Lissages descriptifs et décomposition

- Moyenne mobile m_t = (1/k) Σ_{i=0..k−1} y_{t−i} ; médiane, écart-type et CV mobiles ; bande ± 2σ
  sur 30 jours ; tendance linéaire y_t = a + b t (moindres carrés).
- **Décomposition additive** y_t = T_t + S_t + R_t : T = moyenne mobile centrée sur 7 jours,
  S = moyenne de y − T par jour de la semaine recentrée à somme nulle, R = y − T − S.
- **Forces** (Wang, Smith et Hyndman) : F = max(0, 1 − Var(R) / Var(composante + R)).

### 8.2 Autocorrélations

- **ACF** : ρ̂(k) = Σ_t (y_t − ȳ)(y_{t+k} − ȳ) / Σ_t (y_t − ȳ)² ; bande ± 1,96/√n.
- **PACF** par la récursion de Durbin-Levinson :
  φ_kk = (ρ(k) − Σ_{j<k} φ_{k−1,j} ρ(k − j)) / (1 − Σ_{j<k} φ_{k−1,j} ρ(j)),
  φ_kj = φ_{k−1,j} − φ_kk φ_{k−1,k−j}.
- **Corrélation croisée** admissions → présents : ρ_xy(k) = corr(A_{t−k}, P_t).

| ACF | PACF | Processus |
|---|---|---|
| décroît lentement | un pic à 1 | AR(1) |
| décroît lentement | pics à 1 et 2 | AR(2) |
| coupe net après k | décroît | MA(k) |
| pics à 7, 14, 21 | pic à 7 | saisonnalité hebdomadaire |

### 8.3 Tests sur la série

- **Ljung-Box** : Q = n(n + 2) Σ_{k=1..m} ρ̂_k² / (n − k) ~ χ²(m − paramètres). Sur la série brute,
  p < 0,05 signifie qu'elle a de la mémoire ; sur les résidus d'un modèle, on veut p ≥ 0,05.
- **ADF** : Δy_t = α + γ y_{t−1} + Σ δ_i Δy_{t−i} + ε ; statistique t de γ comparée aux valeurs de
  MacKinnon (−3,43 / −2,86 / −2,57) ; inférieure à −2,86 : on rejette la racine unitaire.
- **KPSS** : η = Σ S_t² / (n² σ̂²_lr), S_t somme cumulée des écarts, σ̂²_lr variance de long terme de
  Newey-West ; valeurs critiques 0,347 / 0,463 / 0,739 ; au-delà de 0,463 on rejette la
  stationnarité. ADF et KPSS se lisent ensemble :

| ADF | KPSS | Conclusion |
|---|---|---|
| rejette | ne rejette pas | stationnaire |
| ne rejette pas | rejette | racine unitaire : différencier |
| rejette | rejette | niveau qui varie lentement : modéliser la saison |
| ne rejette pas | ne rejette pas | pas assez de données |

- **Mann-Kendall** : τ de Kendall entre le temps et la série (tendance monotone).
- **Indice de dispersion des admissions** I = variance / moyenne ; (n − 1) I ~ χ²(n − 1) sous
  l'hypothèse de Poisson (les admissions d'un jour à l'autre sont peu corrélées, contrairement
  aux présents).
- **Périodogramme** : I(f) = |Σ_t (y_t − ȳ) e^{−2iπft}|² / n, période 1/f ; seuil du hasard à 95 %
  = σ² ln(K / 0,05) pour K fréquences (I(f)/σ² suit une loi exponentielle de moyenne 1 pour un
  bruit blanc).

---

## 9. Mathématiques E : modèles de prévision de référence

Code : `svr/references.py`, `svr/classiques.py` (Python) et `outil-saisie/statistiques.js`
(rubrique « Modèles de prévision » de l'outil).

### 9.1 Modèles

| Modèle | Équations |
|---|---|
| Persistance (naïf) | ŷ_{t+h} = y_t |
| Saisonnier naïf | ŷ_{t+h} = moyenne des derniers jours connus de même jour de la semaine que t + h |
| Moyenne mobile | ŷ_{t+h} = (1/k) Σ_{j=0..k−1} y_{t−j} |
| Lissage exponentiel simple | l_t = α y_t + (1 − α) l_{t−1} ; ŷ_{t+h} = l_t |
| Thêta | lissage simple + ½ b̂ (h − 1 + 1/α), b̂ pente des moindres carrés |
| Holt linéaire | l_t = α y_t + (1 − α)(l_{t−1} + b_{t−1}) ; b_t = β(l_t − l_{t−1}) + (1 − β) b_{t−1} ; ŷ_{t+h} = l_t + h b_t |
| Holt amorti | ŷ_{t+h} = l_t + (φ + φ² + … + φ^h) b_t |
| Saisonnier sans tendance | l_t = α(y_t − s_{t−7}) + (1 − α) l_{t−1} ; s_t = γ(y_t − l_t) + (1 − γ) s_{t−7} |
| Holt-Winters additif, tendance amortie (m = 7) | l_t = α(y_t − s_{t−m}) + (1 − α)(l_{t−1} + φ b_{t−1}) ; b_t = β(l_t − l_{t−1}) + (1 − β) φ b_{t−1} ; s_t = γ(y_t − l_t) + (1 − γ) s_{t−m} ; ŷ_{t+h} = l_t + Σ_{j=1..h} φ^j b_t + s_{t+h−m(k+1)}, k = ⌊(h − 1)/m⌋ |
| Holt-Winters multiplicatif | ŷ = (l + Σ φ^j b) × s |
| AR(p) | y_t = c + Σ_{i=1..p} a_i y_{t−i} + ε, moindres carrés, p choisi par AIC = n ln(SCE/n) + 2(p + 1) |
| SARIMA(p,d,q)(P,D,Q)₇ | (1 − φ(B))(1 − Φ(B⁷))(1 − B)^d (1 − B⁷)^D y_t = c + (1 + θ(B))(1 + Θ(B⁷)) ε_t |
| Régression ridge | min Σ (y_i − w·x_i − b)² + λ‖w‖² ; solution exacte (X̃ᵀX̃ + λI) w = X̃ᵀỹ, b = ȳ − x̄·w |

### 9.2 Estimation

- Lissages (outil) : minimisation de la somme des carrés des erreurs à un pas,
  SSE = Σ (y_t − ŷ_{t|t−1})², par le simplexe de **Nelder-Mead** (réflexion 1, expansion 2,
  contraction ½, réduction ½). Les paramètres α, β, γ ∈ ]0 ; 1[ sont écrits σ(u) = 1/(1 + e^{−u})
  pour optimiser sans contrainte ; φ ∈ [0,8 ; 0,98].
- Holt-Winters (Python) : initialisation sur deux semaines (l = moyenne de la 1re semaine,
  b = (moyenne 2e − moyenne 1re)/m, s_i = y_i − l), paramètres choisis par grille en minimisant
  la MAE à h jours sur l'entraînement seul.
- SARIMA : somme conditionnelle des carrés des innovations (CSS) ; paramètres passés par tanh
  (stationnarité et inversibilité approchées). Intervalle : écriture MA(∞) y = Σ ψ_j ε_{t−j},
  Var(e_h) = σ² Σ_{j<h} ψ_j², bornes ± 1,96 √Var. Recherche automatique sur 60 modèles par
  BIC = n ln σ² + k ln n à d et D égaux, puis erreur de validation.
- Intervalle naïf : y_t + quantiles des erreurs passées de la persistance e_s = y_{s+h} − y_s
  (180 derniers jours).

Si l'estimation trouve β = 0, Holt linéaire, Holt amorti et Thêta se réduisent au lissage simple :
ce n'est pas une erreur, c'est l'absence de tendance exploitable.

---

## 10. Mathématiques F : le SVR

Code : `svr/pertes.py`, `svr/noyaux.py`, `svr/optimiseurs.py`, `svr/modeles.py`,
`svr/empilement.py`, `svr/caracteristiques.py`, `svr/validation.py`, `svr/recherche.py`,
`svr/niveaux.py`.

### 10.1 Les niveaux du modèle (ablation)

Chaque niveau ajoute une brique et doit prouver qu'elle améliore le précédent.

| Niveau | Modèle | Ce qu'il ajoute |
|---|---|---|
| 0 | persistance, saisonnier, moyenne mobile | la barre à battre, sans apprentissage |
| 1 | SVR linéaire, perte ε-insensible | un hyperplan f(x) = w·x + b et son tube ± ε |
| 2 | SVR à noyau RBF | des relations non linéaires |
| 3 | SVR quantile (perte pinball) | les coûts asymétriques (τ = 0,8) et l'intervalle à 90 % |
| 4 | SVR quantile à noyau composite | deux blocs de variables mélangés par un poids β appris |
| 5 | empilement | combinaison apprise des niveaux 3, 4 et de la persistance |

### 10.2 Objectif minimisé (forme primale)

```
J(w, b) = ½ ‖w‖² + C Σ_i L(y_i − f(x_i))          f(x) = w·x + b             (linéaire)
J(α, b) = ½ αᵀKα + C Σ_i L(y_i − f(x_i))          f = Kα + b                 (noyau)
```

Le premier terme garde le modèle simple (grande marge), le second fait payer les erreurs ; C règle
l'équilibre. On note r_i = y_i − f_i le résidu (r > 0 : sous-estimation, risque de manquer de
lits) et g_i = ∂L/∂f_i la dérivée de la perte par rapport à la prévision (∂L/∂f = −L'(r)).

### 10.3 Fonctions de perte

| Perte | Formule | Dérivée ∂L/∂f |
|---|---|---|
| ε-insensible | L_ε(r) = max(0, |r| − ε) | −signe(r) · 1(|r| > ε) |
| pinball (quantile τ) | ρ_τ(r) = max(τ r, (τ − 1) r) | −τ si r > 0 ; 1 − τ si r < 0 |
| pinball ε-insensible | τ max(0, r − ε) + (1 − τ) max(0, −r − ε) | −τ si r > ε ; 1 − τ si r < −ε ; 0 sinon |
| hinge (classification) | max(0, 1 − y f) | −y · 1(y f < 1) |

Aux points anguleux, on prend le sous-gradient 0.

**Pourquoi la pinball donne le quantile.** En minimisant E[ρ_τ(Y − q)] en q :
dE/dq = −τ P(Y > q) + (1 − τ) P(Y < q) = 0, soit P(Y < q) = τ. La prévision optimale est le
quantile τ de l'occupation.

**Le tube déforme le quantile.** Avec la pinball ε-insensible, la condition devient
τ P(Y > q + ε) = (1 − τ) P(Y < q − ε) : les jours à moins de ε de q ne comptent plus. Pour un
intervalle calibré, les niveaux quantiles utilisent ε = 0 (paramètre `epsilon_quantile`).

### 10.4 Noyaux

```
linéaire :   K(x, z) = x · z
RBF :        K(x, z) = exp(−γ ‖x − z‖²)        ‖x − z‖² = ‖x‖² + ‖z‖² − 2 x·z (valeurs < 0 ramenées à 0)
composite :  K(x, z) = β K₁(x⁽¹⁾, z⁽¹⁾) + (1 − β) K₂(x⁽²⁾, z⁽²⁾),    β = σ(θ) = 1 / (1 + e^{−θ})
             ∂K/∂θ = β (1 − β) (K₁ − K₂)
```

Par le théorème du représentant, f(x) = Σ_j α_j K(x_j, x) + b : chaque jour d'entraînement vote
pour la prévision, d'autant plus fort que la situation lui ressemble ; les jours avec α_j ≠ 0 sont
les vecteurs de support. γ règle la portée du noyau RBF. Une somme pondérée positive de noyaux
valides est un noyau valide (matrice semi-définie positive). Les deux blocs du noyau composite
sont : (1) l'occupation des 7 derniers jours ; (2) les flux récents et la saison.

### 10.5 Gradients (dérivés à la main, vérifiés par différences finies)

```
Niveau 1 :  ∂J/∂w = w + C Xᵀ g                 ∂J/∂b = C Σ_i g_i
Niveaux 2-3 : ∂J/∂α = Kα + C K g = K(α + C g)   ∂J/∂b = C Σ_i g_i
Niveau 4 :  avec D = K₁ − K₂,
            ∂J/∂θ = β(1 − β) · [ ½ αᵀ D α + C gᵀ D α ]
```

**Direction préconditionnée** (modèles à noyau) : on descend selon α + C g au lieu de K(α + C g).
La matrice K, souvent presque singulière, ralentit la descente dans certaines directions ; la
direction α + C g est le gradient dans l'espace des fonctions. Elle s'annule au même point : même
solution, atteinte plus vite.

### 10.6 Optimiseurs

```
Descente de gradient :  θ ← θ − η g
Momentum :              v ← μ v + g ;  θ ← θ − η v                         (μ ≈ 0,9)
Adam :                  m ← β₁ m + (1 − β₁) g ;  v ← β₂ v + (1 − β₂) g²    (β₁ = 0,9, β₂ = 0,999)
                        m̂ = m / (1 − β₁^t) ;  v̂ = v / (1 − β₂^t)
                        θ ← θ − η m̂ / (√v̂ + ε)                              (ε = 10⁻⁸)
Décroissance du pas :   η_t = η₀ / √(1 + t/T)                               (η₀ = 0,05, T = 500)
```

La correction de biais compense le démarrage de m et v à 0 (E[m_t] ≈ (1 − β₁^t) E[g]). Avec une
perte linéaire par morceaux, le gradient ne s'annule pas près du minimum : la décroissance du pas
garantit la convergence.

**Moyenne de Polyak.** Les itérés oscillent autour du minimum ; on calcule leur moyenne sur la fin
de l'entraînement (à partir de la moitié des pas) :

```
θ̄ = (1/K) Σ_{t=T₀}^{T₀+K−1} θ_t        mise à jour : θ̄ ← θ̄ + (θ_t − θ̄)/k
```

J étant convexe, J(θ̄) ≤ (1/K) Σ J(θ_t) (inégalité de Jensen). On garde, entre la moyenne et le
meilleur point rencontré, celui dont J est le plus petit. Arrêt anticipé si J ne baisse plus
(relativement, tolérance 10⁻⁷) sur 100 pas ; dans ce cas, la moyenne porte sur les 100 derniers
points visités. Réglages par défaut : Adam, 3 000 pas au plus.

### 10.7 Intervalle de prévision

Un modèle quantile par niveau τ ∈ {0,05 ; 0,5 ; 0,95}, entraînés séparément ; les prévisions sont
triées jour par jour pour que les quantiles ne se croisent jamais. Intervalle à 90 % = [q̂_0,05 ;
q̂_0,95], prévision centrale = q̂_0,5, prévision décisionnelle = q̂_τ (τ = 0,8).

### 10.8 Empilement (niveau 5)

```
f = Σ_k w_k p_k + b         w_k = softplus(u_k) = ln(1 + e^{u_k}) > 0
J(u, b) = ½ λ Σ_k w_k² + C Σ_i L(y_i − f_i)
∂J/∂u_k = σ(u_k) · [ λ w_k + C Σ_i g_i p_ik ]         ∂J/∂b = C Σ_i g_i
```

p_k sont des prévisions **hors échantillon** (obtenues en validation glissante), sinon le
méta-modèle ferait confiance au modèle qui a appris l'entraînement par cœur. Les poids positifs
interdisent de « parier contre » un modèle.

### 10.9 Tableau d'apprentissage

Le soir du jour t (l'origine), on prévoit l'occupation du jour t + h. Chaque ligne n'utilise que
ce qui est connu au jour t.

| Bloc | Variables |
|---|---|
| occupation | y_t, y_{t−1}, …, y_{t−6} |
| flux et saison | admissions des 3 et des 7 derniers jours ; sorties des 7 derniers jours ; jour de la semaine du jour cible (7 indicatrices) ; mois du jour cible sin(2π(m − 1)/12), cos(2π(m − 1)/12) ; en option : jour cible férié, veille de férié, vacances scolaires |

Codage circulaire du mois : décembre et janvier sont voisins sur le cercle.

**Standardisation** z = (x − μ)/σ des variables continues, avec μ et σ calculés sur les **seules
lignes d'entraînement** de chaque découpage (sinon le test voit le futur). Le noyau RBF dépend des
distances : sans standardisation, une variable en dizaines écraserait une variable entre −1 et 1.
Les indicatrices 0/1 ne sont pas standardisées.

### 10.10 Validation glissante

Une ligne (origine t, cible t + h) n'est utilisable pour entraîner un modèle à l'origine O que si
t + h ≤ O.

- **Validation glissante** : l'origine O avance par pas de 14 jours (au moins 60 jours
  d'entraînement) ; à chaque O, entraînement sur toutes les lignes de cible ≤ O, validation sur
  les lignes d'origine dans [O, O + pas[. Le modèle et la standardisation sont réappris à chaque
  origine.
- **Test final** : entraînement sur les lignes dont la cible précède la période verrouillée, test
  sur les lignes dont l'origine est dans la période verrouillée ; les lignes à cheval sont écartées.

### 10.11 Recherche des hyperparamètres

- **Grille** sur toutes les combinaisons de valeurs.
- **Essaim particulaire (PSO)** :

```
v_i ← ω v_i + c₁ r₁ (p_i − x_i) + c₂ r₂ (g − x_i)        x_i ← x_i + v_i (ramené dans les bornes)
```

p_i meilleure position de la particule, g meilleure de l'essaim, r₁ et r₂ uniformes sur [0, 1].
C et γ sont explorés en log₁₀. Graine fixe : la recherche est reproductible.

Valeurs de départ (`svr/niveaux.py`) : C = 1 ; ε = 1 lit (niveaux 1 et 2) ; ε = 0 (niveaux
quantiles) ; γ = 0,05 ; γ₁ = 0,05 et γ₂ = 0,1 (noyau composite) ; τ = 0,8.

---

## 11. Mathématiques G : évaluation et comparaison des modèles

Code : `svr/metriques.py`, `svr/analyse.py`, `sensibilite.py`, `benchmark_choix.py`.

### 11.1 Métriques

| Mesure | Formule |
|---|---|
| MAE | (1/n) Σ |y − ŷ| |
| RMSE | √((1/n) Σ (y − ŷ)²) |
| MAPE | (100/n) Σ |y − ŷ| / y (jours y > 0) |
| sMAPE | (100/n) Σ 2|y − ŷ| / (|y| + |ŷ|) |
| MASE | MAE / MAE du saisonnier naïf sur l'entraînement (< 1 : meilleur que la référence) |
| Biais | (1/n) Σ (ŷ − y) en Python (> 0 : surestimation) ; l'outil affiche (1/n) Σ (y − ŷ) |
| Sous-estimations | part des jours où ŷ < y |
| Pinball moyenne | (1/n) Σ ρ_τ(y − q̂_τ) |
| Couverture | part des jours où bas ≤ y ≤ haut (cible 90 % pour un intervalle à 90 %) |
| Largeur moyenne | (1/n) Σ (haut − bas) |
| Gain sur la persistance | 1 − perte(modèle) / perte(persistance) |
| Coût des décisions | c_p · lits manquants + c_s · lits vides |

Un modèle quantile à τ = 0,8 doit surestimer volontairement : il se juge sur la pinball et sur la
part de jours au-dessus de la prévision (cible ≈ 20 %), pas sur la MAE seule.

**Calibration des quantiles** : pour chaque niveau demandé τ, part observée des jours sous q̂_τ ; un
modèle bien calibré est sur la diagonale. **Importance par permutation** : hausse de l'erreur
quand on mélange un groupe de variables. **Courbe d'apprentissage** : erreur d'entraînement et de
validation selon la taille de l'historique.

### 11.2 Test de Diebold-Mariano

Deux modèles A et B sur les mêmes jours, d_t = L(e_t^A) − L(e_t^B) (valeur absolue ou carré).
Hypothèse nulle : E[d_t] = 0.

```
DM = d̄ / √(V̂ / n)        V̂ = γ̂₀ + 2 Σ_{k=1}^{h−1} γ̂_k        (autocovariances de d)
DM* = DM · √[(n + 1 − 2h + h(h − 1)/n) / n]                    (Harvey, Leybourne et Newbold)
p = 2 (1 − Φ(|DM*|))
```

Les autocovariances jusqu'au décalage h − 1 tiennent compte du fait que des prévisions à h jours
faites des jours voisins partagent des jours futurs. DM* < 0 et p < 0,05 : A est
significativement plus précis que B. Sans p < 0,05, on écrit « meilleur en moyenne, mais pas
significativement ».

### 11.3 Analyse de sensibilité à la convention des jours

Mêmes origines et mêmes hyperparamètres sur les trois séries (basse, attendue, haute). Chaque
niveau est noté en MAE (prévision centrale) et en pinball au τ décisionnel. La conclusion est
**robuste** si le meilleur niveau est le même dans les trois scénarios et si aucun gain ne change
de signe en dépassant 3 points en valeur absolue.

### 11.4 Banc de comparaison des choix (D1 à D10)

Chaque dimension change une seule chose ; chaque variante est comparée au choix retenu par
Diebold-Mariano (meilleure, équivalente ou moins bonne).

| Dimension | Question | Variantes |
|---|---|---|
| D1 | Le SVR bat-il les méthodes classiques ? | persistance, saisonnier, moyenne mobile, Holt-Winters, ridge, SVR niveaux 1 à 4 |
| D2 | Quel noyau ? | linéaire, RBF, composite |
| D3 | Quelle perte ? | carrée (ridge), ε-insensible avec ε = 0 / 0,5 / 1 / 2 |
| D4 | Quel τ selon le coût d'une pénurie ? | τ de 0,5 à 0,9 ; coût moyen pour des rapports pénurie / lit vide de 1, 2, 4, 9 |
| D5 | Quelles variables ? | retards seuls, + flux, + calendrier, complet, + fériés, + vacances, + fériés et vacances, 3 / 7 / 14 retards |
| D6 | Faut-il standardiser ? | avec, sans |
| D7 | Tout le passé ou une fenêtre ? | croissante ; 365, 180, 90 derniers jours |
| D8 | Comment optimiser ? | Adam complet, sans Polyak, sans préconditionnement, sans décroissance, momentum, descente simple |
| D9 | Combiner apporte-t-il ? | meilleur modèle seul, moyenne simple, empilement |
| D10 | La recherche d'hyperparamètres paie-t-elle ? | défaut, grille, essaim particulaire |

### 11.5 Ce que les analyses apportent aux choix du SVR

| Analyse | Choix du modèle qu'elle justifie |
|---|---|
| ACF / PACF | nombre de retards d'occupation (7, testé contre 3 et 14 en D5) |
| Corrélation croisée, Kaplan-Meier | admissions sur 3 et 7 jours ; au-delà, une admission ne pèse plus |
| Loi de Little | sorties sur 7 jours, qui complètent le bilan des flux |
| ADF + KPSS, force de la tendance | mois en sinus / cosinus ; validation glissante réentraînée |
| Kruskal-Wallis sur le jour de la semaine | indicatrices du jour, gardées seulement si D5 montre un gain |
| Surdispersion (M/G/∞), Erlang B | perte quantile τ = 0,8 |
| Spearman nettement supérieur à Pearson, résidus en courbe | noyau RBF plutôt que linéaire |
| Écarts d'échelle (CV, écart-type) | standardisation (D6) |
| Monte-Carlo | plancher d'erreur dû à la reconstitution de la cible |
| Ljung-Box des résidus du SVR | diagnostic final : p < 0,05 signifie qu'il manque un retard ou une variable |

---

## 12. Mathématiques H : survie, classification et transfert

### 12.1 Probabilités de sortie J0 / J1 / J2 (`svr/survie.py`, `modele_survie.py`)

**Tableau patient-jour.** Chaque séjour est découpé en jours de présence : une ligne par jour, avec
l'ancienneté k (0 = jour d'entrée) et l'événement (1 si l'enfant sort ce jour-là). Un séjour
censuré donne des lignes toutes à 0. Sortie non écrite : au jour n − 1, deux lignes « sort »
(poids p) et « reste » (poids 1 − p), puis au jour n une ligne « sort » de poids 1 − p.

**Hasard journalier** h(k, x) = P(sortir le jour d | présent au début du jour d, ancienneté k,
variables x). Pour un enfant présent ce matin :

```
P(J0) = h₀        P(J1) = (1 − h₀) h₁        P(J2) = (1 − h₀)(1 − h₁) h₂
```

Sorties attendues d'un jour = somme des probabilités des enfants présents.

**Risques concurrents** : un hasard par cause c (domicile, transfert, décès, autre), h = Σ_c h_c,
P(sortie par c le jour J1) = (1 − h₀) h_{c,1}.

**Références** :
- table de survie (actuarielle) : h(k) = Σ poids des sorties à k / Σ poids des présents à k ;
- loi gamma ajustée par les moments (a = m²/v, θ = v/m), sortie le jour ⌊T⌋ :
  h(k) = [F(k + 1) − F(k)] / [1 − F(k)], F(x) = P(a, x/θ) (gamma incomplète régularisée).

### 12.2 SVM de classification à coûts asymétriques (`svr/classification.py`)

```
J(w, b) = ½ ‖w‖² + Σ_i C_i max(0, 1 − y_i f(x_i))        y_i ∈ {−1, +1},  f(x) = w·x + b
∂J/∂w = w − Σ_i C_i y_i x_i 1(y_i f_i < 1)               ∂J/∂b = −Σ_i C_i y_i 1(y_i f_i < 1)
```

C_i = C₊ pour les positifs, C₋ pour les négatifs, multiplié par le poids de l'exemple. Choix
usuel pour des classes déséquilibrées : C₊ / C₋ = n₋ / n₊.

**Calibration de Platt** sur des données non utilisées pour l'entraînement :

```
P(y = 1 | f) = 1 / (1 + exp(A f + B))
cibles adoucies : t₊ = (N₊ + 1)/(N₊ + 2),  t₋ = 1/(N₋ + 2)
L = −Σ w_i [t_i ln p_i + (1 − t_i) ln(1 − p_i)]
∂L/∂A = Σ w_i (t_i − p_i) f_i        ∂L/∂B = Σ w_i (t_i − p_i)
```

**Mesures** : score de Brier (1/Σw) Σ w_i (p_i − y_i)² ; log-loss
−(1/Σw) Σ w_i [y ln p + (1 − y) ln(1 − p)] ; AUC = probabilité qu'un positif ait un score plus
élevé qu'un négatif (statistique de Mann-Whitney, calcul en O(n log n), ex æquo comptés pour
moitié).

### 12.3 Transfert vers des services à historique court (`transfert.py`)

Trois stratégies sur les mêmes jours du service cible : A local (cible seule, hyperparamètres de
la source gelés), B transfert direct (source seule, en taux), C groupé (source et cible réunies,
en taux), plus la persistance.

**Passage aux taux.** Avec N lits, Y = N y. Les pertes ε-insensible et pinball sont positivement
homogènes : L_ε(N r) = N L_{ε/N}(r). En posant f = N f_r et α = N α_r :

```
J_N = N² · [ ½ α_rᵀ K α_r + (C/N) Σ L_{ε/N}(y − f_r) ]
⇒  C_taux = C / N        ε_taux = ε / N        (γ inchangé : variables standardisées)
```

**Total de l'hôpital** = somme des prévisions centrales des services. La somme des quantiles 80 %
n'est pas le quantile 80 % de la somme : le total n'est noté que sur sa prévision centrale.

---

## 13. Outils numériques internes

Ces briques produisent toutes les p-valeurs ; elles sont écrites à la main
(`outil-saisie/statistiques.js`, et leurs équivalents Python dans `svr/`).

| Outil | Méthode | Sert à |
|---|---|---|
| ln Γ(x) | approximation de Lanczos (g = 7, 9 coefficients) | lois du χ², de Student, de Fisher, binomiale négative |
| gamma incomplète P(a, x) | série si x < a + 1, sinon fraction continue de Lentz | p-valeurs du χ², loi gamma |
| bêta incomplète I_x(a, b) | fraction continue | p-valeurs de Student et de Fisher |
| loi normale Φ(z) | fonction erreur | tests en z |
| quantile normal Φ⁻¹(p) | algorithme d'Acklam | droite de Henry, intervalle de Wilson |
| Student : P(|T| > t) | I_{ν/(ν+t²)}(ν/2, ½) | tests t, IC |
| χ² : P(X > x) | 1 − P(k/2, x/2) | χ², Bartlett, Ljung-Box, Jarque-Bera, log-rank |
| Fisher : P(F > f) | I_{d₂/(d₂+d₁f)}(d₂/2, d₁/2) | ANOVA, F global |
| inversion de matrice | Gauss-Jordan à pivot partiel | régression, KMO |
| valeurs propres | méthode de Jacobi | ACP |
| optimisation sans gradient | simplexe de Nelder-Mead | lissages exponentiels, SARIMA |
| nombres pseudo-aléatoires | mulberry32 à graine fixe | analyse parallèle de Horn, Monte-Carlo |

---

## 14. Fichier par fichier

### `nera/` : des registres à l'occupation

| Fichier | Rôle | Fonctions principales |
|---|---|---|
| `verrou.py` | période verrouillée : date, application, ouverture journalisée | `appliquer`, `ouvrir_coffre` |
| `chargement.py` | lecture de l'export, statut de chaque sortie, convention des jours, période exploitable | `lire_export`, `convention_nombre_de_jours`, `preparer_sejours`, `periode_exploitable` |
| `imputation.py` | durées inconnues (exclure, médiane, estimée par prix puis issue) et leur validation croisée | `valider_estimation` |
| `occupation.py` | recensement de minuit, trois scénarios | `sorties_possibles`, `reconstituer_occupation`, `trois_scenarios`, `resume_occupation` |
| `indicateurs.py` | TOM et fourchette, DMS, rotation, intervalle de rotation, mortalité, par mois et par année | `indicateurs`, `indicateurs_avec_fourchette` |
| `garde_fous.py` | loi de Little, Erlang B | `verifier_little`, `comparer_erlang`, `erlang_b` |
| `doublons.py` | patients « Ancien » réécrits au report : détection, classement, fusion sur demande | `reperer_reports`, `retirer_reports_confirmes` |

### `svr/` : les modèles

| Fichier | Contenu |
|---|---|
| `pertes.py` | ε-insensible, pinball, pinball ε-insensible, hinge, et leurs dérivées |
| `noyaux.py` | noyaux linéaire, RBF, composite |
| `optimiseurs.py` | descente de gradient, momentum, Adam, décroissance du pas |
| `modeles.py` | `ModeleSVR` (boucle, meilleur point, moyenne de Polyak), `SVRLineaire`, `SVRNoyau`, `SVRNoyauComposite`, `IntervalleQuantile` |
| `niveaux.py` | `Hyperparametres` et `fabrique(niveau, hp)` des niveaux 1 à 4 |
| `empilement.py` | niveau 5 (poids softplus) |
| `caracteristiques.py` | tableau d'apprentissage, standardisation, options de variables (fériés, vacances, nombre de retards) |
| `validation.py` | validation glissante, découpage final |
| `references.py` | niveau 0 et intervalle naïf |
| `classiques.py` | Holt-Winters additif amorti, régression ridge |
| `metriques.py` | métriques et Diebold-Mariano avec correction HLN |
| `recherche.py` | grille et essaim particulaire |
| `analyse.py` | Pearson, Spearman, ACF, PACF, profils, calibration, courbe d'apprentissage, importance par permutation, coût des décisions, kappa de Cohen |
| `classification.py` | SVM à coûts par exemple, Platt, Brier, log-loss, AUC |
| `survie.py` | tableau patient-jour, hasard, J0/J1/J2, table de survie, loi gamma |
| `calendrier.py` | jours fériés (Pâques calculée), fêtes musulmanes et vacances lues dans `donnees/` |
| `reproductibilite.py` | fiche d'environnement (versions, commande, commit, paramètres) |
| `concurrents.py` | modèles d'apprentissage concurrents (forêt aléatoire, boosting, perceptron, LSTM) : écrit, ni branché ni testé, réservé à une étape ultérieure |

### `outil-saisie/` : saisie et analyse des registres

| Fichier | Rôle |
|---|---|
| `saisie.html` | page unique : saisie, contrôle qualité, sauvegarde, reconstitution de l'occupation (`calculerIndicateurs`) |
| `registres.js` | description des registres de chaque service (colonnes, règles) |
| `statistiques.js` | bibliothèque statistique écrite à la main (`window.Stat`) : lois, tests, régression, ACP, modèles de prévision, SARIMA |
| `indicateurs.js` | rubriques d'analyse, graphiques SVG dessinés à la main, vues 3D, panneau des avertissements |
| `occupation-validation.js` | bilan des flux, Monte-Carlo, Kaplan-Meier, file M/G/∞ |
| `calendrier.js` | jours fériés et vacances scolaires du Cameroun (mêmes dates que les fichiers Python) |
| `convertir_photos.*` | conversion locale des photos (HEIC vers JPEG) |
| `assets/` | thème, logo, icône |
| `LISEZMOI.md` | mode d'emploi détaillé de l'outil |

---

## 15. Les scripts, dans l'ordre

Toutes les sorties vont dans `resultats/`. Chaque script écrit une fiche
`*_environnement.json` (versions, commande, commit, paramètres) pour la reproductibilité.

### Étape 1 : `rapport_occupation.py`, de l'export à l'occupation

```bash
~/memoire-env/bin/python rapport_occupation.py donnees/<export>.csv --service PED --lits <N>
```

Affiche la convention des jours mesurée, les séjours gardés et écartés, la période exploitable,
l'occupation et sa fourchette, la loi de Little et Erlang B, les indicateurs par mois. Écrit
`occupation_PED.csv` (et ses versions basse et haute), `indicateurs_PED_par_mois.csv`,
`indicateurs_PED_par_annee.csv`, `occupation_PED.png`, le diagramme de flux des données
(`flux_donnees_PED.csv` / `.png`) et la liste des reports suspects (`reports_PED.csv`).

Options : `--lits-fichier donnees/lits_PED.csv` (capacité variable, fichier `date_debut;lits`) ;
`--reports retirer` (fusion des reports confirmés, seulement après confirmation par le service).

### Étape 2 : `lancer_niveaux.py`, ablation des niveaux 0 à 5

```bash
~/memoire-env/bin/python lancer_niveaux.py --service PED --horizons 1 3 7 --tau 0.8 --recherche grille
```

Validation glissante sur les 6 mois avant le verrou, une origine tous les 14 jours. Options :
`--recherche pso`, `--scenario basse|haute`, `--pas`, `--debut-validation`. Écrit
`ablation_PED_h<h>.csv`, `ablation_PED_tests.csv` (Diebold-Mariano) et
`hyperparametres_PED_h<h>.json` (relu par les étapes suivantes).

### Étape 3 : `sensibilite.py`, robustesse à la convention des jours

```bash
~/memoire-env/bin/python sensibilite.py --service PED --horizons 1 3 7
```

Écrit `sensibilite_PED.csv` et `sensibilite_PED_synthese.csv` (verdict robuste ou sensible).

### Étape 3 bis : `benchmark_choix.py`, chaque choix face à ses alternatives

```bash
~/memoire-env/bin/python benchmark_choix.py --service PED --horizons 1 7
```

Options : `--dimensions D1 D5`, `--pas` (28 par défaut), `--rapide`. Écrit
`benchmark_PED_<D>_h<h>.csv` et `benchmark_PED.md` (tableaux et conclusions prêts pour le mémoire).

### Étape 4 : `visualisations.py`, toutes les figures

```bash
~/memoire-env/bin/python visualisations.py --service PED
```

### Étape 5 : `validation_finale.py`, une seule fois, à la toute fin

```bash
~/memoire-env/bin/python validation_finale.py donnees/<export>.csv --service PED --lits <N> \
    --extraction <aaaa-mm-jj> --confirmation "J'ouvre le coffre pour la validation finale"
```

Chaque niveau, avec ses hyperparamètres retenus, est entraîné sur tout ce qui précède le verrou,
puis prévoit la période verrouillée.

### Étape 6 : `modele_survie.py`, probabilités de sortie J0 / J1 / J2

```bash
~/memoire-env/bin/python modele_survie.py donnees/<export>.csv --service PED --lits <N> --causes
```

Écrit `survie_PED.md` / `.csv`, trois figures et `survie_PED_modele.json` (paramètres du modèle,
sans aucune donnée de patient).

### Étape 7 : `transfert.py`, services à historique court et total de l'hôpital

```bash
~/memoire-env/bin/python transfert.py donnees/<export>.csv --source PED --cibles MED CHI \
    --lits PED=20 MED=24 CHI=18 --horizons 1 7
```

Écrit `transfert_<SERVICE>_h<h>.csv`, `transfert_total_h<h>.csv` et `transfert.md`.

### À part

```bash
~/memoire-env/bin/python demo_entrainement.py --exercice
~/memoire-env/bin/python qualite_saisie.py donnees/saisie_A.csv donnees/saisie_B.csv
```

`demo_entrainement.py` affiche J, ‖∇J‖ et les paramètres pendant l'entraînement d'un petit exemple
dont la solution exacte est connue (J = 1,5833). `qualite_saisie.py` compare deux saisies des
mêmes photos (accord par colonne, kappa de Cohen, liste des cases en désaccord).

---

## 16. Les figures et leur lecture

Écrites dans `resultats/figures_<SERVICE>/`.

| Figure | Contenu | Lecture |
|---|---|---|
| `01_serie_occupation` | occupation chaque soir, fourchette, capacité | bande large = beaucoup de sorties non écrites |
| `02_profils` | moyennes par jour de la semaine et par mois | justifie ou non les variables de calendrier |
| `03_autocorrelation` | ACF et PACF jusqu'à 35 jours | décroissance lente = forte mémoire ; pics à 7, 14, 21 = rythme hebdomadaire |
| `04_correlations` | Pearson et Spearman entre variables et cible | Pearson différent de Spearman = relation courbe |
| `05_relations` | cible face aux principales variables | nuage serré = variable informative |
| `06_nuage_3d` | jours dans l'espace (occupation, admissions 7 j, cible) | plan suffisant ou surface courbe nécessaire |
| `07_hyperplan_svr_3d` | SVR linéaire : plan, tube ± ε, vecteurs de support | seuls les points sur ou hors du tube déterminent le plan |
| `08_surface_svr_rbf_3d` | SVR RBF : surface médiane et quantiles 5 % / 95 % | les points doivent tomber entre les deux grilles 9 fois sur 10 |
| `09_convergence` | J(t)/J(0) pendant l'entraînement | doit descendre puis se stabiliser |
| `10_courbe_apprentissage` | erreurs selon la longueur de l'historique | courbes qui se rapprochent = assez de données |
| `11_hyperparametres` | erreur de validation selon C et γ | large zone sombre = choix peu sensible |
| `12_previsions` | médiane, quantile τ, intervalle 90 %, réalité, persistance | la réalité doit rester dans la bande |
| `13_residus` | histogramme et évolution des erreurs | centré sur 0 = pas de biais ; dérive = réentraîner |
| `14_calibration` | couverture observée contre niveau demandé | sous la diagonale = sous-estimation des besoins |
| `15_ablation` | MAE et RMSE des niveaux 0 à 5 | chaque niveau doit améliorer le précédent |
| `16_sensibilite` | gain selon la convention des jours | barres de même signe = conclusion robuste |
| `17_importance_variables` | importance par permutation | barre proche de 0 = variable inutile |

Le module lits fait de la **régression** : l'hyperplan ne sépare pas deux classes, il passe au
milieu des données avec un tube de tolérance ± ε. L'hyperplan séparateur viendra avec le module
de triage (classification).

---

## 17. Tests

```bash
~/memoire-env/bin/python -m pytest tests -q
```

| Fichier | Ce qui est vérifié |
|---|---|
| `test_svr.py` | pertes et dérivées, noyaux, gradients des SVR par différences finies, Adam, convergence vers la solution exacte, tableau sans fuite |
| `test_occupation.py` | recensement de minuit sur des cas faits à la main, censure, Little, Erlang B |
| `test_indicateurs.py` | TOM, DMS, rotation, mortalité ; part inclusive globale et mensuelle ; trois scénarios ; série attendue toujours entre les bornes |
| `test_verrou.py` | rien après le verrou n'est lu ; ouverture journalisée ; période exploitable |
| `test_analyse.py` | Pearson, rangs avec ex æquo, Spearman, ACF, PACF, calibration, profils |
| `test_survie_transfert.py` | Polyak après arrêt anticipé, gradient du SVM classifieur, Platt, AUC et Brier, gamma incomplète, tableau patient-jour, table de survie, J0/J1/J2, conversion des hyperparamètres en taux |
| `test_ajouts.py` | Pâques et fériés, Holt-Winters, ridge, options des variables, reports, capacité variable, kappa, coût des décisions, importance par permutation |
| `test_calendrier.py` | concordance des jours fériés et des vacances entre Python, JavaScript et les fichiers de données |

`test_calendrier.py` lit les fichiers de `donnees/` : il demande que ces fichiers soient présents
localement.

Les fichiers JavaScript se vérifient par `node --check <fichier>.js` (syntaxe), puis dans le
navigateur : chaque section de l'outil affiche « Calcul impossible » avec le message d'erreur si
un calcul échoue.

---

## 18. État d'avancement et suite du travail

| Partie | État |
|---|---|
| Outil de saisie : saisie, contrôle qualité, indicateurs, statistiques, prévisions, validation de l'occupation | fait, utilisé pour la pédiatrie |
| Lecture de l'export, période verrouillée, statuts, période exploitable | fait, testé |
| Occupation (recensement de minuit, trois scénarios), indicateurs, Little, Erlang B | fait, testé, identique dans l'outil |
| SVR niveaux 1 à 5, optimiseurs, validation glissante, Diebold-Mariano, recherche d'hyperparamètres | fait, gradients vérifiés |
| Banc de comparaison D1 à D10, sensibilité, figures | fait |
| Jours fériés et vacances scolaires camerounais | fait, testé |
| Modèle de survie J0/J1/J2, transfert, total de l'hôpital | fait, testé |
| Exécution de toute la chaîne Python sur les données réelles | à faire, après la fin de la saisie |
| Validation finale sur la période verrouillée | écrite, à lancer une seule fois à la toute fin |
| Module triage (SVM de classification) | à faire, attend le registre des urgences |
| Branchement à l'API (`PrevisionCapaciteService`) | à faire, quand un modèle sera validé |

Suite du travail, dans l'ordre :

1. Terminer la saisie et corriger les données (dates incohérentes, doublons, numéros manquants),
   puis mesurer le taux d'erreur par double saisie.
2. Valider la reconstitution : comptages réels dans le bilan des flux, intervalle de Monte-Carlo.
3. Faire l'analyse descriptive et l'analyse de la série (sections 7 et 8) pour fixer les entrées.
4. Exporter le dataset harmonisé, lancer les étapes 1 à 4 et le banc de comparaison.
5. Comparer le SVR retenu au naïf, aux lissages, à AR et SARIMA (MAE, RMSE, MASE, pinball,
   couverture, Diebold-Mariano) ; vérifier ses résidus (ACF, Ljung-Box).
6. Lancer la validation finale une seule fois.
7. Pistes à mesurer par le banc avant adoption : sorties attendues du modèle de survie comme
   variable d'entrée ; variable « présents attendus » Σ_k A_{t−k} Ŝ(k) ; référence quantile d'une
   loi de Poisson ou binomiale négative de moyenne λ̂W.

---

## 19. Références

- Kaplan E. L., Meier P. (1958). Nonparametric estimation from incomplete observations. *JASA*.
- Greenwood M. (1926). The natural duration of cancer. *Reports on Public Health and Medical Subjects*.
- Mantel N. (1966). Evaluation of survival data and two new rank order statistics. *Cancer Chemotherapy Reports*.
- Little J. D. C. (1961). A proof for the queuing formula L = λW. *Operations Research*.
- Erlang A. K. (1917). Solution of some problems in the theory of probabilities of significance in automatic telephone exchanges.
- Vapnik V. (1995). *The Nature of Statistical Learning Theory*. Springer.
- Smola A. J., Schölkopf B. (2004). A tutorial on support vector regression. *Statistics and Computing*.
- Koenker R., Bassett G. (1978). Regression quantiles. *Econometrica*.
- Gönen M., Alpaydın E. (2011). Multiple kernel learning algorithms. *JMLR*.
- Wolpert D. H. (1992). Stacked generalization. *Neural Networks*.
- Kingma D. P., Ba J. (2015). Adam: a method for stochastic optimization. *ICLR*.
- Polyak B. T., Juditsky A. B. (1992). Acceleration of stochastic approximation by averaging. *SIAM J. Control Optim.*
- Kennedy J., Eberhart R. (1995). Particle swarm optimization. *IEEE ICNN*.
- Platt J. (1999). Probabilistic outputs for support vector machines.
- Diebold F. X., Mariano R. S. (1995). Comparing predictive accuracy. *JBES*.
- Harvey D., Leybourne S., Newbold P. (1997). Testing the equality of prediction mean squared errors. *IJF*.
- Hyndman R. J., Athanasopoulos G. *Forecasting: Principles and Practice*.
- Wang X., Smith K., Hyndman R. J. (2006). Characteristic-based clustering for time series data. *DMKD*.
- Ljung G. M., Box G. E. P. (1978). On a measure of lack of fit in time series models. *Biometrika*.
- Dickey D. A., Fuller W. A. (1979). Distribution of the estimators for autoregressive time series with a unit root. *JASA*.
- Kwiatkowski D., Phillips P., Schmidt P., Shin Y. (1992). Testing the null hypothesis of stationarity. *J. Econometrics*.
- Horn J. L. (1965). A rationale and test for the number of factors in factor analysis. *Psychometrika*.
- Kaiser H. F. (1974). An index of factorial simplicity. *Psychometrika*.
- Meeus J. (1991). *Astronomical Algorithms*.
- Press W. H. et al. *Numerical Recipes* (fonctions gamma et bêta incomplètes).
