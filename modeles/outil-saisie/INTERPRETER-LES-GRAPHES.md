# Interpréter tous les graphes

Ce guide explique comment lire **chaque graphe** de l'outil de saisie (onglet Indicateurs) et des scripts
Python (`modeles/resultats/`). Les nombres cités sont des **exemples fictifs** : ils montrent comment raisonner,
ils ne décrivent pas vos données. Chaque rubrique de l'outil garde aussi son encadré « Comment lire ».

Pour chaque graphe : **ce qu'il montre**, **comment le lire**, **ce qui doit alerter**, **un exemple fictif**.

---

## 0. Règles valables pour tous les graphes

**Les commandes communes**
- **Légende cliquable** : un clic sur un élément de légende masque la courbe, la bande ou les barres de cette
  couleur ; un second clic la réaffiche. Utile pour comparer deux courbes sans être gêné par les autres.
- **Jour · Semaine · Mois · Année** (au-dessus des graphes jour par jour) : chaque point devient la **moyenne**
  de la période. Le jour montre le bruit quotidien ; la semaine efface le rythme de la semaine ; le mois montre
  la saison ; l'année compare les années.
- **Zoom** (− / +, molette) et **déplacement** (‹ ›, glisser) : pour regarder une période précise (une
  épidémie, une fin d'année). **Tout** revient à toute la période.
- **Animation** : la courbe se construit jour après jour. Elle aide à voir dans quel ordre les choses arrivent
  (les admissions montent avant les présents, une saison se répète).
- **Survol** : la bulle donne la valeur exacte du jour (ou de la période) sous la souris.

**La méthode de comptage** (bouton Calcul → Comptage), rappelée en tête de chaque graphe de l'occupation :

| Méthode | Ce qu'elle mesure | Ce qu'elle oublie |
|---|---|---|
| Recensement de minuit | lits occupés la nuit (norme hospitalière) | les mises en observation, le jour de sortie |
| Présence dans la journée | enfants présents à un moment du jour | compte deux fois un lit libéré puis réoccupé le même jour |
| Pondérée par le temps | occupation moyenne réelle, avec des heures typiques | dépend des heures supposées |
| Toutes les méthodes | les trois l'une sous l'autre | — |

**Comment lire « toutes les méthodes »** : si les trois graphes racontent la même histoire (mêmes pics, même
saison), la conclusion est **robuste** ; si elles divergent, la conclusion dépend de la définition et il faut
l'écrire. En général : journée > minuit ≈ pondérée.

**Les bandes** (zones colorées) donnent une incertitude : plus elles sont larges, moins le chiffre est sûr.

**Une p-valeur < 0,05** dit qu'un effet est peu compatible avec le hasard, pas qu'il est important : regardez
toujours la taille de l'effet à côté.

---

## 1. Synthèse

**Votre saisie** — la période saisie, le nombre de lignes et ce que devient chaque ligne (sortie écrite,
calculée, estimée, encore hospitalisé). *À surveiller* : une part « estimée » élevée (plus de 20 %) rend
l'occupation moins sûre. *Exemple* : 1 200 lignes, 75 % de sorties écrites, 10 % calculées, 15 % estimées.

**Chiffres clés de l'occupation** — taux d'occupation (TOM), présents moyens, admissions par jour, durée
moyenne de séjour (DMS), journées, sureffectif, rotation, intervalle de rotation. *Lecture* : le TOM est la
part des lits occupés en moyenne ; la fourchette donne l'effet de la convention des jours. *Exemple* : TOM
58 % [54 – 62] avec 20 lits = 11,6 enfants en moyenne ; intervalle de rotation 2,1 jours = un lit reste vide
2 jours entre deux enfants. Un intervalle **négatif** signale un sureffectif.

**Patients et qualité des soins** — SCAM, référés, décès, transfusions, avec intervalle de confiance.
*Exemple* : SCAM 12 % [10 ; 14] : environ un enfant sur huit part contre avis.

---

## 2. Statistiques descriptives

**Variables numériques (patients, jours)** — moyenne, médiane, écart-type, quantiles, asymétrie. *Lecture* :
moyenne très au-dessus de la médiane = longue queue à droite (quelques valeurs très grandes). *Exemple* :
durée moyenne 3,4 nuits, médiane 3 : quelques longs séjours tirent la moyenne vers le haut.

**Distribution d'une variable** — histogramme, courbe normale, droite de Henry, boîte à moustaches.
*Lecture* : si les points de la droite de Henry quittent la diagonale en haut à droite, la queue droite est
plus lourde qu'une loi normale ; préférer alors la médiane et les tests sur les rangs. Les cercles de la boîte
sont des valeurs atypiques : **à vérifier sur la photo** (erreur de saisie ?).

**Variables qualitatives** — effectifs, pourcentages avec intervalle de Wilson. *Exemple* : paludisme 40 %
[37 ; 43] des admissions.

**Comparaison d'une variable entre groupes** — boîtes côte à côte et test (Mann-Whitney, Kruskal-Wallis).
*Lecture* : des boîtes qui se chevauchent largement = groupes semblables. *Exemple* : durée selon le sexe,
p = 0,6 : pas de différence.

---

## 3. Corrélations et tests

**Matrices de corrélation** — chaque case = force du lien entre deux variables (rouge : elles montent
ensemble ; bleu : l'une monte quand l'autre baisse). *Lecture* : |r| < 0,3 faible, 0,3 – 0,5 modéré, > 0,5
fort. *Exemple* : présents d'hier × présents d'aujourd'hui r = 0,9 : forte mémoire de la série.

**Toutes les paires classées** — la liste des liens du plus fort au plus faible, avec étoiles de
significativité.

**Nuage de points et droite de régression** — chaque point est un patient ou un jour. *Lecture* : nuage serré
autour de la droite = lien fort ; nuage en forme de courbe = lien non linéaire (argument pour le noyau RBF).

**Nuage en 3D, plan de régression en 3D** — même lecture avec trois variables ; tourner la vue aide à voir si
un plan suffit ou s'il faut une surface courbe.

**Khi-deux, V de Cramér, tableau croisé** — lien entre deux variables qualitatives. Les cases fortement
positives (résidu > 2) « font » le lien. *Exemple* : V = 0,15, sepsis sur-représenté parmi les référés.

**Tests de comparaison (tous les croisements)** — table de tous les tests ; ne retenir que les effets
significatifs **et** d'une taille notable.

**Régression linéaire multiple** — coefficients, intervalles, R², VIF, résidus. *Lecture* : un coefficient
dont l'intervalle ne contient pas 0 est significatif ; VIF > 5 = variables trop liées entre elles ; résidus en
entonnoir ou en courbe = modèle linéaire insuffisant.

**Jours fériés et vacances scolaires** — admissions un jour férié comparées à un jour ordinaire du même jour
de la semaine. *Exemple* : rapport 0,8 = 20 % d'admissions en moins un jour férié.

**Corrélation croisée admissions → présents** — combien de jours une admission pèse sur l'occupation.
*Exemple* : corrélation forte jusqu'à 3 jours de décalage = une admission occupe un lit environ 3 jours.

---

## 4. Analyse multivariée (ACP)

**Adéquation (KMO, Bartlett) et valeurs propres** — l'ACP n'a de sens que si Bartlett p < 0,05 et KMO ≥ 0,6.
**Éboulis** — garder les axes au-dessus du seuil de Horn. **Cercle des corrélations** — flèches longues et
proches = variables liées ; à angle droit = indépendantes. **Projection des patients** — patients proches =
profils semblables. **Contributions, cos²** — quelles variables « font » chaque axe. **Valeurs-test** — un
groupe à |v| > 1,96 est nettement d'un côté de l'axe. **Vue 3D** — mêmes lectures en trois axes ; ellipses
séparées = groupes différents. *Exemple* : axe 1 = « séjours lourds » (durée, prix, transfusion), les enfants
transfusés y sont nettement à droite (v = +6).

---

## 5. Occupation

**Taux d'occupation par période** — barres du TOM par mois (ou semaine, année) avec fourchette, repères 85 %
(tendu) et 100 % (plein). *À surveiller* : les mois au-dessus de 85 %. *Exemple* : décembre 84 % [80 – 88],
juin 38 %.

**Occupation moyenne et maximale par mois** — la moyenne dit le niveau habituel, le maximum le pire jour.
Un écart moyenne / maximum grand = des pics brefs.

**Répartition des jours selon le taux** — combien de jours le service est calme (< 50 %), normal, tendu
(> 85 %) ou en sureffectif (> 100 %).

**Occupation selon le jour de la semaine** — barres par jour avec intervalle. Barres de même hauteur = pas de
rythme hebdomadaire (le calendrier apportera peu au modèle).

**Pic de la journée** — bande bleu clair entre deux bornes exactes : en bas, le plus grand des deux minuits
qui encadrent la journée ; en haut, les enfants présents à un moment de la journée. Le vrai pic est dans la
bande. *Lecture* : c'est **le nombre de lits nécessaires au moment le plus chargé**. Jours où même la borne
basse dépasse les lits = sureffectif **certain** ; où seule la borne haute dépasse = sureffectif **possible**.
*Exemple* : pic moyen entre 10 et 12 enfants pour 8,5 présents à minuit : le service est plus chargé dans la
journée que la nuit.

**Loi de Little et Erlang B** — Little vérifie la cohérence (présents ≈ admissions par jour × durée) : écart
< 10 % = données cohérentes. Erlang B donne la probabilité de trouver tous les lits pris et le nombre de lits
pour rester sous 5 % ou 1 %. *Exemple* : charge moyenne 9 → 14 lits suffisent 95 % du temps, mais le mois le
plus chargé en demande 18.

**Bilan des flux** — l'occupation retracée comme un stock (hier + entrées − sorties). L'écart doit être 0 :
c'est un contrôle du calcul. Avec des comptages réels (cahier de garde), un écart toujours positif signale des
enfants présents mais absents du registre.

**Simulation de Monte-Carlo** — bande bleu clair = 90 % des simulations, violet = médiane, orange = calcul
principal. *Lecture* : bande étroite = les données manquantes changent peu le résultat (reconstitution
robuste). *Exemple* : TOM 55 % [54 ; 56].

**Analyse de survie (Kaplan-Meier)** — part des enfants encore hospitalisés après t nuits. *Lecture* : la
médiane est la durée où la courbe passe sous 50 % ; une courbe qui descend plus vite = séjours plus courts ;
log-rank p < 0,05 = groupes différents. *Exemple* : médiane 3 nuits ; les SCAM sortent plus vite.

**Modèle de file M/G/∞** — barres = répartition observée du nombre de présents ; courbes = loi de Poisson,
mélange mensuel, binomiale négative. *Lecture* : indice de dispersion > 1 = l'occupation varie plus que le
hasard (vagues) ; la loi qui colle aux barres donne la bonne probabilité de jours tendus.

---

## 6. Séries temporelles

**Courbe jour par jour** — présents chaque jour, moyennes mobiles, tendance, bande ± 2 écarts-types,
fourchette, capacité. *Lecture* : la moyenne mobile 7 jours enlève le bruit quotidien ; 30 jours montre la
saison ; un point hors de la bande ± 2 σ est un jour inhabituel. Passer en **mois** pour voir la saison, en
**jour** et zoomer pour regarder une épidémie.

**Admissions jour par jour** — chaque jour, le nombre d'admissions (bleu), avec moyennes mobiles 7 et 30
jours. *Lecture* : indice de dispersion proche de 1 = arrivées au hasard ; > 1 = jours de rush.

**Décomposition** — tendance (évolution lente), semaine (profil hebdomadaire), imprévus (reste). *Exemple* :
force de la tendance 0,6, de la semaine 0,05 : l'occupation suit surtout la saison, très peu le jour.

**ACF / PACF** — barres hors de la zone grise = mémoire significative. ACF qui décroît lentement + PACF avec un
seul pic = l'occupation d'aujourd'hui dépend surtout de celle d'hier (modèle AR(1)) ; pics à 7, 14, 21 =
rythme hebdomadaire.

**Volatilité** — écart-type mobile : les périodes où il monte sont plus difficiles à prévoir.

---

## 7. Modèles de prévision

**Série étudiée et tests de stationnarité** — ADF et KPSS se lisent ensemble : ADF rejette + KPSS ne rejette
pas = série stable ; les deux rejettent = niveau qui change lentement avec la saison.

**Tendance, saisonnalité et dispersion** — Mann-Kendall (tendance), Kruskal-Wallis par jour (semaine),
indice de dispersion.

**Périodogramme** — les pics au-dessus du seuil sont des cycles réels (7 jours = semaine, 365 = année).

**Comparaison des modèles** — table MAE, RMSE, MASE, biais sur la validation. *Lecture* : MASE < 1 = mieux
que la référence naïve ; le test de Diebold-Mariano dit si l'écart entre deux modèles est réel. *Exemple* :
AR(14) MAE 1,9 contre naïf 2,0, DM p = 0,11 : meilleur en moyenne, pas significativement.

**SARIMA et diagnostic des résidus** — les résidus doivent ressembler à du bruit (ACF dans la bande,
Ljung-Box p ≥ 0,05) ; sinon il reste de l'information non captée.

**Prévisions de tous les modèles** — courbes prolongées après la fin des données, avec intervalle à 95 %.
L'intervalle s'élargit avec l'horizon : c'est normal.

---

## 8. Flux et séjours, patients, tableaux

**Admissions et sorties par période** — si les admissions dépassent durablement les sorties, l'occupation
monte. **Durée des séjours** — histogramme des nuits : une longue queue = quelques séjours très longs.
**DMS par mois, par cause, par âge** — quelles périodes, maladies ou âges allongent les séjours.
**Âge et sexe, causes, issues, quartiers** — décrivent la population : à lire en pourcentage avec leur
intervalle. **Récapitulatif mensuel** — à comparer ligne à ligne avec le récapitulatif du registre papier :
un écart signale des lignes oubliées. **Indicateurs par période, par cause** — les mêmes chiffres que la
synthèse, mois par mois ou cause par cause.

---

## 9. Figures et tableaux produits par Python (`modeles/resultats/`)

| Fichier | Lecture |
|---|---|
| `occupation_PED.png` | occupation jour par jour, fourchette et capacité : même lecture que la courbe jour par jour |
| `01_serie_occupation` à `06_nuage_3d` | série, profils, ACF / PACF, corrélations, relations, nuage 3D : mêmes lectures que les sections 5 et 6 |
| `07_hyperplan_svr_3d` | le SVR linéaire : un plan et son tube ± ε ; seuls les points rouges (sur ou hors du tube, « vecteurs de support ») déterminent le plan |
| `08_surface_svr_rbf_3d` | le SVR à noyau RBF : surface courbe entre les quantiles 5 % et 95 % ; 9 points sur 10 doivent tomber entre les deux grilles |
| `09_convergence` | J pendant l'entraînement : doit descendre puis se stabiliser ; s'il oscille fort, le pas d'apprentissage est trop grand |
| `10_courbe_apprentissage` | erreurs d'entraînement et de validation selon la quantité d'historique : courbes qui se rejoignent = assez de données ; écart persistant = surapprentissage |
| `11_hyperparametres` | erreur selon C et γ : une large zone sombre = choix peu sensible (rassurant) |
| `12_previsions` | prévision, quantile τ, intervalle 90 %, réalité : la réalité doit rester dans la bande |
| `13_residus` | erreurs centrées sur 0 = pas de biais ; dérive dans le temps = réentraîner |
| `14_calibration` | couverture observée contre demandée : sur la diagonale = bien calibré ; en dessous = le modèle sous-estime les besoins |
| `15_ablation`, `16_sensibilite`, `17_importance_variables` | chaque niveau doit améliorer le précédent ; conclusions identiques quelle que soit la convention ; une barre proche de 0 = variable inutile |
| `parametres_PED_<famille>_<paramètre>.png` | erreur selon la valeur d'un paramètre, valeur retenue cerclée : courbe plate = paramètre peu important ; creux net ailleurs que sur la valeur retenue = réglage à revoir |
| `benchmark_PED.md`, `pretraitement_PED.md`, `parametres_PED.md` | colonne « vs choix retenu » : équivalent (choix défendable), moins bon (argument pour le choix), meilleur (**choix à revoir**) |
| `scenarios_lits_PED.csv` | taux, jours saturés, sureffectif pour 15 à 20 lits : présenter le taux comme une plage tant que la capacité n'est pas confirmée |
