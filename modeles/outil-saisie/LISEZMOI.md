# Outil de saisie des registres hospitaliers

*Première brique du modèle : c'est ici que les registres papier deviennent des données.*

L'outil de saisie est une **page web autonome** (`saisie.html`). On l'ouvre dans un navigateur, on affiche
à côté la photo d'une page du registre, et on recopie les lignes dans un formulaire. Il produit le **CSV**
que l'application NERA importe, puis que les modèles Python (dossier parent `modeles/`) analysent.

Pendant la saisie, il calcule aussi **toutes les statistiques** des lignes déjà saisies : occupation des lits,
statistiques descriptives, corrélations et tests, séries temporelles, modèles de prévision (Holt-Winters,
SARIMA…). Elles se mettent à jour à chaque ligne enregistrée.

- **Rien à installer** : HTML + JavaScript, aucune bibliothèque, aucun serveur obligatoire.
- **Rien ne sort de l'ordinateur** : les lignes restent dans le navigateur ; seuls les fichiers que vous
  exportez existent ailleurs.
- **Toutes les statistiques sont codées à la main** (`statistiques.js`), comme les modèles Python du mémoire :
  lois de probabilité, tests, régression, ARIMA/SARIMA, optimiseur de Nelder-Mead.
- **Aucune donnée identifiante** : le nom, le prénom, le téléphone, le médecin et la facture ne sont jamais
  recopiés (ces colonnes n'existent pas dans le formulaire).

---

Pour lire **chaque graphe** (ce qu'il montre, ce qui doit alerter, exemples fictifs) : [`INTERPRETER-LES-GRAPHES.md`](INTERPRETER-LES-GRAPHES.md).

## Sommaire

1. [Place dans le projet](#1-place-dans-le-projet)
2. [Lancer l'outil](#2-lancer-loutil)
3. [Préparer les photos](#3-préparer-les-photos)
4. [Onglet 1 · Saisie](#4-onglet-1--saisie)
5. [Onglet 2 · Contrôle qualité](#5-onglet-2--contrôle-qualité)
6. [Onglet 3 · Indicateurs et statistiques](#6-onglet-3--indicateurs-et-statistiques)
7. [Comment les calculs sont faits](#7-comment-les-calculs-sont-faits)
8. [Sauvegarder, exporter, restaurer](#8-sauvegarder-exporter-restaurer)
9. [Confidentialité et données](#9-confidentialité-et-données)
10. [Ajouter un service ou modifier un registre](#10-ajouter-un-service-ou-modifier-un-registre)
11. [Fichier par fichier](#11-fichier-par-fichier)
12. [Problèmes fréquents](#12-problèmes-fréquents)

---

## 1. Place dans le projet

```
Registre papier (photos)
   │  convertir_photos.bat         photos HEIC/JPEG → JPEG propres, sans métadonnées
   ▼
saisie.html  ── onglet 1 ──►  lignes du registre (gardées dans le navigateur)
   │            onglet 2 ──►  taux d'erreur de saisie (contrôle qualité, pour le mémoire)
   │            onglet 3 ──►  indicateurs et statistiques, mis à jour à chaque ligne
   │
   ├── Sauvegarde complète (.json) ──► copie de sécurité, restaurable en un clic
   └── Export CSV (un fichier par service)
          │
          ▼
   Application NERA (import) ──► base PostgreSQL ──► export « dataset harmonisé »
          │
          ▼
   modeles/donnees/<export>.csv ──► rapport_occupation.py, lancer_niveaux.py, … (voir ../README.md)
```

Les calculs d'occupation de l'onglet 3 sont **les mêmes** que ceux de `nera/occupation.py` et de l'application
NERA (même recensement de minuit, même convention des jours, même fourchette). Ils ont été comparés sur les
mêmes lignes : **écart nul**. L'outil sert donc aussi de contrôle immédiat de ce que donneront les modèles.

Pour vérifier une double saisie (deux personnes saisissent les mêmes photos), voir `qualite_saisie.py` dans
`../README.md`.

---

## 2. Lancer l'outil

### Prérequis

- Un navigateur récent : **Chrome, Edge** (recommandés) ou Firefox.
- C'est tout. La police d'écriture (Plus Jakarta Sans) est chargée depuis Google Fonts si Internet est
  disponible ; sans Internet, l'outil fonctionne avec la police du système.

### Méthode A — double-clic (la plus simple)

Ouvrir `saisie.html` par un double-clic. L'adresse commence par `file:///…/outil-saisie/saisie.html`.

### Méthode B — petit serveur local

Depuis ce dossier :

```bash
python -m http.server 8765
```

puis ouvrir `http://localhost:8765/saisie.html`.

> **Important :** le navigateur range les lignes **par adresse**. Les lignes saisies avec la méthode A ne
> sont pas visibles avec la méthode B (et inversement), ni dans un autre navigateur. Pour passer de l'un à
> l'autre : **Sauvegarde → Télécharger la sauvegarde complète**, puis **Restaurer** de l'autre côté
> (§ 8). Choisissez une méthode et gardez-la.

### Première ouverture

La fenêtre **« Comment ça marche ? »** s'ouvre (on la retrouve avec le bouton **?** en haut à droite).
Choisir le **service** dans la liste en haut : le formulaire affiche les colonnes du registre de ce service.

---

## 3. Préparer les photos

Les téléphones produisent souvent des photos **HEIC**, que les navigateurs n'affichent pas, et toutes les
photos contiennent des métadonnées (position GPS, date, modèle du téléphone).

Double-cliquer sur **`convertir_photos.bat`**, puis indiquer :
1. le dossier des photos originales (par exemple `C:\Registres\pediatrie`) ;
2. le dossier de sortie (par exemple `photos_pediatrie`).

Le script (`convertir_photos.ps1`) utilise le décodeur intégré à Windows (rien à installer) : il convertit
en JPEG, réduit à 2600 pixels de côté au plus, **supprime les métadonnées** et **ne touche jamais aux
originaux**. Une photo prise de travers se redresse ensuite dans l'outil (boutons ⟲ ⟳).

Les dossiers `photos*/` sont ignorés par git : **les photos ne sont jamais envoyées sur GitHub.**

---

## 4. Onglet 1 · Saisie

L'écran a trois colonnes : la **liste des photos** (avec leur numéro et le nombre de lignes déjà saisies),
la **photo** (molette : zoom, glisser : déplacer, boutons : pivoter, contraste, photo suivante) et le
**formulaire**.

1. **Ouvrir les photos** (bouton en haut) : sélectionner toutes les photos converties du service.
2. Pour chaque ligne de la page, remplir le formulaire et **enregistrer** (`Ctrl` + `Entrée`).
   Le N° d'ordre suivant se remplit tout seul.
3. Les lignes de la photo affichée apparaissent dans le tableau sous le formulaire : un clic sur une ligne
   la rouvre pour la corriger, la corbeille la supprime.

### Règles de recopie

| Situation dans le registre | Ce qu'on tape |
|---|---|
| Texte écrit | Exactement ce qui est écrit (« APG » reste « APG ») |
| Case illisible | `?` |
| Case vide | rien |
| Même date que la date d'enregistrement | `=` |
| Jour seul (« 5 ») | `5` → complété avec le mois et l'année de la date d'enregistrement |
| Date | `010724`, `1/7/24` ou `01/07/2024` → mis en forme `01/07/24` ; date impossible ou future signalée |
| Date de sortie non écrite | rien : elle est calculée (entrée + nombre de jours), voir § 7 |

### Raccourcis

| Touche | Effet |
|---|---|
| `Entrée` | champ suivant (saute les champs « gardés » et recopiés) |
| `Ctrl` + `Entrée` | enregistrer la ligne |
| `Ctrl` + `D` | recopier la ligne précédente |
| `Alt` + `1` … `9` | ajouter le terme rapide n° 1 à 9 de la case (APG, Artesun inj, NFS…) |
| `Échap` | nouvelle ligne |

- **Garder** (à côté d'un champ) : la valeur est reprise sur les lignes suivantes, par exemple la date
  pour toute une page. Un bandeau bleu rappelle les valeurs gardées.
- **Termes rapides** : boutons sous les cases (diagnostics, examens, traitements…). Leur signification
  s'affiche au survol et dans le lexique de l'aide (`ABREVIATIONS` dans `registres.js`).
- **Aperçu** (en haut) : toutes les lignes saisies, telles qu'elles seront exportées, avec recherche ;
  les cases marquées `?` sont en jaune.

---

## 5. Onglet 2 · Contrôle qualité

Recopier des centaines de lignes à la main entraîne forcément quelques erreurs. Ce contrôle **mesure** le
taux d'erreur, chiffre à mettre dans le mémoire.

Le contrôle se fait **page par page**, car les lignes transcrites depuis les CSV ne savent pas de quelle photo
elles viennent : c'est la photo qu'on tire au hasard, et c'est elle qui retrouve ses lignes.

1. **Ouvrir les photos** du registre (JPEG ; convertir les HEIC avec `convertir_photos.bat`).
2. Choisir le nombre de pages (20 par défaut, environ 300 lignes) et **Tirer au hasard**. On peut aussi
   ajouter une page précise.
3. Pour chaque page, la photo s'affiche à gauche. Choisir le **mois** et taper le **premier N° d'ordre** écrit
   sur la photo (la numérotation repart à 1 chaque mois) : le dernier N° se remplit seul (premier + 14, une
   page ayant au plus 15 lignes), à corriger si la page en a moins. Les lignes saisies correspondantes
   s'affichent à droite, dans l'ordre du registre ; les N° absents de la saisie sont signalés, les doublons
   (même N° deux fois) surlignés. Il n'est pas nécessaire que la photo ait été rattachée à ses lignes lors de
   la saisie (cas des lignes transcrites et importées en CSV) : c'est ce qu'on lit sur la photo qui les retrouve.
   - Une photo identifiée l'est pour de bon (gardé dans la sauvegarde) : elle n'est plus à identifier lors
     d'un contrôle suivant.
   - Les photos étant nommées dans l'ordre de prise de vue, une photo voisine d'une photo déjà identifiée est
     **proposée** automatiquement (même mois, N° suivants), avec un rappel de vérifier sur la photo.
4. **Cliquer chaque case différente de la photo** (elle devient rouge). Compter avec + / − les lignes de la
   photo **oubliées** dans la saisie et les lignes saisies **en trop**.
5. **Page vérifiée, suivante** (ou **Passer cette page** si elle est illisible ou d'un autre registre). Une page
   vérifiée rattache sa photo aux lignes qui n'en avaient pas : l'onglet Saisie l'affiche ensuite.
6. **Voir les résultats** :
   - taux d'erreur global = cases fausses ÷ cases vérifiées, avec un intervalle de confiance à 95 % par
     **bootstrap sur les pages** (2 000 tirages avec remise, à partir de 5 pages) : la page est l'unité tirée
     au hasard, et les erreurs d'une même page se ressemblent ;
   - taux d'erreur sur les **colonnes de l'occupation** (dates, nombre de jours, issue, prix) : ce sont elles qui
     comptent pour le mémoire ;
   - part des lignes avec au moins une erreur, lignes oubliées et en trop ;
   - taux par colonne avec un **intervalle de Wilson** ; plus de 5 % : colonne à revérifier en entier ;
   - estimation du nombre de cases fausses sur toute la saisie ;
   - **liste des erreurs** avec un bouton **Corriger** qui ouvre la ligne dans l'onglet Saisie ;
   - une **phrase prête pour le mémoire** et l'export CSV (résumé, colonnes, détail des erreurs).

Repères : moins de 1 % de cases fausses, très bonne qualité ; moins de 2 %, bonne ; 2 à 5 %, acceptable ;
au-delà, la saisie est à reprendre. Le contrôle se fait en plusieurs séances : tout est gardé dans la sauvegarde.

---

## 6. Onglet 3 · Indicateurs et statistiques

### Disposition

```
┌────────────────────┬──────────────────────────────────────────────────────────────────────────┐
│ Barre latérale     │ Titre de la rubrique   Statistique ‹ [menu ▾] ›   Lits [25]   Mois|Année │
│  · rubriques       ├──────────────────────────────────────────────────────────────────────────┤
│  · état de la mise │  Statistique : options · chiffres clés · graphique · « Comment lire »   │
│    à jour          │  (bouton « Agrandir » sur chaque statistique)                            │
└────────────────────┴──────────────────────────────────────────────────────────────────────────┘
```

- **Barre latérale** : les rubriques. En haut, le nombre de lignes et l'heure du dernier calcul
  (« +3 depuis la dernière fois »).
- **Filtre « Statistique »** (en haut) : « Toutes » (les statistiques de la rubrique les unes sous les autres)
  ou une seule ; flèches ‹ › pour passer à la précédente ou à la suivante.
- **Lits du service** : nécessaire pour le taux d'occupation. **Par mois / Par année** : regroupement des
  tableaux et des barres.
- **Agrandir** : la statistique en grand, avec ses options, et ‹ Précédente / Suivante › (flèches du
  clavier ; `Échap` pour fermer).
- **Survol** : la souris sur une courbe montre la date et toutes les valeurs du jour ; sur une barre, une
  case, un point ou une boîte, la valeur exacte.
- **Navigation dans le temps** (graphes jour par jour, comme une application de cours de bourse) :
  **Jour · Semaine · Mois · Année** (chaque point devient la moyenne de la période) ; **−** / **+** ou la
  molette pour dézoomer ou zoomer à l'endroit pointé ; **‹ ›** ou glisser pour se déplacer ; **Tout** pour
  revenir à toute la période ; **Animation** fait avancer les courbes dans le temps (Pause pour arrêter). La vue
  est gardée pour chaque rubrique et s'applique aux trois méthodes.
- **Légende cliquable** : un clic sur un élément de légende masque la courbe, la bande ou les barres
  correspondantes ; un second clic les réaffiche. Le choix est gardé, même après un zoom ou un recalcul.
- **Comment lire** : chaque statistique a son explication (case à cocher en bas de la barre latérale pour
  les masquer).
- **Mise à jour automatique** : tout est recalculé quand une ligne est enregistrée, importée, corrigée ou
  supprimée.

### Les rubriques

| Rubrique | Contenu |
|---|---|
| **Synthèse** | Votre saisie (période, lignes, statuts des séjours, répartition des lignes) ; chiffres clés de l'occupation (TOM et fourchette, présents, admissions, DMS, journées, sureffectif, rotation, intervalle de rotation) ; patients et qualité des soins (décès, SCAM, référés, MEO, transfusions, âge médian, moins de 5 ans, sexe) |
| **Statistiques descriptives** | Pour chaque variable numérique (patients et jours) : n, manquants, moyenne et IC 95 %, médiane, mode, écart-type, variance, erreur-type, CV, min, P5, P10, Q1, Q3, P90, P95, max, étendue, IQR, MAD, asymétrie, aplatissement, Jarque-Bera, valeurs atypiques, somme · histogramme + loi normale, droite de Henry, boîte à moustaches · variables qualitatives (effectifs, %, IC de Wilson, entropie) · comparaison entre groupes (tableau, Kruskal-Wallis, ANOVA, Mann-Whitney, Welch, tailles d'effet, boîtes) |
| **Corrélations et tests** | Matrices Pearson / Spearman / Kendall avec étoiles de significativité · toutes les paires classées par force · nuage de points et droite de régression · khi-deux et V de Cramér · tableau croisé avec résidus · tests de groupes sur tous les croisements · régression linéaire multiple (observé / prédit, résidus, coefficients standardisés, IC, VIF) · corrélation croisée admissions → présents |
| **Analyse multivariée (ACP)** | ACP normée écrite à la main (Jacobi) sur les patients complets, log(1 + x) pour les variables très asymétriques · KMO et MSA, test de Bartlett · valeurs propres, analyse parallèle de Horn, bâton brisé · cercle des corrélations (variables supplémentaires en pointillés) · projection des patients colorée par une variable qualitative, barycentres et ellipses de confiance à 95 % · cos², contributions · valeurs-test des modalités · interprétation automatique des axes |
| **Calendrier camerounais** | Jours fériés (fêtes fixes, Vendredi saint et Ascension calculés depuis Pâques, Aïd el-Fitr et Tabaski d'après la Commission nationale du croissant lunaire) et vacances scolaires (arrêtés MINEDUB/MINESEC) : traits rouges et fond vert sur les courbes, variables « férié » et « vacances » dans les corrélations et la régression, section « Jours fériés et vacances scolaires : effet sur les admissions » (Mann-Whitney, observé ÷ attendu à jour de semaine égal, écart vacances − classe à mois égal) |
| **Occupation** | TOM par période et sa fourchette · occupation moyenne et maximale · jours par niveau de remplissage · jour de la semaine · loi de Little et Erlang B · bilan des flux (recalage sur comptages réels) · simulation de Monte-Carlo · survie (Kaplan-Meier, log-rank) · file M/G/∞ (Poisson, mélange mensuel, binomiale négative) |
| **Séries temporelles** | Courbe jour par jour (moyennes et médiane mobiles, tendance, bande ± 2 σ, min–max, fourchette, capacité) · admissions · décomposition tendance / semaine / résidu · ACF · PACF · volatilité |
| **Modèles de prévision** | Tests de stationnarité (ADF, KPSS, Ljung-Box) · tendance, saisonnalité, dispersion (Mann-Kendall, forces, Kruskal-Wallis, indice de dispersion) · périodogramme · comparaison de 9 modèles sur une validation · SARIMA (ordres réglables ou recherche automatique, prévision et intervalle à 95 %) · diagnostic des résidus · prévisions de tous les modèles |
| **Flux et séjours** | Admissions et sorties · durées de séjour · DMS par mois, par cause, par tranche d'âge |
| **Patients** | Âge et sexe · causes · issues · jour d'admission · quartiers · durée de séjour selon l'âge · transfusions |
| **Tableaux** | Récapitulatif mensuel (à comparer à celui du registre) · indicateurs par période · indicateurs par cause |

Les rubriques marquées « occupation » restent grisées tant que la saisie ne couvre pas assez de jours
(voir § 7). Les statistiques sur les patients sont disponibles dès les premières lignes.

> Les modèles de prévision de l'onglet 3 sont **exploratoires** : ils servent de références et à
> comprendre la série. Le modèle du mémoire est le SVR des scripts Python, comparé à ces références.

---

## 7. Comment les calculs sont faits

### Saisie progressive

Le registre est saisi page après page. Tous les calculs portent **uniquement sur la période saisie**, du
premier au dernier jour d'enregistrement présent dans vos lignes, jamais jusqu'à aujourd'hui : au-delà du
dernier jour saisi, on ne sait rien.

### Les quatre statuts d'un séjour

| Statut | Signification | Utilisé pour |
|---|---|---|
| sortie **écrite** | la date de sortie figure dans le registre | occupation, durées |
| sortie **calculée** | pas de date de sortie, mais un nombre de jours : sortie = entrée + nombre de jours | occupation, durées |
| **encore hospitalisé** | entré dans les 30 derniers jours saisis, sans sortie connue | occupation (jusqu'à la fin) |
| durée **inconnue** | ni sortie ni nombre de jours | exclu de l'occupation |

### Rodage

Les enfants entrés **avant** le début de la saisie occupent des lits mais n'ont pas de ligne. Le calcul
commence donc après un **rodage** de `max(14 jours, 95e percentile des durées)`, compté depuis le premier
mois où au moins 90 % des durées sont connues. C'est pourquoi les statistiques de durée (DMS, histogramme)
ne comptent que les séjours **terminés pendant la période de calcul** : un encadré de la synthèse détaille
où va chaque ligne.

### Occupation : trois méthodes de comptage

Bouton **Calcul** → **Comptage** :

| Méthode | Un enfant compte le jour d | Séjour de 3 nuits | Mise en observation |
|---|---|---|---|
| **Recensement de minuit** (défaut, norme hospitalière) | 1 si entrée ≤ d < sortie | 3 jours | 0 |
| **Présence dans la journée** | 1 si entrée ≤ d ≤ sortie | 4 jours | 1 |
| **Pondérée par le temps** | la part du jour passée dans le service : 1 − h_e/24 le jour d'entrée, 1 les jours pleins, h_s/24 le jour de sortie | 3 + (h_s − h_e)/24 | m/24 |
| **Toutes les méthodes** | les trois graphes l'un sous l'autre, dans chaque rubrique qui en dépend | | |

Heures typiques de la méthode pondérée (même bouton) : entrée 12 h, sortie 11 h, séjour du même jour 8 h, à
confirmer avec le major. Les rubriques qui ne dépendent pas de la méthode (admissions, flux, durées) ne sont
dessinées qu'une fois.

**Pic de la journée** (rubrique Occupation) : le plus grand nombre d'enfants présents en même temps est encadré
exactement, sans hypothèse d'heure, entre le plus grand des deux minuits qui encadrent la journée et le comptage
de la journée.

**Capacité variable** : « Lits du service » est la capacité de départ ; « Changements » ajoute les
changements de capacité, un par ligne ou séparés par « ; » (`01/03/25=20`). Taux, sureffectif, rotation et
intervalle de rotation utilisent les lits de chaque jour.

Le comptage journalier ajoute environ une journée par séjour : le taux d'occupation augmente d'environ
« admissions par jour ÷ lits ». Tous les calculs suivent la méthode choisie (journées, taux, loi de Little
avec W + 1 jour, bilan des flux, Monte-Carlo, file M/G/∞).

Limites : le recensement de minuit ignore les mises en observation et le jour de sortie (sous-estime
l'occupation de jour) ; le comptage journalier compte deux fois un lit libéré le matin et réoccupé
l'après-midi (peut surestimer le nombre de lits occupés en même temps). Sans heure d'entrée ni de sortie dans
le registre, la vérité se situe entre les deux. Le mémoire doit dire laquelle est retenue et pourquoi.

### Occupation : recensement de minuit et fourchette

Chaque soir, on compte les patients présents (entrés avant ou ce jour-là, pas encore sortis). Pour une
sortie calculée, on ne sait pas si le « nombre de jours » du registre compte les nuits ou inclut le jour de
sortie : la dernière nuit est comptée avec la probabilité `1 − p`, où `p` est la part de lignes
« inclusives » mesurée sur les lignes qui ont **à la fois** une date de sortie et un nombre de jours
(lissée par mois : `p_M = (k_M + 10·p̂) / (n_M + 10)`). La **fourchette basse / haute** correspond à
`p = 1` et `p = 0`.

| Indicateur | Formule |
|---|---|
| Journées d'hospitalisation | Σ présents à minuit |
| TOM (taux d'occupation moyen) | journées ÷ (lits × jours) |
| DMS (durée moyenne de séjour) | nuits moyennes des séjours terminés |
| Rotation | sorties ÷ lits |
| Intervalle de rotation | (lits × jours − journées) ÷ sorties |
| Mortalité | décès ÷ sorties |

### Statistiques et modèles (`statistiques.js`)

Tout est écrit à la main, avec la formule en commentaire :

- **Lois** : ln Γ (Lanczos), gamma et bêta incomplètes régularisées (séries et fractions continues de Lentz),
  d'où les p-valeurs exactes des lois normale, de Student, du khi-deux et de Fisher ; Φ⁻¹ (Acklam).
- **Descriptif** : quantiles de type 7 (comme R et pandas), asymétrie G1 et aplatissement G2 corrigés,
  Jarque-Bera, IC de la moyenne par Student, IC de Wilson pour les proportions.
- **Tests** : Pearson (test t), Spearman (rangs, ex æquo au rang moyen), Kendall τ-b, khi-deux et V de
  Cramér, ANOVA, Kruskal-Wallis, Mann-Whitney, t de Welch, régression multiple par moindres carrés
  (`β = (XᵀX)⁻¹Xᵀy`, inversion de Gauss-Jordan), VIF. Une corrélation n'est calculée que si au moins
  8 patients ont les deux valeurs (et au moins 3 « oui » et 3 « non » pour une variable 0/1).
- **Séries** : ACF, PACF (Durbin-Levinson), Ljung-Box, ADF (valeurs critiques de MacKinnon), KPSS
  (Newey-West), périodogramme, corrélation croisée, forces de tendance et de saisonnalité.
- **Modèles** : naïf, saisonnier naïf, moyenne, moyenne mobile, lissage exponentiel simple, Holt amorti,
  Holt-Winters additif, AR(p) choisi par AIC, ARIMA / SARIMA(p,d,q)(P,D,Q)₇ estimé par somme
  conditionnelle des carrés minimisée par **Nelder-Mead**, intervalles par les poids ψ.
- **Évaluation honnête** : chaque modèle est estimé sur les premiers jours, puis prévoit chaque soir le
  lendemain sur les derniers jours (15, 20 ou 30 %) jamais vus à l'estimation ; MAE, RMSE, MAPE, sMAPE,
  MASE, biais, AIC/BIC et test de **Diebold-Mariano** (correction de Harvey-Leybourne-Newbold).

### Période de test final (coffre-fort)

`CONFIG_SAISIE.dateVerrou` (dans `registres.js`, `2026-09-01`) : les lignes datées à partir de cette date
ne sont **jamais** comptées dans les indicateurs, comme dans les scripts Python (voir le « coffre-fort »
dans `../README.md`).

---

## 8. Sauvegarder, exporter, restaurer

Tout se fait avec le bouton **Sauvegarde** (en haut). Une **pastille orange** sur le bouton signale des
lignes pas encore sauvegardées.

### Sauvegarde complète (`.json`) — à faire à la fin de chaque séance

Un seul fichier avec **toutes** les lignes de **tous** les services et tout le contexte : nombre de lits,
champs gardés, contrôles qualité, réglages des indicateurs. Le fichier contient aussi une **empreinte**
(FNV-1a sur 32 bits) des lignes : à la restauration, l'outil vérifie que le fichier est intact.

```json
{ "format": "nera-saisie-sauvegarde", "version": 1, "creee": "…",
  "resume": { "PED": { "n": 269, "du": "2024-10-01", "au": "2024-12-16" } },
  "empreinte": "…", "etat": { "lignes": [ … ], "lits": { … }, … } }
```

### Restaurer

**Sauvegarde → Choisir une sauvegarde (.json)** : l'outil affiche son contenu (lignes par service, dates)
et propose (aucune information sur les photos n'y figure) :
- **Remplacer tout** : l'outil redevient exactement comme au moment de la sauvegarde. Une copie de l'état
  actuel est d'abord téléchargée, par sécurité.
- **Ajouter seulement les lignes manquantes** : une ligne déjà présente (même identifiant, ou même contenu
  si l'identifiant manque) est ignorée.

Toutes les statistiques sont recalculées aussitôt.

### CSV (pour Excel et l'import dans NERA)

Un fichier par service : `registre-<service>-<date>.csv`, encodé en UTF-8 avec BOM, séparateur `;`.
Colonnes : `Identifiant ligne`, puis les colonnes du registre dans l'ordre de `registres.js`
(intitulés `l`). L'identifiant vaut `<SERVICE>-<AAAAMM>-<N° d'ordre sur 3 chiffres>`, par exemple
`PED-202411-001` (« bis » pour un même N° le même jour).

**Reprendre un CSV** ajoute ses lignes au service affiché, sans doublons ; refuser l'ajout propose de tout
remplacer.

**Aucune donnée sur les photos** n'est exportée ni comptée : pas de colonne Photo dans les CSV, pas de nombre de
photos dans les statistiques, l'aperçu ou la sauvegarde. Les anciens CSV qui avaient une colonne Photo se
réimportent quand même.

---

## 9. Confidentialité et données

- **Jamais saisi** : nom, prénom, téléphone, contact, médecin, facture (`registres.js` ne les décrit pas).
- **Photos** : n'envoyez pas de photos où des noms ou des téléphones sont lisibles à quelqu'un d'extérieur ;
  masquez-les avant tout partage.
- **Stockage** : les lignes sont dans le stockage local du navigateur (`localStorage`, clé
  `saisie-registre-v1`). Vider les données du navigateur les efface : d'où la sauvegarde complète.
- **Git** : `.gitignore` exclut les dossiers `photos*/` et tous les `.jpg`, `.heic`, `.csv`, `.json` de ce
  dossier. **Seul le code est publié.**
- **Réseau** : aucune requête n'envoie de données. La seule ressource extérieure est la police Google Fonts.

---

## 10. Ajouter un service ou modifier un registre

Tout est dans `registres.js`. Un service = un bloc :

```js
PED: {
  nom: 'Pédiatrie',
  ordre: 'n_ordre',                         // colonne du N° d'ordre (incrémenté tout seul)
  maxLignesParPhoto: 15,
  dateReference: 'date_enregistrement',     // date de « = » et de l'identifiant
  sortieCalculee: { sortie: 'date_sortie', entree: 'date_entree', jours: 'nb_jours' },
  colonnes: [
    { k: 'age', l: 'Âge', court: true, tableau: true, aide: 'Avec l’unité : 4 ans, 9 mois, 5 j.' },
    { k: 'diagnostic', l: 'Diagnostic', raccourcis: ['APG', 'Sepsis', …] },
    …
  ],
},
```

| Champ d'une colonne | Rôle |
|---|---|
| `k` | identifiant interne (minuscules, sans accent) |
| `l` | intitulé, tel qu'il apparaît dans le CSV |
| `aide` | explication sous le champ |
| `date` | contrôle `jj/mm/aa`, raccourcis `=` et jour seul |
| `court` | champ étroit (deux par ligne) |
| `tableau` | affiché dans le tableau « Lignes de cette photo » |
| `raccourcis` | termes rapides (boutons et `Alt` + n°) |
| `separateur` | ce qui sépare deux termes (`' + '` pour les traitements) |
| `rare` | case presque toujours vide : `Entrée` la saute |

Services déjà décrits : **PED** (pédiatrie, hospitalisation) et **URG** (urgences : paramètres vitaux,
symptômes, diagnostic, décision). Les statistiques s'adaptent seules aux colonnes présentes (par exemple
pouls, TA, glycémie et température pour les urgences).

---

## 11. Fichier par fichier

| Fichier | Rôle |
|---|---|
| `saisie.html` | La page : mise en page, onglets Saisie et Contrôle qualité, visionneuse de photos, formulaire, raccourcis, aperçu, import/export CSV, sauvegarde et restauration, calcul de l'occupation (`calculerIndicateurs`) et statistiques de base de la saisie |
| `registres.js` | Description des registres (services, colonnes, termes rapides), lexique des abréviations, réglages communs (`CONFIG_SAISIE`) |
| `calendrier.js` | Jours fériés et vacances scolaires du Cameroun (`window.CALENDRIER_CM`) ; mêmes dates que `donnees/feries_supplementaires.csv` et `donnees/vacances_scolaires.csv` (vérifié par `tests/test_calendrier.py`) |
| `statistiques.js` | Bibliothèque statistique écrite à la main (`window.Stat`) : lois, descriptif, tests, régression, séries temporelles, modèles de prévision, métriques |
| `indicateurs.js` | Onglet 3 : rubriques et statistiques, graphiques SVG dessinés à la main, barre latérale, filtre, fenêtre « Agrandir », infobulles, mise à jour automatique |
| `occupation-validation.js` | Quatre contrôles de l'occupation ajoutés à la rubrique Occupation : bilan des flux, Monte-Carlo (300 tirages, graine fixe), Kaplan-Meier, file M/G/∞ |
| `assets/theme.css` | Copie de la feuille de style de l'application NERA (`app/src/styles/theme.css`) : à recopier si le thème de l'application change |
| `assets/logo-na.png`, `assets/favicon-32.png` | Logo et icône |
| `convertir_photos.bat` / `.ps1` | Conversion des photos (HEIC → JPEG, sans métadonnées) |

---

## 12. Problèmes fréquents

| Problème | Solution |
|---|---|
| Mes lignes ont disparu | Mauvaise adresse (§ 2 : `file://` et `localhost` sont séparés), autre navigateur, ou données du navigateur effacées → **Sauvegarde → Restaurer** la dernière sauvegarde complète |
| Les photos ne s'affichent plus | Normal après une réouverture : les photos ne sont jamais copiées dans l'outil → **Ouvrir les photos** à nouveau |
| Une photo HEIC ne s'ouvre pas | La convertir avec `convertir_photos.bat` (§ 3) |
| « Ce fichier ne correspond pas au registre » à l'import CSV | Choisir d'abord le bon **service** en haut, puis reprendre le CSV |
| Une meilleure transcription d'un mois déjà saisi est « déjà présente, ignorée » | Réimporter le fichier : l'outil repère les lignes de même mois, même N° et date proche (à 7 jours près) dont le contenu diffère, et propose de **remplacer** les anciennes. OK remplace (la photo rattachée est gardée), Annuler garde les anciennes. Les lignes que seul l'ancien fichier contient sont conservées |
| Un CSV importé n'apparaît pas dans les indicateurs | Le séparateur (« ; », « , » ou tabulation) et les noms de colonnes courants (« Date entrée », « Nbre jrs », « Montant », « Dg »…) sont reconnus automatiquement ; les colonnes Nom, Téléphone, Facture et Médecin ne sont jamais importées. Les lignes à partir du 01/09/2026 sont dans la **période de test verrouillée** : elles sont gardées mais n'entrent pas dans les indicateurs |
| Rubriques Occupation / Séries temporelles grisées | Saisie trop courte : il faut dépasser le rodage (§ 7) ; le message de la Synthèse dit jusqu'à quelle date saisir |
| Moins de séjours dans les durées que de lignes | Normal : seules les sorties pendant la période de calcul comptent ; l'encadré de la Synthèse détaille la répartition |
| Une corrélation affiche « — » | Pas assez de patients ayant les deux valeurs (§ 7) |
| Les modèles de prévision demandent plus de jours | Il faut au moins 42 jours saisis pour estimer et valider |
| Le style ou le logo ne s'affiche pas | Garder `saisie.html` à côté du dossier `assets/` |


### Avertissements et remarques

Dans les indicateurs, les avertissements (doublons probables, lignes écartées, numéros manquants…) et les remarques ne s'affichent plus en encadrés de couleur : chaque section montre deux boutons, « Avertissements » et « Remarques », avec leur nombre. Un clic ouvre le détail dans un panneau à droite (Échap ou clic à côté pour fermer). Dans l'onglet Saisie, les règles et raccourcis s'ouvrent de la même façon (bouton « Règles et raccourcis de saisie »).
