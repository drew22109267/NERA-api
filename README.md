# NERA : API hospitalière et chaîne de données du mémoire

Ce dépôt contient deux volets, documentés chacun dans sa rubrique :

| Rubrique | Dossier | Ce que c'est |
| --- | --- | --- |
| [**Partie 1 · Backend**](#partie-1--backend) | `HopitalApi/` | l'API REST de l'application hospitalière NERA (.NET 8, PostgreSQL) |
| [**Partie 2 · Saisie IA**](#partie-2--saisie-ia--collecte-et-transcription-des-registres) | `modeles/outil-saisie/` | la collecte des registres papier : photos, masquage, transcription (à la main ou assistée par IA), import, contrôle qualité, analyses |

Les modèles du mémoire (reconstitution de l'occupation, statistiques, SVR écrits à la main en
PyTorch, validation) sont dans `modeles/`, avec toutes leurs formules mathématiques dans
[`modeles/README.md`](modeles/README.md). La [partie 3](#partie-3--modèles-du-mémoire) en donne le résumé.

## Sommaire

- [Organisation du dépôt](#organisation-du-dépôt)
- [Partie 1 · Backend](#partie-1--backend)
  - [1.1 Prérequis](#11-prérequis) · [1.2 Lancer l'API](#12-lancer-lapi) · [1.3 Configuration et secrets](#13-configuration-et-secrets) · [1.4 Comptes initiaux](#14-comptes-initiaux)
  - [1.5 Points d'entrée](#15-points-dentrée) · [1.6 Fonctionnement interne](#16-fonctionnement-interne) · [1.7 Limites connues](#17-limites-connues)
- [Partie 2 · Saisie IA : collecte et transcription des registres](#partie-2--saisie-ia--collecte-et-transcription-des-registres)
  - [2.1 Vue d'ensemble](#21-vue-densemble) · [2.2 Photographier](#22-étape-1--photographier-les-registres) · [2.3 Convertir](#23-étape-2--convertir-les-photos)
  - [2.4 Lancer l'outil](#24-étape-3--lancer-loutil-de-saisie) · [2.5 Masquer](#25-étape-4--masquer-les-données-identifiantes) · [2.6 Transcrire](#26-étape-5--transcrire)
  - [2.7 Importer](#27-étape-6--importer-un-csv) · [2.8 Contrôle qualité](#28-étape-7--mesurer-la-qualité-de-la-saisie) · [2.9 Combler les trous](#29-étape-8--repérer-et-combler-les-trous)
  - [2.10 Sauvegarder](#210-étape-9--sauvegarder-et-exporter) · [2.11 Analyser](#211-étape-10--analyser) · [2.12 Confidentialité](#212-confidentialité-et-fichiers-jamais-versionnés)
- [Partie 3 · Modèles du mémoire](#partie-3--modèles-du-mémoire)

---

## Organisation du dépôt

```
backend/
├── README.md                     ce document
├── HopitalApi/                   Partie 1 : API .NET 8 (contrôleurs, services, modèles, migrations)
│   ├── appsettings.json          réglages communs, sans secret
│   └── appsettings.exemple.json  modèle des secrets à remplir
├── lancer-api-wsl.bat / .sh      lancement de l'API dans WSL (Windows)
├── docker-compose.yml            base PostgreSQL en conteneur (option)
└── modeles/
    ├── README.md                 modèles du mémoire : formules, scripts, tests
    ├── outil-saisie/             Partie 2 : outil de saisie des registres (HTML + JavaScript)
    │   ├── saisie.html           la page à ouvrir
    │   ├── LISEZMOI.md           mode d'emploi détaillé de l'outil
    │   └── convertir_photos.bat  conversion des photos (HEIC → JPEG, sans métadonnées)
    ├── nera/ , svr/ , tests/     Partie 3 : code Python des modèles
    └── *.py                      scripts d'analyse, dans l'ordre décrit par modeles/README.md
```

---

# Partie 1 · Backend

API REST qui remplace intégralement les données locales du frontend. Aucune donnée de patient
n'est pré-remplie : la base démarre avec les seules données de référence (établissement,
services, lits, règles d'orientation, paramètres, comptes).

## 1.1 Prérequis

- .NET SDK 8.0
- PostgreSQL 14 ou plus (installé, ou en conteneur avec `docker compose up -d db`)
- Sous Windows avec Smart App Control actif : WSL (Ubuntu), voir 1.2

## 1.2 Lancer l'API

**Une seule fois :**

```bash
# 1. créer la base
createdb hopital                    # ou : docker compose up -d db

# 2. créer les secrets locaux (voir 1.3), puis remplir le fichier
cp HopitalApi/appsettings.exemple.json HopitalApi/appsettings.Development.json

# 3. outil de migration
dotnet tool install --global dotnet-ef
```

**Ensuite, à chaque fois :**

- Sous Linux ou macOS :

  ```bash
  cd HopitalApi
  dotnet run
  ```

- Sous Windows : double-cliquer sur `lancer-api-wsl.bat`. Le script copie le code dans WSL,
  le compile et lance l'API ; fermer la fenêtre l'arrête. On l'utilise parce que Smart App Control
  bloque les bibliothèques compilées lancées directement depuis Windows.

Au démarrage, l'API applique les migrations, puis amorce les données de référence si les tables
sont vides.

- API : `http://localhost:5080`
- Documentation interactive : `http://localhost:5080/swagger`
- Sonde de santé : `GET /api/sante`

## 1.3 Configuration et secrets

Aucun secret n'est versionné. La configuration est répartie en trois fichiers :

| Fichier | Versionné | Contenu |
| --- | --- | --- |
| `HopitalApi/appsettings.json` | oui | réglages communs, **sans aucun secret** (chaîne de connexion et clé JWT vides) |
| `HopitalApi/appsettings.exemple.json` | oui | modèle à copier, avec les clés à remplir |
| `HopitalApi/appsettings.Development.json` | **non** (`.gitignore`) | les vrais secrets du poste de développement |

ASP.NET Core lit `appsettings.json`, puis `appsettings.<Environnement>.json`, puis les variables
d'environnement ; chaque source remplace la précédente. En développement (`dotnet run`,
`lancer-api-wsl.sh`), l'environnement est `Development` : les secrets viennent donc de
`appsettings.Development.json`.

| Clé | Rôle | Variable d'environnement (production) |
| --- | --- | --- |
| `ConnectionStrings:Postgres` | connexion à la base, mot de passe compris | `ConnectionStrings__Postgres` |
| `Jwt:Key` | signature des jetons de connexion ; au moins 32 caractères aléatoires | `Jwt__Key` |
| `Seed:AdminPassword` | mot de passe du premier administrateur, utilisé seulement si aucun administrateur n'existe | `Seed__AdminPassword` |

Générer une clé JWT :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

En production, on ne crée pas de fichier : on définit les variables d'environnement sur le
serveur (ou dans le gestionnaire de secrets de l'hébergeur) :

```bash
export ConnectionStrings__Postgres="Host=...;Database=hopital;Username=...;Password=..."
export Jwt__Key="<clé générée>"
```

Si la chaîne de connexion ou la clé JWT manque (ou si la clé fait moins de 32 caractères),
l'API refuse de démarrer et indique ce qui manque. Changer la clé JWT déconnecte tous les
utilisateurs : il suffit de se reconnecter.

## 1.4 Comptes initiaux

Le premier administrateur est créé au premier démarrage avec l'adresse `Seed:AdminEmail` et le
mot de passe `Seed:AdminPassword`, **à changer dès la première connexion**.

| Rôle | Adresse |
| --- | --- |
| Agent d'accueil | accueil@hopital.cm |
| Infirmier de triage | infirmier@hopital.cm |
| Médecin | medecin@hopital.cm |
| Gestionnaire de lits | lits@hopital.cm |
| Direction | direction@hopital.cm |
| Data manager | data@hopital.cm |
| Administrateur | admin@hopital.cm |

Les mots de passe sont hachés avec BCrypt. L'authentification délivre un jeton JWT (12 h) que le
frontend envoie en en-tête `Authorization: Bearer …`.

## 1.5 Points d'entrée

| Domaine | Route |
| --- | --- |
| Authentification | `POST /api/auth/login`, `POST /api/auth/signup`, `GET /api/auth/moi` |
| Comptes | `GET /api/auth/utilisateurs`, `PATCH /api/auth/utilisateurs/{id}` |
| Patients | `GET/POST /api/patients`, `GET/PUT/DELETE /api/patients/{id}`, `GET /api/patients/doublons` |
| Passages | `GET/POST /api/passages`, `GET /api/passages/{id}` |
| Triage | `POST /api/passages/{id}/evaluer`, `POST /api/passages/{id}/triage` |
| Décision | `POST /api/passages/{id}/decision`, `POST /api/passages/{id}/statut` |
| Services & lits | `GET /api/services`, `PUT /api/services/{id}`, `GET /api/services/{id}/lits` |
| Prévision | `GET /api/services/{id}/prevision?horizon=30&hausseAdmissions=10` |
| Orientation | `GET /api/orientation?motif=…&age=…&sexe=F&categorie=2`, `GET /api/orientation/motifs` |
| Séjours | `GET/POST /api/sejours`, `POST /api/sejours/{id}/sortie`, `POST /api/sejours/{id}/blocage` |
| Rendez-vous | `GET/POST /api/rendezvous`, `GET /api/rendezvous/creneaux`, `POST /api/rendezvous/{id}/statut` |
| Demandes non satisfaites | `GET/POST /api/demandes` |
| Notifications | `GET/POST /api/notifications`, `POST /api/notifications/{id}/lue` |
| Tableau de bord | `GET /api/tableau-bord`, `GET /api/tableau-bord/recherche?q=…` |
| Rapports | `GET /api/rapports/indicateurs`, `GET /api/rapports/occupation.csv`, `GET /api/rapports/export-complet` |
| Qualité & audit | `GET /api/qualite`, `GET /api/qualite/predictions`, `GET /api/qualite/audit` |
| Paramètres | `GET /api/parametres`, `PUT /api/parametres/{cle}` |
| Pièces jointes | `GET/POST /api/pieces-jointes`, `GET /api/pieces-jointes/{id}/contenu` |
| Recherche multi-hôpitaux | contrôleurs `Recherche`, `Etablissements`, `Referentiels` (import des registres, indicateurs, référentiels partagés) |

Toutes les listes volumineuses sont paginées : `?page=1&pageSize=25`, réponse
`{ items, total, page, pageSize, pages }`.

## 1.6 Fonctionnement interne

**Modèles d'intelligence artificielle.** Les modèles d'apprentissage ne sont **pas encore branchés**
sur l'API. Trois services portent aujourd'hui une implémentation par règles, avec la même signature
que l'appel qui les remplacera :

| Service | Fichier | Remplacé par |
| --- | --- | --- |
| `TriageScoreService.Evaluer` | `Services/TriageScoreService.cs` | SVM de triage |
| `PrevisionCapaciteService.Prevoir` | `Services/PrevisionCapaciteService.cs` | SVR quantile (partie 3) |
| `PrevisionCapaciteService.ProbaSortie` | idem | modèle de survie J0/J1/J2 (partie 3) |

Chaque appel au moteur de triage est journalisé dans `PredictionLog` (entrée, sortie, explication,
décision humaine) : c'est le matériau du réentraînement et de l'audit d'équité. Le nom du modèle
actif est stocké dans `Parametres` (`modele.triage`, `modele.prevision`).

**Redistribution des patients.** `OrientationService` croise la règle clinique (table
`RegleOrientation` : motif → service d'accueil et service de repli), les bornes d'âge et de sexe du
service, la catégorie de triage et les lits réellement libres. Il renvoie jusqu'à cinq propositions
classées, chacune avec ses raisons, et un avertissement si aucun lit n'est libre.

**Concurrence.** `Passage` et `Service` portent une colonne de version PostgreSQL (`xmin`). Si deux
postes modifient le même passage, le second reçoit `409 Conflict` au lieu d'écraser le premier.

**Confidentialité.** `AuditLog` enregistre les actions et les simples consultations de dossier
(utilisateur, rôle, cible, adresse IP). `DELETE /api/patients/{id}` anonymise le dossier à la
demande du patient.

## 1.7 Limites connues

- Mise à jour entre postes par interrogation périodique ; un hub SignalR serait l'étape suivante.
- Pièces jointes stockées sur disque local ; à remplacer par un stockage objet (MinIO, S3).
- Passerelle SMS/USSD non branchée : les notifications SMS sont enregistrées sans envoi réel.

---

# Partie 2 · Saisie IA : collecte et transcription des registres

Les données du mémoire viennent des **registres papier d'hospitalisation** (pédiatrie). Cette
partie décrit, étape par étape, comment on passe d'un registre papier à des données propres et
contrôlées. Tout se fait avec l'**outil de saisie** (`modeles/outil-saisie/saisie.html`), une page
web autonome : rien à installer, aucune donnée envoyée sur Internet.

La transcription des lignes peut se faire **à la main** dans l'outil ou être **assistée par une IA**
(un assistant capable de lire des images, qui reçoit les photos masquées et rend un CSV). Dans les
deux cas, ce sont les mêmes étapes de masquage, d'import et de contrôle qui garantissent la qualité.

Le mode d'emploi détaillé de l'outil (raccourcis, règles de recopie, calculs, ajout d'un service)
est dans [`modeles/outil-saisie/LISEZMOI.md`](modeles/outil-saisie/LISEZMOI.md).

## 2.1 Vue d'ensemble

```
 1. Photographier le registre (page par page, téléphone)
 2. Convertir les photos           convertir_photos.bat : HEIC → JPEG, métadonnées supprimées
 3. Ouvrir l'outil de saisie       saisie.html (double-clic ou petit serveur local)
 4. Masquer noms et téléphones     bouton « Masquer », puis « Enregistrer les photos masquées »
 5. Transcrire                     à la main (onglet Saisie) ou par IA à partir des photos masquées → CSV
 6. Importer le CSV                Sauvegarde → « Reprendre un CSV »
 7. Contrôle qualité               onglet 2 : pages tirées au hasard, taux d'erreur chiffré
 8. Combler les trous              panneau Avertissements : N° manquants, jours sans inscription
 9. Sauvegarder / exporter         sauvegarde complète .json, CSV pour l'application NERA
10. Analyser                       onglet 3 (indicateurs, statistiques, prévisions), puis modèles Python
```

## 2.2 Étape 1 · Photographier les registres

- Une photo par page (ou par double page si tout reste lisible), à plat, bien éclairée, sans reflet.
- Toujours cadrer la **colonne des N° d'ordre** et la **date** : ce sont eux qui identifient les lignes.
- Photographier **jusqu'à la dernière ligne de chaque mois**. Les fins de mois sont les pages les plus
  souvent oubliées : un trou de plusieurs jours en fin de mois dans les analyses vient presque toujours
  d'une dernière page non photographiée.
- Photographier aussi le **récapitulatif mensuel** du registre : il sert à vérifier les totaux.
- Ranger les photos dans un dossier par service et par période. Garder les originaux à part.

## 2.3 Étape 2 · Convertir les photos

Les téléphones produisent souvent des photos HEIC (que les navigateurs n'affichent pas), et toutes
les photos contiennent des métadonnées (position GPS, date, modèle du téléphone).

1. Double-cliquer sur `modeles/outil-saisie/convertir_photos.bat`.
2. Indiquer le dossier des photos originales, puis le dossier de sortie.

Le script convertit en JPEG, réduit à 2 600 pixels de côté au plus, **supprime les métadonnées** et ne
modifie jamais les originaux. Il utilise le décodeur intégré à Windows : rien à installer.

## 2.4 Étape 3 · Lancer l'outil de saisie

- **Méthode A, la plus simple** : double-cliquer sur `modeles/outil-saisie/saisie.html` (Chrome ou Edge).
- **Méthode B, serveur local** : depuis le dossier qui contient `backend/` :

  ```bash
  python -m http.server 8765
  ```

  puis ouvrir `http://localhost:8765/backend/modeles/outil-saisie/saisie.html`.

Le navigateur range les lignes **par adresse** : les lignes saisies par la méthode A ne sont pas
visibles par la méthode B, ni dans un autre navigateur. Choisir une méthode et la garder ; pour passer
de l'une à l'autre, utiliser la sauvegarde complète (étape 9).

À la première ouverture, choisir le **service** en haut de l'écran. La fenêtre « Aide » rappelle les
règles à tout moment.

## 2.5 Étape 4 · Masquer les données identifiantes

Avant qu'une photo quitte l'ordinateur (par exemple pour une transcription assistée par IA), les
données identifiantes doivent être cachées.

1. Menu **Ouvrir les photos** : sélectionner les JPEG convertis.
2. Sur la photo, bouton **■ Masquer**, puis tracer un rectangle (cliquer-glisser) sur chaque **nom**,
   **téléphone**, **nom de médecin** et **numéro de facture**.
3. **Reprendre la photo précédente** recopie les masques quand la mise en page est la même.
4. **Enregistrer toutes les photos masquées** : l'outil produit des copies où les zones sont noircies
   dans l'image elle-même. Ce sont ces copies, et elles seules, qui peuvent être transmises.

## 2.6 Étape 5 · Transcrire

**À la main** (onglet 1 · Saisie) : la photo à gauche, le formulaire à droite. `Entrée` passe au champ
suivant, `Ctrl + Entrée` enregistre la ligne, le N° suivant se remplit seul. Les règles (« ? » pour
une case illisible, « = » pour une date identique, etc.) sont dans le LISEZMOI de l'outil.

**Assistée par IA**, à partir des photos masquées. On demande à l'assistant de rendre un CSV qui
respecte les règles suivantes :

| Règle | Détail |
| --- | --- |
| En-tête | `Identifiant ligne;N° d'ordre;Date (enregistrement);Ancien / Nouveau;Sexe;Âge;Domicile;Date d'entrée;Date de sortie;Diagnostic;Bilan demandé;T3 reçu;GE / TDR palu;Diagnostic de sortie;T3 de sortie;Nbre de jours;Prix;Observation;Remarque de saisie` |
| Séparateur | `;` de préférence ; `,` et la tabulation sont aussi reconnus |
| Dates | `jj/mm/aa` ou `jj/mm/aaaa` |
| Une ligne du registre | une ligne du CSV, dans l'ordre des N° |
| Case illisible | la valeur lue suivie de `?`, ou `?` seul |
| Jamais recopié | nom, prénom, téléphone, médecin, numéro de facture |
| Notes en rouge | dans la remarque : « Transfusion (rouge) », « Drépano (rouge) », « Référé… » |
| Remarque | commence par « Transcription IA à vérifier », suivie de ce qui était douteux |

L'import reconnaît aussi les autres noms de colonnes courants (« N° », « Date », « Date entrée »,
« Date sortie », « Dg », « Signe/Symptôme », « Nbre jrs », « Montant », « Annotation (rouge) »…) et
sépare un montant écrit avec l'issue (« 7500F Sortie »). Les colonnes nom, téléphone, médecin et
facture ne sont **jamais importées**, même si elles sont présentes.

Une transcription par IA n'est jamais considérée comme juste par principe : elle passe par le
contrôle qualité de l'étape 7, comme une saisie à la main.

## 2.7 Étape 6 · Importer un CSV

1. Choisir le bon **service** en haut de l'écran.
2. Bouton **Sauvegarde** (en bas de la barre latérale) → **Reprendre un CSV** → choisir le fichier.
3. L'outil indique combien de lignes ont été ajoutées et combien, déjà présentes, ont été ignorées :
   on peut réimporter un fichier sans créer de doublon.
4. Vérifier dans **Aperçu des lignes** (barre latérale) que les mois attendus apparaissent.

Si une ligne transcrite deux fois diffère légèrement (deux transcriptions de la même page), elle n'est
pas reconnue comme doublon : le panneau Avertissements de l'onglet 3 signale les doublons probables.

## 2.8 Étape 7 · Mesurer la qualité de la saisie

Onglet 2 · **Contrôle qualité**. On relit un échantillon tiré au hasard, page par page, et l'outil en
déduit le taux d'erreur de toute la saisie.

1. Ouvrir les photos, choisir le nombre de pages (20 par défaut, environ 300 lignes), **Tirer au hasard**.
2. Pour chaque page : choisir le **mois** et taper le **premier N°** écrit sur la photo. Les lignes
   saisies correspondantes s'affichent à côté (le dernier N° se remplit seul). La photo n'a pas besoin
   d'avoir été rattachée à ses lignes au moment de la saisie.
3. Cliquer chaque case **différente de la photo** (elle devient rouge) ; compter les lignes oubliées ou
   en trop.
4. **Voir les résultats** : taux d'erreur global avec son intervalle de confiance, taux sur les colonnes
   qui servent au calcul de l'occupation, taux par colonne, liste des erreurs avec un bouton
   **Corriger**, et une phrase prête pour le mémoire.

Repères : moins de 1 % de cases fausses, très bonne qualité ; moins de 2 %, bonne ; de 2 à 5 %,
acceptable ; au-delà, la saisie est à reprendre. Une colonne au-dessus de 5 % est à revérifier en
entier. Une photo identifiée l'est pour de bon, et ses voisines sont proposées automatiquement.

## 2.9 Étape 8 · Repérer et combler les trous

Dans l'onglet 3 · Indicateurs, le bouton **Avertissements** liste par mois :

- les **N° d'ordre manquants** (la numérotation repart à 1 chaque mois) : une suite de N° manquants
  signale une page entière non saisie ;
- le **trou final** (dernières pages pas encore saisies) : le calcul de l'occupation s'arrête avant ;
- les dates d'enregistrement incohérentes et les doublons probables.

Il faut aussi chercher les **jours sans aucune inscription** de plus de trois jours hors week-end,
surtout en fin de mois. Ces trous font baisser artificiellement l'occupation et faussent
l'apprentissage du modèle : on les comble en retrouvant les pages, ou on les signale dans le mémoire.

## 2.10 Étape 9 · Sauvegarder et exporter

Bouton **Sauvegarde** (barre latérale) :

- **Télécharger la sauvegarde complète** (`.json`) à la fin de **chaque séance** : lignes de tous les
  services, masques, contrôles qualité, réglages. C'est la vraie copie de sécurité ; la garder aussi sur
  une clé USB. **Restaurer** la recharge en un clic.
- **CSV du service affiché** ou **de tous les services** : le fichier importé dans l'application NERA.

## 2.11 Étape 10 · Analyser

L'onglet 3 · **Indicateurs** calcule en direct, sur les lignes saisies : occupation (taux, pics, loi de
Little, Erlang B, bilan des flux, Monte-Carlo, survie, file M/G/∞), statistiques descriptives,
corrélations et tests, ACP, calendrier camerounais, séries temporelles et modèles de prévision.

**Période verrouillée.** Les lignes entrées à partir du **01/09/2026** sont gardées mais n'entrent dans
**aucune** analyse : septembre et octobre 2026 sont réservés au test final du modèle (partie 3).

Pour les modèles du mémoire : exporter le dataset harmonisé depuis l'application NERA dans
`modeles/donnees/`, puis suivre [`modeles/README.md`](modeles/README.md).

## 2.12 Confidentialité et fichiers jamais versionnés

- Les photos, les CSV, les sauvegardes `.json` et le dossier `modeles/donnees/` sont exclus par le
  `.gitignore` : **seuls le code, la documentation et les icônes sont sur GitHub.**
- Les noms, téléphones, médecins et numéros de facture ne sont ni recopiés, ni importés, ni exportés.
- L'outil n'envoie rien sur Internet ; seule la police d'écriture est chargée depuis Google Fonts quand
  Internet est disponible.

---

# Partie 3 · Modèles du mémoire

Le dossier `modeles/` contient la chaîne d'analyse du mémoire, écrite à la main en PyTorch (aucune
bibliothèque d'apprentissage automatique) :

1. reconstitution de l'occupation jour par jour (recensement de minuit, convention des jours, trois
   scénarios) et indicateurs hospitaliers ;
2. SVR en cinq niveaux (linéaire, noyau RBF, quantile à coûts asymétriques, noyau composite,
   empilement), optimisés par Adam avec des gradients dérivés analytiquement ;
3. validation glissante, banc de comparaison de tous les choix, test de Diebold-Mariano ;
4. test final sur septembre-octobre 2026, avec réentraînement mensuel ;
5. modèle de survie J0/J1/J2 et transfert vers les services à historique court.

Installation, ordre des scripts, toutes les formules mathématiques, lecture des figures et tests :
[`modeles/README.md`](modeles/README.md).
