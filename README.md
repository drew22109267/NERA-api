# API Triage & Lits — backend .NET 8 + PostgreSQL

API REST qui remplace intégralement les données locales du frontend. Aucune donnée
de patient n'est pré-remplie : la base démarre avec les seules données de référence
(établissement, services, lits, règles d'orientation, paramètres, comptes).

Le dépôt contient deux parties :

| Dossier | Contenu | Documentation |
| --- | --- | --- |
| `HopitalApi/` | API REST de l'application hospitalière (.NET 8, PostgreSQL) | ce document |
| `modeles/` | code du mémoire : reconstitution de l'occupation des lits, statistiques, modèles SVR écrits à la main (PyTorch), outil de saisie des registres | [`modeles/README.md`](modeles/README.md) : installation, parcours des données, toutes les formules mathématiques, fichier par fichier, ordre des scripts, tests |

## Prérequis

- .NET SDK 8.0
- PostgreSQL 14 ou plus

## Démarrage

```bash
# 1. base de données
createdb hopital          # ou : docker compose up -d db

# 2. chaîne de connexion — adapter si besoin
#    backend/HopitalApi/appsettings.json → ConnectionStrings:Postgres

# 3. migration initiale (une seule fois)
cd backend/HopitalApi
dotnet tool install --global dotnet-ef      # si absent
dotnet ef migrations add InitialCreate
dotnet ef database update

# 4. lancer
dotnet run
```

L'API écoute sur `http://localhost:5080` (voir `Properties/launchSettings.json`).
Documentation interactive : `http://localhost:5080/swagger`.
Sonde de santé : `GET /api/sante`.

Au démarrage l'application applique les migrations puis amorce les données de
référence si les tables sont vides.

## Comptes initiaux

Créés au premier démarrage avec le mot de passe défini par `Seed:DemoPassword`
(`demo1234` par défaut — **à changer avant toute mise en service**).

| Rôle | Adresse |
| --- | --- |
| Agent d'accueil | accueil@hopital.cm |
| Infirmier de triage | infirmier@hopital.cm |
| Médecin | medecin@hopital.cm |
| Gestionnaire de lits | lits@hopital.cm |
| Direction | direction@hopital.cm |
| Data manager | data@hopital.cm |
| Administrateur | admin@hopital.cm |

Les mots de passe sont hachés avec BCrypt. L'authentification délivre un jeton JWT
(12 h) que le frontend envoie en en-tête `Authorization: Bearer …`.

## Points d'entrée

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

Toutes les listes volumineuses sont paginées : `?page=1&pageSize=25`, réponse
`{ items, total, page, pageSize, pages }`.

## Modèle d'intelligence artificielle

Les modèles d'apprentissage **ne sont pas implémentés**. Trois services portent
aujourd'hui une implémentation par règles, à la même signature que l'appel réseau
qui les remplacera :

| Service | Fichier | Remplace |
| --- | --- | --- |
| `TriageScoreService.Evaluer` | `Services/TriageScoreService.cs` | SVM de triage |
| `PrevisionCapaciteService.Prevoir` | `Services/PrevisionCapaciteService.cs` | SVR quantile |
| `PrevisionCapaciteService.ProbaSortie` | idem | SVM de survie |

Chaque appel au moteur de triage est journalisé dans `PredictionLog` avec son
entrée, sa sortie, son explication et la décision humaine — le matériau nécessaire
au réentraînement et à l'audit d'équité. Le nom du modèle actif est stocké dans
`Parametres` (`modele.triage`, `modele.prevision`).

## Redistribution des patients

`OrientationService` croise quatre sources : la règle clinique (table
`RegleOrientation`, motif → service d'accueil + service de repli), les bornes d'âge
et de sexe du service, la catégorie de triage, et les lits réellement libres.
Il renvoie jusqu'à cinq propositions classées, chacune avec ses raisons en clair et
un avertissement lorsqu'aucun lit n'est disponible.

## Concurrence et cohérence

`Passage` et `Service` portent une colonne de version PostgreSQL (`xmin`). Si deux
postes modifient le même passage, le second reçoit `409 Conflict` avec un message
explicite plutôt qu'un écrasement silencieux.

## Confidentialité

`AuditLog` enregistre les actions **et** les simples consultations de dossier
(`type = consultation`), avec utilisateur, rôle, cible et adresse IP.
`DELETE /api/patients/{id}` anonymise le dossier à la demande du patient.

## Limites connues

- Mise à jour entre postes par interrogation périodique côté frontend ; un hub
  SignalR est le prochain ajout naturel pour du temps réel.
- Stockage des pièces jointes sur disque local ; à remplacer par MinIO ou S3.
- Passerelle SMS/USSD non branchée : les notifications de canal `SMS` sont
  enregistrées en base et affichées dans l'application, sans envoi réel.
