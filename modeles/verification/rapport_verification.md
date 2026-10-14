# Rapport de vérification des calculs

Produit par `verification/verifier_calculs.py` sur des **données fictives** (registre inventé, séries simulées).
Les bibliothèques de référence ne servent qu'à juger : aucun calcul de l'outil ni des modèles ne les utilise.

**118 calculs justes sur 118**.

## A. Occupation : outil (JavaScript) = Python = force brute

| Calcul | Verdict | Détail |
|---|---|---|
| minuit : même période (2025-01-15 → 2025-09-30) | juste |  |
| minuit : présents (attendue) outil = Python = force brute | juste | écart max 6.9e-12 sur 259 jours |
| minuit : présents (basse) outil = Python = force brute | juste | écart max 0.0e+00 sur 259 jours |
| minuit : présents (haute) outil = Python = force brute | juste | écart max 0.0e+00 sur 259 jours |
| minuit : bornes du pic de la journée | juste |  |
| minuit : pic bas ≤ pic haut chaque jour | juste |  |
| minuit : admissions du jour | juste |  |
| minuit : capacité de chaque jour (15 puis 20 lits au 01/05/25) | juste |  |
| minuit : taux d'occupation = Σ présents ÷ Σ lits | juste | outil 52.7 %, Python 52.74 % |
| minuit : jours en sureffectif | juste | 4 jours |
| journee : même période (2025-01-15 → 2025-09-30) | juste |  |
| journee : présents (attendue) outil = Python = force brute | juste | écart max 5.3e-12 sur 259 jours |
| journee : présents (basse) outil = Python = force brute | juste | écart max 0.0e+00 sur 259 jours |
| journee : présents (haute) outil = Python = force brute | juste | écart max 0.0e+00 sur 259 jours |
| journee : bornes du pic de la journée | juste |  |
| journee : pic bas ≤ pic haut chaque jour | juste |  |
| journee : admissions du jour | juste |  |
| journee : capacité de chaque jour (15 puis 20 lits au 01/05/25) | juste |  |
| journee : taux d'occupation = Σ présents ÷ Σ lits | juste | outil 70.1 %, Python 70.11 % |
| journee : jours en sureffectif | juste | 16 jours |
| pondere : même période (2025-01-15 → 2025-09-30) | juste |  |
| pondere : présents (attendue) outil = Python = force brute | juste | écart max 2.0e-11 sur 259 jours |
| pondere : présents (basse) outil = Python = force brute | juste | écart max 0.0e+00 sur 259 jours |
| pondere : présents (haute) outil = Python = force brute | juste | écart max 0.0e+00 sur 259 jours |
| pondere : bornes du pic de la journée | juste |  |
| pondere : pic bas ≤ pic haut chaque jour | juste |  |
| pondere : admissions du jour | juste |  |
| pondere : capacité de chaque jour (15 puis 20 lits au 01/05/25) | juste |  |
| pondere : taux d'occupation = Σ présents ÷ Σ lits | juste | outil 56.9 %, Python 56.92 % |
| pondere : jours en sureffectif | juste | 4 jours |
| minuit ≤ journée et pondérée ≤ journée, chaque jour | juste |  |

## B. Bibliothèque statistique de l'outil contre scipy, statsmodels, numpy

