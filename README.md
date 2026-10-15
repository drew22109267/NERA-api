# NERA-api : API de l'application hospitalière NERA

Ce dépôt contient **uniquement le backend** de l'application NERA : l'API REST (.NET 8, PostgreSQL) qui gère les
hôpitaux, les services, les lits et les séjours, importe les registres harmonisés et accueillera les prévisions
du modèle.

Le reste du projet est dans deux autres dépôts :

| Dépôt | Contenu |
|---|---|
| **NERA-api** (celui-ci) | l'API de l'application hospitalière NERA |
| [outil-saisi](https://github.com/drew22109267/outil-saisi) | collecte des données (outil de saisie des registres papier), traitement (occupation des lits), statistiques, décisions prises sur les données |
| [nera-modele](https://github.com/drew22109267/nera-modele) | le modèle de prévision NERA : module lit (opérationnel) et module triage (en préparation), avec toutes les mathématiques |

## Sommaire

- [Organisation du dépôt](#organisation-du-dépôt)
- [Backend](#backend)
  - [1.1 Prérequis](#11-prérequis) · [1.2 Lancer l'API](#12-lancer-lapi) · [1.3 Configuration et secrets](#13-configuration-et-secrets) · [1.4 Comptes initiaux](#14-comptes-initiaux)
  - [1.5 Points d'entrée](#15-points-dentrée) · [1.6 Fonctionnement interne](#16-fonctionnement-interne) · [1.7 Limites connues](#17-limites-connues)

---

## Organisation du dépôt

```
backend/
├── README.md                     ce document
├── HopitalApi/                   API .NET 8 (contrôleurs, services, modèles, migrations)
│   ├── appsettings.json          réglages communs, sans secret
│   └── appsettings.exemple.json  modèle des secrets à remplir
├── lancer-api-wsl.bat / .sh      lancement de l'API dans WSL (Windows)
└── docker-compose.yml            base PostgreSQL en conteneur (option)
```

---

# Backend

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
