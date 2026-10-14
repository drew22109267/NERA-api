# Méthode : fonctions de coût, minimisation et justification de chaque choix

Ce document explique, pour chaque modèle du mémoire :

1. **ce qu'il prédit** ;
2. **la fonction de coût** : ce que coûte une erreur, jour par jour ;
3. **la fonction minimisée** : le coût total que l'entraînement rend le plus petit possible ;
4. **ce qui est appris** (paramètres) et **ce qui est réglé** (hyperparamètres) ;
5. **la technique de minimisation**, pas à pas ;
6. **le banc de comparaison** qui teste chaque choix contre ses alternatives.

Il se termine par le **registre de toutes les décisions** : pour chacune, l'option retenue, les
alternatives, la raison du choix et le banc qui la vérifie.

Les formules complètes, avec leurs démonstrations, sont dans [`README.md`](README.md) (sections 5 à 13).
Ce document-ci se concentre sur la logique des choix.

---

## Sommaire

1. [Le problème posé](#1-le-problème-posé)
2. [Ce qu'on attend d'une bonne prévision : les mesures](#2-ce-quon-attend-dune-bonne-prévision--les-mesures)
3. [Les SVR, niveaux 1 à 5](#3-les-svr-niveaux-1-à-5)
4. [Les modèles de référence](#4-les-modèles-de-référence)
5. [Les modèles concurrents d'apprentissage](#5-les-modèles-concurrents-dapprentissage)
6. [Le réglage des hyperparamètres](#6-le-réglage-des-hyperparamètres)
7. [La validation : comment on évite de se tromper soi-même](#7-la-validation--comment-on-évite-de-se-tromper-soi-même)
8. [Les bancs de comparaison et leur lecture](#8-les-bancs-de-comparaison-et-leur-lecture)
9. [Registre de toutes les décisions](#9-registre-de-toutes-les-décisions)

---

## 1. Le problème posé

Chaque soir (le jour t), on veut prévoir le **nombre d'enfants présents à minuit** dans le service de
pédiatrie le jour t + h, pour h = 1, 3 ou 7 jours. Cette série, notée y_t, est reconstituée à partir des
registres papier (recensement de minuit, voir README section 5).

Pour un jour t, le modèle reçoit un vecteur x_t de variables connues ce soir-là :

| Variable | Sens |
|---|---|
| `occ_j-0` … `occ_j-6` | présents les 7 derniers jours (y_t, y_{t−1}, …, y_{t−6}) |
| `adm_3j`, `adm_7j` | admissions des 3 et des 7 derniers jours |
| `sorties_7j` | sorties des 7 derniers jours |
| `cible_jour_0` … `cible_jour_6` | jour de la semaine du jour prévu (7 cases 0/1) |
| `mois_sin`, `mois_cos` | mois du jour prévu, placé sur un cercle (décembre voisin de janvier) |
| `cible_feriee`, `veille_feriee`, `cible_vacances` | en option : jour férié, veille de férié, vacances scolaires |

Il doit rendre une prévision ŷ_{t+h}, et pour les modèles quantiles plusieurs prévisions : la médiane, le
**quantile τ = 0,8** (le nombre de lits à prévoir) et les bornes d'un intervalle à 90 %.

**Pourquoi un quantile et pas la moyenne ?** Manquer un lit (un enfant sans place) coûte plus cher que
réserver un lit de trop. Si une pénurie coûte r fois plus qu'un lit vide, la décision optimale est le
quantile τ = r / (1 + r) de l'occupation. τ = 0,8 revient à dire qu'une pénurie coûte 4 fois plus. Ce choix
est testé dans le banc D4 (τ de 0,5 à 0,9 et coût moyen pour plusieurs rapports r).

---

## 2. Ce qu'on attend d'une bonne prévision : les mesures

On note y la valeur réelle, ŷ la prévision, n le nombre de jours évalués.

| Mesure | Formule | Ce qu'elle dit | Meilleur |
|---|---|---|---|
| MAE (erreur absolue moyenne) | (1/n) Σ \|y − ŷ\| | de combien d'enfants on se trompe en moyenne | petite |
| RMSE | √((1/n) Σ (y − ŷ)²) | comme la MAE, mais punit davantage les grosses erreurs | petite |
| Biais | (1/n) Σ (ŷ − y) | > 0 : le modèle prévoit trop ; < 0 : pas assez | proche de 0 (sauf quantile) |
| Perte pinball au quantile τ | (1/n) Σ ρ_τ(y − q̂_τ) | la qualité d'une prévision de quantile : la mesure « juste » pour τ = 0,8 | petite |
| Couverture à 90 % | part des jours où bas ≤ y ≤ haut | l'intervalle tient-il sa promesse ? | proche de 90 % |
| Gain sur la persistance | 1 − MAE(modèle) / MAE(« demain = aujourd'hui ») | ce que le modèle apporte de plus que la règle la plus simple | positif |
| Test de Diebold-Mariano | voir 8.2 | l'écart entre deux modèles est-il réel ou dû au hasard ? | p < 0,05 |

La perte pinball s'écrit ρ_τ(r) = τ·r si r ≥ 0 (sous-estimation), (τ − 1)·r si r < 0 (surestimation). Avec
τ = 0,8, une sous-estimation d'un lit coûte 0,8 et une surestimation d'un lit coûte 0,2.

---

## 3. Les SVR, niveaux 1 à 5

Les cinq niveaux forment une **ablation** : chaque niveau ajoute une seule idée au précédent, et doit
prouver par le banc (D1, puis Diebold-Mariano) qu'elle améliore la prévision.

### 3.1 Niveau 1 : SVR linéaire

**Prévision.** ŷ = f(x) = w·x + b : une combinaison linéaire des variables (un hyperplan).

**Fonction de coût (par jour).** La perte ε-insensible : L_ε(r) = max(0, |r| − ε), avec r = y − f(x).
Une erreur de moins de ε lits ne coûte rien (c'est le « tube » du SVR) ; au-delà, le coût croît linéairement.

**Fonction minimisée.**

```
J(w, b) = ½ ‖w‖²  +  C · Σ_i L_ε(y_i − w·x_i − b)
          ───────     ───────────────────────────
          simplicité  erreurs hors du tube
```

Le premier terme pousse vers un modèle simple (les coefficients ne s'emballent pas : c'est la
« marge » du SVM) ; le second fait payer les erreurs. **C** règle l'équilibre : C grand, on colle aux
données ; C petit, on privilégie la simplicité.

**Appris :** w (un poids par variable) et b. **Réglés :** C, ε.

**Technique de minimisation : descente de gradient avec Adam**, gradients écrits à la main.

1. Dérivée de la perte par rapport à la prévision : g_i = ∂L/∂f_i = −signe(r_i) si |r_i| > ε, 0 sinon.
2. Gradient de J : ∂J/∂w = w + C·Σ_i g_i x_i = w + C Xᵀg ; ∂J/∂b = C·Σ_i g_i.
3. Pas d'Adam, répété jusqu'à 3 000 fois :
   - m ← 0,9·m + 0,1·g (moyenne du gradient) ; v ← 0,999·v + 0,001·g² (moyenne du gradient au carré) ;
   - corrections de démarrage m̂ = m / (1 − 0,9^t), v̂ = v / (1 − 0,999^t) ;
   - θ ← θ − η_t · m̂ / (√v̂ + 10⁻⁸), avec un pas qui diminue : η_t = η₀ / √(1 + t/T), η₀ = 0,05, T = 500.
4. **Arrêt** quand J ne baisse plus (moins de 10⁻⁷ en relatif) pendant 100 pas.
5. **Moyenne de Polyak** : la perte n'étant pas dérivable partout, les paramètres oscillent autour du
   minimum ; on fait la moyenne des points visités sur la seconde moitié de l'entraînement, et l'on garde,
   entre cette moyenne et le meilleur point rencontré, celui dont J est le plus petit.

Pourquoi c'est sûr : J est **convexe** (somme d'une parabole et de fonctions en « V ») ; il n'a donc pas
de faux minimum, et la descente avec pas décroissant converge vers le minimum global. Les gradients sont
vérifiés par différences finies dans les tests.

**Bancs :** D1 (contre les autres modèles), D3 (perte), D8 (technique de minimisation), sensibilité de C et ε.

### 3.2 Niveau 2 : SVR à noyau RBF

**Prévision.** f(x) = Σ_j α_j K(x_j, x) + b, avec le noyau gaussien K(x, z) = exp(−γ‖x − z‖²). Chaque jour
d'entraînement x_j « vote » pour la prévision, d'autant plus fort que la situation x lui ressemble. Cela
permet des relations **non linéaires** (effets de seuil, saturation).

**Fonction de coût :** la même perte ε-insensible.

**Fonction minimisée.** J(α, b) = ½ αᵀKα + C·Σ_i L_ε(y_i − f(x_i)), où K est la matrice des ressemblances
entre jours d'entraînement (αᵀKα est la « simplicité » de f dans l'espace du noyau).

**Appris :** α (un poids par jour d'entraînement) et b. **Réglés :** C, ε, γ (portée du noyau : γ grand,
seuls les jours très semblables comptent ; γ petit, la fonction est lisse).

**Technique :** Adam comme au niveau 1, avec ∂J/∂α = K(α + Cg) et ∂J/∂b = C·Σ g. On descend selon la
direction **préconditionnée** α + Cg (le gradient sans le facteur K) : même minimum, atteint plus vite, car K
est souvent presque singulière. J reste convexe.

**Bancs :** D1, D2 (noyau linéaire, RBF, composite), D6 (standardisation), D8, sensibilité de C, ε, γ.

### 3.3 Niveau 3 : SVR quantile (coûts asymétriques)

**Fonction de coût :** la perte **pinball** ρ_τ(r) (section 2), qui donne le quantile τ au lieu de la
moyenne : en minimisant la somme des ρ_τ, la proportion de jours sous la prévision tend vers τ.

**Fonction minimisée.** J(α, b) = ½ αᵀKα + C·Σ_i ρ_τ(y_i − f(x_i)). Un modèle par quantile
(τ = 0,05 ; 0,5 ; 0,8 ; 0,95), puis les prévisions sont triées jour par jour pour que les quantiles ne se
croisent jamais. Le tube ε vaut 0 : un tube déformerait le quantile (démontré dans `svr/pertes.py`).

**Technique :** Adam, gradient de la pinball : g_i = −τ si r_i > 0, 1 − τ si r_i < 0.

**Bancs :** D1, D3, D4 (choix de τ selon le coût d'une pénurie), sensibilité de τ, C, γ.

### 3.4 Niveau 4 : SVR quantile à noyau composite

**Prévision.** Le noyau mélange deux blocs de variables : K = β·K₁(occupation passée) + (1 − β)·K₂(flux et
saison), avec β = σ(θ) = 1 / (1 + e^{−θ}) dans ]0, 1[. β dit quelle source d'information compte le plus.

**Fonction minimisée.** J(α, b, θ) = ½ αᵀK(θ)α + C·Σ_i ρ_τ(y_i − f(x_i)).

**Appris :** α, b **et β** (via θ). **Réglés :** C, γ₁, γ₂, τ.

**Technique :** Adam sur (α, b, θ), avec ∂J/∂θ = β(1 − β)·[½ αᵀDα + C gᵀDα], D = K₁ − K₂ (dérivation dans
`svr/modeles.py`, vérifiée par différences finies). Attention : J n'est plus convexe en θ ; la validation
glissante vérifie que le β appris tient sur des jours jamais vus.

**Bancs :** D1, D2, sensibilité de γ₁, γ₂, C, τ, et des réglages d'optimisation (famille `svr4`).

### 3.5 Niveau 5 : empilement

**Prévision.** f = Σ_k w_k·p_k + b : combinaison des prévisions p_k de la persistance et des niveaux 3 et 4,
avec des poids positifs w_k = ln(1 + e^{u_k}).

**Fonction minimisée.** J(u, b) = ½ λ Σ_k w_k² + C·Σ_i ρ_τ(y_i − f_i), sur des prévisions **hors
échantillon** (faites en validation glissante), sinon le méta-modèle ferait confiance au modèle qui a appris
par cœur.

**Technique :** Adam ; ∂J/∂u_k = σ(u_k)·[λ w_k + C·Σ_i g_i p_ik].

**Banc :** D9 (meilleur modèle seul, moyenne simple, empilement).

---

## 4. Les modèles de référence

Ils fixent la barre à franchir. Tous sont **réestimés à chaque origine** de la validation glissante, sur les
seuls jours connus ce soir-là, exactement comme le SVR est réentraîné (fichier `svr/series_classiques.py`).

| Modèle | Fonction minimisée | Technique |
|---|---|---|
| Persistance, saisonnier naïf, moyenne mobile | aucune (règle fixe) | — |
| Lissage simple, Holt linéaire, Holt amorti, lissage saisonnier, Holt-Winters additif et multiplicatif, Thêta | somme des carrés des erreurs à un pas : SSE = Σ_t (y_t − ŷ_{t\|t−1})² | **simplexe de Nelder-Mead** sur α, β, γ, φ (écrits σ(u) pour rester dans ]0, 1[, φ dans ]0,8 ; 0,98[) |
| AR(p) | somme des carrés des résidus Σ (y_t − c − Σ a_i y_{t−i})² | **solution exacte** des équations normales (XᵀX)a = Xᵀy ; p choisi par le critère AIC |
| SARIMA | somme conditionnelle des carrés des innovations (CSS) Σ ε_t² | Nelder-Mead sur les coefficients (passés par tanh) ; ordre choisi par BIC puis erreur sur la fin de l'apprentissage |
| Régression ridge | Σ (y_i − w·x_i − b)² + λ‖w‖² | solution exacte (X̃ᵀX̃ + λI)w = X̃ᵀỹ |

**Le simplexe de Nelder-Mead, pas à pas.** Il cherche le minimum d'une fonction sans calculer de dérivée.
On part d'un triangle de points (un « simplexe » de d + 1 points pour d paramètres). À chaque étape :
1. on classe les points du meilleur au pire ;
2. on **réfléchit** le pire point par rapport au centre des autres ;
3. si le reflet est le meilleur de tous, on tente d'aller plus loin (**expansion**, ×2) ;
4. s'il reste mauvais, on **contracte** vers le centre (×½), ou l'on **réduit** tout le simplexe vers le
   meilleur point (×½) ;
5. on s'arrête quand tous les points ont presque la même valeur (écart relatif < 10⁻⁹).

**Quantiles des références.** Une référence donne une seule prévision ŷ. Pour la juger avec la même perte
pinball que le SVR, on lui ajoute les quantiles de ses propres erreurs à h jours sur l'apprentissage :
q̂_τ = ŷ + Q_τ(e).

**Banc :** D1.

---

## 5. Les modèles concurrents d'apprentissage

Mêmes variables, même standardisation, même validation et mêmes quantiles que le SVR : seule la **forme** de
la fonction change. Un écart de précision s'attribue donc au modèle, pas aux données (`svr/concurrents.py`).

### 5.1 Forêt aléatoire quantile

**Un arbre** découpe l'espace des variables en rectangles. À chaque nœud, il choisit la variable et le
seuil qui **minimisent la somme des carrés** des deux côtés : SCE = Σ_gauche (r − r̄_G)² + Σ_droite (r − r̄_D)².
Technique : recherche **exhaustive gloutonne**, en une passe triée par variable. Il n'y a pas de fonction
globale minimisée : l'arbre fait le meilleur choix local à chaque nœud.

**La forêt** fait pousser 300 arbres, chacun sur un tirage avec remise des jours et, à chaque nœud, sur un
tiers des variables tirées au hasard. Leurs erreurs se compensent. Pour un quantile, chaque jour
d'entraînement reçoit un poids selon qu'il tombe dans les mêmes feuilles que le jour à prévoir, et le
quantile τ est lu sur cette distribution pondérée (Meinshausen, 2006).

**Réglés :** nombre d'arbres, profondeur, taille minimale des feuilles, part des variables.
**Bancs :** D1, sensibilité (famille `foret`).

### 5.2 Gradient boosting quantile

**Fonction minimisée :** Σ_i ρ_τ(y_i − F(x_i)).
**Technique : descente de gradient dans l'espace des fonctions.** On part de F₀ = quantile τ de y ; à chaque
étape, un petit arbre apprend la direction de descente (les pseudo-résidus −∂ρ_τ/∂F = τ ou τ − 1), chaque
feuille reçoit le pas optimal (le quantile τ des résidus de la feuille), puis F ← F + ν·arbre. Un modèle
par quantile.

**Réglés :** étapes, taux ν, profondeur, sous-échantillon. **Bancs :** D1, sensibilité (famille `boosting`).

### 5.3 Perceptron multicouche quantile

**Prévision :** deux couches cachées avec ReLU, une sortie par quantile.
**Fonction minimisée :** J = (1/n) Σ_i Σ_q ρ_{τ_q}(y_i − F_iq) + (λ/2)·Σ ‖W‖².
**Technique :** rétropropagation écrite à la main (règle de la chaîne couche par couche), Adam, arrêt
anticipé sur les 15 % derniers jours de l'apprentissage (dans l'ordre du temps), moyenne de 3
initialisations. J n'est pas convexe : l'arrêt anticipé et la moyenne des initialisations limitent le
surapprentissage.

**Réglés :** architecture, taux, λ, époques, patience, graines. **Bancs :** D1, sensibilité (famille `mlp`).

### 5.4 LSTM quantile

**Prévision :** une cellule à mémoire lit l'occupation des 7 derniers jours dans l'ordre, puis son état
final est combiné aux autres variables.
**Fonction minimisée :** la même que le perceptron.
**Technique :** rétropropagation dans le temps écrite à la main, Adam, arrêt anticipé, moyenne de graines.
Avec quelques centaines de jours, le risque de surapprentissage est fort : c'est ce que la comparaison doit
montrer ou démentir.

**Bancs :** D1, sensibilité (famille `lstm`).

---

## 6. Le réglage des hyperparamètres

Les hyperparamètres (C, ε, γ…) ne s'apprennent pas par gradient. On les choisit en minimisant la **perte
pinball moyenne au quantile τ** (ou la MAE pour les niveaux non quantiles) **en validation glissante** :

- **grille** : toutes les combinaisons d'une liste (par exemple C ∈ {0,3 ; 1 ; 3}, γ ∈ {0,02 ; 0,05 ; 0,2}) ;
- **essaim particulaire** : 8 particules explorent l'espace pendant 10 itérations ; chacune est attirée par
  sa meilleure position et par la meilleure de l'essaim
  (v ← 0,7·v + 1,5·r₁(p − x) + 1,5·r₂(g − x)), C et γ étant explorés en échelle logarithmique.

**Limite à écrire dans le mémoire :** les réglages étant choisis sur les jours de validation, l'erreur
mesurée sur ces mêmes jours est un peu optimiste. C'est pour cela que le **test final** porte sur
septembre-octobre 2026, jamais vus pendant les réglages.

**Bancs :** D10 (défaut, grille, essaim : le gain vaut-il le temps de calcul ?) et la **sensibilité de
chaque paramètre** (`benchmark_parametres.py`).

---

## 7. La validation : comment on évite de se tromper soi-même

**Règle d'or :** un modèle ne voit jamais une information qu'il n'aurait pas eue le soir de la prévision.

1. **Période verrouillée.** Les données à partir du 01/09/2026 ne sont lues par aucun calcul pendant le
   développement. Elles serviront une seule fois, au test final.
2. **Validation glissante.** Sur les 6 mois qui précèdent le verrou, on avance l'origine O par pas de 14 ou
   28 jours. À chaque O : entraînement sur tous les jours dont la cible est connue (≤ O), prévision des jours
   suivants, puis O avance. Les modèles sont **réentraînés à chaque origine**, comme ils le seraient en
   service.
3. **Standardisation** (z = (x − moyenne)/écart-type) apprise sur l'entraînement seul, à chaque origine.
4. **Test final** : septembre prévu par un modèle appris jusqu'au 31 août ; octobre prévu après
   réentraînement au 30 septembre.

---

## 8. Les bancs de comparaison et leur lecture

### 8.1 Les quatre bancs

| Banc | Script | Ce qu'il compare |
|---|---|---|
| Prétraitement | `benchmark_pretraitement.py` | P1 à P7 : comment on passe des registres à la série |
| Choix de conception | `benchmark_choix.py` | D1 à D11 : modèles, noyau, perte, τ, variables, standardisation, fenêtre, optimisation, combinaison, recherche, chaque variable |
| Paramètres | `benchmark_parametres.py` | chaque paramètre, un à la fois, autour de sa valeur retenue |
| Convention des jours | `sensibilite.py` | les trois séries (basse, attendue, haute) : les conclusions changent-elles ? |

Dans tous les bancs : **une seule chose change à la fois**, tout le reste est identique (mêmes jours, même
validation), et chaque variante est comparée au choix retenu (marqué « retenu ») par le test de Diebold-Mariano.

### 8.2 Le test de Diebold-Mariano, simplement

Deux modèles A et B prévoient les mêmes jours. Chaque jour, on calcule la différence de leurs erreurs
d_t = |e_t^A| − |e_t^B|. Si les deux modèles se valent, d_t vaut 0 en moyenne. Le test regarde si la
moyenne observée de d_t est trop éloignée de 0 pour être due au hasard, en tenant compte du fait que des
prévisions à h jours faites des jours voisins se ressemblent (correction de Harvey, Leybourne et Newbold).

### 8.3 Lire la colonne « vs choix retenu »

| Verdict | Sens | Conséquence |
|---|---|---|
| choix retenu | la référence de la comparaison | — |
| équivalent | différence non significative (p ≥ 0,05) | le choix retenu est défendable ; on peut citer l'alternative comme aussi bonne |
| moins bon | significativement moins précis (p < 0,05) | argument **pour** le choix retenu |
| meilleur | significativement plus précis (p < 0,05) | **le choix retenu doit être revu**, et c'est écrit dans la conclusion du tableau |
| identique | exactement les mêmes prévisions | l'option n'a aucun effet |

Pour D11 (une variable retirée) : « moins bon » veut dire que la variable est **utile** ; « meilleur » veut
dire que le modèle fait mieux **sans** elle, et qu'elle devrait être retirée.

Pour la sensibilité des paramètres : l'**amplitude** (MAE max − MAE min) / MAE retenue dit si le résultat
dépend beaucoup de ce réglage. Une petite amplitude est rassurante : la conclusion ne tient pas à un réglage fin.

---

## 9. Registre de toutes les décisions

Chaque ligne : ce qui a été retenu, contre quoi, pourquoi, et où c'est vérifié. « Protocole » signifie que
le choix est fixé par la méthode du mémoire et n'est pas mis en compétition (la raison est donnée).

### 9.1 Données

| Décision | Retenu | Alternatives | Pourquoi | Vérifié par |
|---|---|---|---|---|
| Service étudié | pédiatrie | autres services | seul registre disponible sur 27 mois ; les autres services n'ont que 6 mois (transfert, `transfert.py`) | protocole |
| Période de données | juillet 2024 → 31 août 2026 | — | tout ce qui est saisi avant le verrou | protocole |
| Période de test final | septembre-octobre 2026, verrouillée | 1 mois | 2 mois = test à 1 mois + test après réentraînement ; 1 mois est trop court pour un test fiable | protocole |
| Cible | présents à minuit, J+1, J+3, J+7 | admissions, sorties | c'est le nombre de lits occupés ; les trois horizons couvrent la décision du lendemain et de la semaine | protocole |
| Source des données | registre saisi → NERA → export harmonisé | lecture directe de l'outil | chemin final de production ; même harmonisation pour tous les hôpitaux | protocole |
| Qualité de saisie | contrôle sur photos (page par page) | — | mesure le bruit des données, limite basse de l'erreur atteignable | contrôle qualité de l'outil |

### 9.2 Prétraitement (`benchmark_pretraitement.py`)

| Décision | Retenu | Alternatives | Pourquoi | Banc |
|---|---|---|---|---|
| Durées inconnues | estimée (prix, puis issue, puis médiane) | exclure, médiane | exclure sous-estime l'occupation des mois incomplets ; le prix suit la durée (tarif à la journée) | P1 |
| Fenêtre de censure | p95 des durées connues | 14, 30, 60 jours | s'adapte au service au lieu d'un nombre arbitraire | P2 |
| Convention des jours | série attendue (nuit incertaine = 1 − p) | tout inclusif, tout en nuits | espérance exacte, sans supposer une seule pratique | P3, `sensibilite.py` |
| Patients reportés | gardés | fusionnés | la fusion n'est sûre qu'une fois confirmée par le service | P4 |
| Début de la période | mois avec ≥ 90 % de durées connues, puis rodage | 80 %, 95 %, rodage au début | équilibre entre données gardées et biais de sous-comptage | P5 |
| Fin de série | p95 du délai d'inscription retiré | aucune coupe, 7 jours | les derniers jours manquent d'enfants pas encore inscrits | P6 |
| Trous de saisie | gardés | lignes d'apprentissage touchées exclues | à mesurer : un trou crée un faux creux que le modèle apprendrait | P7 |

### 9.3 Variables d'entrée (`benchmark_choix.py`)

| Décision | Retenu | Alternatives | Pourquoi | Banc |
|---|---|---|---|---|
| Groupes de variables | retards + flux + calendrier | retards seuls, + flux, + calendrier | l'occupation a de la mémoire (ACF), les flux la font bouger, la saison la module | D5 |
| Nombre de jours de retard | 7 | 3, 5, 10, 14, 21 | l'ACF et la PACF, et une admission pèse environ 3 à 7 jours | D5, sensibilité `variables` |
| Jours fériés, vacances | à garder seulement si gain | sans | connus à l'avance, mais rares : gain incertain | D5 |
| Chaque variable | toutes | toutes sauf une | vérifie qu'aucune variable ne nuit | D11 |
| Standardisation | oui, apprise sur l'entraînement | sans | le noyau RBF mesure des distances : sans elle, une variable à grande échelle écrase les autres | D6 |
| Fenêtre d'entraînement | tout le passé | 365, 180, 90 derniers jours | plus de saisons vues ; mesure aussi le coût d'un historique court | D7 |

### 9.4 Modèle

| Décision | Retenu | Alternatives | Pourquoi | Banc |
|---|---|---|---|---|
| Famille de modèle | SVR quantile à noyau composite | 10 références, ridge, forêt, boosting, perceptron, LSTM, SVR niveaux 1 à 3 | sujet du mémoire, à justifier par la comparaison | D1 |
| Noyau | composite (deux blocs, poids β appris) | linéaire, RBF | sépare l'information « occupation passée » de « flux et saison » | D2 |
| Fonction de coût | pinball (quantile) | carrée, ε-insensible ε = 0 à 2 | coûts asymétriques : manquer un lit coûte plus | D3 |
| Quantile τ | 0,8 | 0,5 à 0,9 | pénurie 4 fois plus coûteuse qu'un lit vide | D4, sensibilité de τ |
| Combinaison | empilement appris | meilleur modèle seul, moyenne simple | à justifier par le gain | D9 |

### 9.5 Minimisation et réglages

| Décision | Retenu | Alternatives | Pourquoi | Banc |
|---|---|---|---|---|
| Optimiseur | Adam | descente simple, momentum | un pas adapté à chaque paramètre ; robuste aux échelles différentes | D8, sensibilité `optimiseur` |
| Taux d'apprentissage η₀ | 0,05 | 0,005 à 0,2 | compromis vitesse / stabilité | sensibilité `taux` |
| Décroissance du pas | η₀/√(1 + t/500) | pas constant, T = 100 ou 2 000 | garantit la convergence d'une perte non dérivable partout | D8, sensibilité `decroissance` |
| Moyenne de Polyak | sur la seconde moitié | aucune, 25 %, 75 % | stabilise un minimum autour duquel on oscille | D8, sensibilité `moyenne_polyak` |
| Direction préconditionnée | oui | gradient brut | même minimum, atteint plus vite | D8, sensibilité `preconditionne` |
| Itérations, tolérance | 3 000, 10⁻⁷ | 300 à 6 000 ; 10⁻⁵ à 10⁻⁹ | assez pour converger sans calcul inutile | sensibilité `iterations`, `tolerance` |
| C, ε, γ, γ₁, γ₂ | choisis par grille | défaut, essaim particulaire | la grille est simple et reproductible | D10, sensibilité de chacun |
| Réglages des concurrents | valeurs usuelles de la littérature | grilles de la sensibilité | traités aussi équitablement que le SVR | sensibilité `foret`, `boosting`, `mlp`, `lstm` |

### 9.6 Validation et évaluation

| Décision | Retenu | Alternatives | Pourquoi | Vérifié par |
|---|---|---|---|---|
| Schéma de validation | glissante, réentraînement à chaque origine | découpage unique | reproduit l'usage réel, jour après jour | protocole |
| Période de validation | 6 mois avant le verrou | — | assez de jours pour le test de Diebold-Mariano, en gardant l'essentiel pour apprendre | protocole |
| Mesure principale | pinball à τ (et MAE pour la médiane) | MAE seule | la pinball juge ce que le modèle doit faire : un quantile | protocole |
| Test statistique | Diebold-Mariano avec correction HLN | comparer deux chiffres | distingue un vrai gain d'un écart dû au hasard | protocole |
| Sensibilité à la convention des jours | trois séries | une seule | les conclusions ne doivent pas dépendre d'une hypothèse invérifiable | `sensibilite.py` |