| Calcul | Verdict | Détail |
|---|---|---|
| lnGamma(0.3) | juste | outil 1.095797995, référence 1.095797995 |
| lnGamma(1.0) | juste | outil -8.881784197e-16, référence 0 |
| lnGamma(4.5) | juste | outil 2.453736571, référence 2.453736571 |
| lnGamma(37.2) | juste | outil 96.43971016, référence 96.43971016 |
| gammaP(0.5, 0.2) | juste | outil 0.4729107431, référence 0.4729107431 |
| gammaP(3, 2.5) | juste | outil 0.4561868841, référence 0.4561868841 |
| gammaP(10, 14.1) | juste | outil 0.8952511506, référence 0.8952511506 |
| betaI(2, 3, 0.4) | juste | outil 0.5248, référence 0.5248 |
| betaI(0.5, 7, 0.1) | juste | outil 0.7672211675, référence 0.7672211675 |
| betaI(15, 4, 0.8) | juste | outil 0.5010254585, référence 0.5010254585 |
| phi(-3.1) | juste | outil 0.0009676032132, référence 0.0009676032132 |
| phi(-1) | juste | outil 0.1586552539, référence 0.1586552539 |
| phi(0) | juste | outil 0.5, référence 0.5 |
| phi(0.5) | juste | outil 0.6914624613, référence 0.6914624613 |
| phi(1.96) | juste | outil 0.9750021049, référence 0.9750021049 |
| phi(4) | juste | outil 0.9999683288, référence 0.9999683288 |
| qnorm(0.001) | juste | outil -3.090232305, référence -3.090232306 |
| qnorm(0.025) | juste | outil -1.959963986, référence -1.959963985 |
| qnorm(0.3) | juste | outil -0.5244005133, référence -0.5244005127 |
| qnorm(0.5) | juste | outil 0, référence 0 |
| qnorm(0.9) | juste | outil 1.281551564, référence 1.281551566 |
| qnorm(0.999) | juste | outil 3.090232305, référence 3.090232306 |
| pStudentBilat(2.1, 5) | juste | outil 0.08975324988, référence 0.08975324988 |
| pStudentBilat(-1.3, 30) | juste | outil 0.2035009585, référence 0.2035009585 |
| pStudentBilat(4.2, 118.5) | juste | outil 5.194135803e-05, référence 5.194135803e-05 |
| tCritique(3) | juste | outil 3.182446305, référence 3.182446305 |
| tCritique(12) | juste | outil 2.17881283, référence 2.17881283 |
| tCritique(119) | juste | outil 1.980099876, référence 1.980099876 |
| pKhi2(3.2, 1) | juste | outil 0.07363827012, référence 0.07363827012 |
| pKhi2(11.07, 5) | juste | outil 0.05000961862, référence 0.05000961862 |
| pKhi2(40, 30) | juste | outil 0.1048642811, référence 0.1048642811 |
| pFisher(2.5, 3, 40) | juste | outil 0.07325435202, référence 0.07325435202 |
| pFisher(1.1, 10, 200) | juste | outil 0.3637601595, référence 0.3637601595 |
| pFisher(6, 1, 12) | juste | outil 0.03062177025, référence 0.03062177025 |
| intervalle de Wilson 37/140 (z exact) | juste | [0.1982 ; 0.3429] |
| intervalle de Wilson avec z = 1,96 (réglage de l'outil) | juste | [0.19824 ; 0.34292] |
| descriptif : moyenne | juste | 4.00911 / 4.00911 |
| descriptif : mediane | juste | 3.77978 / 3.77978 |
| descriptif : variance | juste | 5.38437 / 5.38437 |
| descriptif : ecart | juste | 2.32043 / 2.32043 |
| descriptif : asymetrie | juste | 0.640568 / 0.640568 |
| descriptif : aplatissement | juste | -0.0165559 / -0.0165559 |
| descriptif : q1 | juste | 2.30529 / 2.30529 |
| descriptif : q3 | juste | 5.27173 / 5.27173 |
| descriptif : p5 | juste | 0.748097 / 0.748097 |
| descriptif : p95 | juste | 8.70095 / 8.70095 |
| descriptif : jb | juste | 8.02339 / 8.02339 |
| descriptif : pJb | juste | 0.0181027 / 0.0181027 |
| descriptif : icBas | juste | 3.58967 / 3.58967 |
| descriptif : icHaut | juste | 4.42854 / 4.42854 |
| descriptif : mad | juste | 1.48071 / 1.48071 |
| Pearson r et p | juste |  |
| Spearman ρ et p | juste |  |
| Kendall τ-b et p (asymptotique) | juste |  |
| khi-deux, p et V de Cramér | juste |  |
| t de Welch et p | juste |  |
| ANOVA F et p | juste |  |
| Kruskal-Wallis H et p (sans ex æquo) | juste |  |
| Mann-Whitney U et p | juste |  |
| régression : coefficients | juste |  |
| régression : erreurs-types | juste |  |
| régression : p-valeurs | juste |  |
| régression : R², R² ajusté, F, p(F) | juste |  |
| valeurs propres (Jacobi) | juste |  |
| ACP : valeurs propres, Bartlett, KMO | juste |  |
| ACP : coordonnées des individus | juste |  |
| ACF | juste |  |
| PACF (Durbin-Levinson) | juste |  |
| Ljung-Box Q et p | juste |  |
| ADF (statistique, 7 retards) | juste |  |
| KPSS (statistique) | juste |  |
| périodogramme | juste |  |
| MAE, RMSE, MAPE, sMAPE, MASE, biais | juste |  |
| Diebold-Mariano (Harvey-Leybourne-Newbold) | juste |  |
| lissage exponentiel : α minimise la somme des carrés | juste | α outil 0.0299, recherche exhaustive 0.030 |
| AR(2) : coefficients des moindres carrés | juste |  |
| AR : ordre choisi = vrai ordre (2) ou voisin | juste | ordre 2 |
| ARMA(1,1) par CSS : minimum atteint (Nelder-Mead contre grille) | juste | CSS outil 312.399, meilleure grille 312.433 |

## C. Cas calculés à la main

| Calcul | Verdict | Détail |
|---|---|---|
| séjour de 3 nuits, minuit | juste | attendu [1, 1, 1, 0] |
| séjour de 3 nuits, journee | juste | attendu [1, 1, 1, 1] |
| séjour de 3 nuits, pondere | juste | attendu [0.625, 1, 1, 0.625] |
| séjour du même jour, minuit | juste | attendu 0 |
| séjour du même jour, journee | juste | attendu 1 |
| séjour du même jour, pondere | juste | attendu 0.25 |
| sortie calculée ambiguë (p = 0,4), minuit | juste | attendu [1, 0.6, 0] |
| sortie calculée ambiguë (p = 0,4), journee | juste | attendu [1, 1, 0.6] |
| Wilson 0 sur 10 = [0 ; 0,2775] | juste |  |
