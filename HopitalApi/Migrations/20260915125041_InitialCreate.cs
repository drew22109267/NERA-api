using System;
using System.Collections.Generic;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace HopitalApi.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Audits",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Date = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UtilisateurId = table.Column<int>(type: "integer", nullable: true),
                    Utilisateur = table.Column<string>(type: "text", nullable: false),
                    Role = table.Column<string>(type: "text", nullable: false),
                    Type = table.Column<string>(type: "text", nullable: false),
                    Action = table.Column<string>(type: "text", nullable: false),
                    Cible = table.Column<string>(type: "text", nullable: true),
                    Detail = table.Column<string>(type: "text", nullable: true),
                    AdresseIp = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Audits", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Etablissements",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Code = table.Column<string>(type: "text", nullable: false),
                    Nom = table.Column<string>(type: "text", nullable: false),
                    Categorie = table.Column<string>(type: "text", nullable: false),
                    Ville = table.Column<string>(type: "text", nullable: false),
                    Region = table.Column<string>(type: "text", nullable: false),
                    Actif = table.Column<bool>(type: "boolean", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Etablissements", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Notifications",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Date = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    Destinataire = table.Column<string>(type: "text", nullable: false),
                    UtilisateurId = table.Column<int>(type: "integer", nullable: true),
                    PatientId = table.Column<int>(type: "integer", nullable: true),
                    Type = table.Column<string>(type: "text", nullable: false),
                    Texte = table.Column<string>(type: "text", nullable: false),
                    Niveau = table.Column<string>(type: "text", nullable: false),
                    Canal = table.Column<string>(type: "text", nullable: false),
                    Lue = table.Column<bool>(type: "boolean", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Notifications", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Parametres",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Cle = table.Column<string>(type: "text", nullable: false),
                    Valeur = table.Column<string>(type: "text", nullable: false),
                    Libelle = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Parametres", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Patients",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Reference = table.Column<string>(type: "text", nullable: false),
                    Nom = table.Column<string>(type: "text", nullable: false),
                    Prenom = table.Column<string>(type: "text", nullable: false),
                    Sexe = table.Column<string>(type: "text", nullable: false),
                    Age = table.Column<int>(type: "integer", nullable: false),
                    DateNaissance = table.Column<DateOnly>(type: "date", nullable: true),
                    Telephone = table.Column<string>(type: "text", nullable: true),
                    Email = table.Column<string>(type: "text", nullable: true),
                    Quartier = table.Column<string>(type: "text", nullable: true),
                    Arrondissement = table.Column<string>(type: "text", nullable: true),
                    Milieu = table.Column<string>(type: "text", nullable: false),
                    ModePaiement = table.Column<string>(type: "text", nullable: false),
                    ContactUrgence = table.Column<string>(type: "text", nullable: true),
                    Antecedents = table.Column<List<string>>(type: "text[]", nullable: false),
                    Allergies = table.Column<string>(type: "text", nullable: true),
                    Consentement = table.Column<bool>(type: "boolean", nullable: false),
                    CreeLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Patients", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Predictions",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Date = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    PassageId = table.Column<int>(type: "integer", nullable: true),
                    Modele = table.Column<string>(type: "text", nullable: false),
                    TypeModele = table.Column<string>(type: "text", nullable: false),
                    Score = table.Column<double>(type: "double precision", nullable: false),
                    Sortie = table.Column<int>(type: "integer", nullable: false),
                    Confiance = table.Column<double>(type: "double precision", nullable: false),
                    ExplicationJson = table.Column<string>(type: "text", nullable: false),
                    EntreeJson = table.Column<string>(type: "text", nullable: false),
                    DecisionHumaine = table.Column<int>(type: "integer", nullable: true),
                    Ecart = table.Column<bool>(type: "boolean", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Predictions", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "ReglesOrientation",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Motif = table.Column<string>(type: "text", nullable: false),
                    ServiceCode = table.Column<string>(type: "text", nullable: false),
                    ServiceAlternatifCode = table.Column<string>(type: "text", nullable: true),
                    Priorite = table.Column<int>(type: "integer", nullable: false),
                    AgeMin = table.Column<int>(type: "integer", nullable: false),
                    AgeMax = table.Column<int>(type: "integer", nullable: false),
                    SexeRequis = table.Column<string>(type: "text", nullable: true),
                    CategorieMax = table.Column<int>(type: "integer", nullable: true),
                    Commentaire = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ReglesOrientation", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Utilisateurs",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Nom = table.Column<string>(type: "text", nullable: false),
                    Email = table.Column<string>(type: "text", nullable: false),
                    MotDePasseHash = table.Column<string>(type: "text", nullable: false),
                    Role = table.Column<string>(type: "text", nullable: false),
                    ServiceId = table.Column<int>(type: "integer", nullable: true),
                    PatientId = table.Column<int>(type: "integer", nullable: true),
                    Actif = table.Column<bool>(type: "boolean", nullable: false),
                    CreeLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    DerniereConnexion = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Utilisateurs", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Services",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EtablissementId = table.Column<int>(type: "integer", nullable: false),
                    Code = table.Column<string>(type: "text", nullable: false),
                    Nom = table.Column<string>(type: "text", nullable: false),
                    Pole = table.Column<string>(type: "text", nullable: false),
                    Hospitalisation = table.Column<bool>(type: "boolean", nullable: false),
                    UrgencesCompatible = table.Column<bool>(type: "boolean", nullable: false),
                    AgeMin = table.Column<int>(type: "integer", nullable: false),
                    AgeMax = table.Column<int>(type: "integer", nullable: false),
                    LitsInstalles = table.Column<int>(type: "integer", nullable: false),
                    LitsArmes = table.Column<int>(type: "integer", nullable: false),
                    Occupes = table.Column<int>(type: "integer", nullable: false),
                    Bloques = table.Column<int>(type: "integer", nullable: false),
                    Programmes = table.Column<int>(type: "integer", nullable: false),
                    Tendance = table.Column<double>(type: "double precision", nullable: false),
                    Ordre = table.Column<int>(type: "integer", nullable: false),
                    Actif = table.Column<bool>(type: "boolean", nullable: false),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Services", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Services_Etablissements_EtablissementId",
                        column: x => x.EtablissementId,
                        principalTable: "Etablissements",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "PiecesJointes",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    PatientId = table.Column<int>(type: "integer", nullable: false),
                    PassageId = table.Column<int>(type: "integer", nullable: true),
                    NomFichier = table.Column<string>(type: "text", nullable: false),
                    TypeMime = table.Column<string>(type: "text", nullable: false),
                    Taille = table.Column<long>(type: "bigint", nullable: false),
                    Categorie = table.Column<string>(type: "text", nullable: false),
                    CheminStockage = table.Column<string>(type: "text", nullable: false),
                    DeposeLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    DeposePar = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PiecesJointes", x => x.Id);
                    table.ForeignKey(
                        name: "FK_PiecesJointes_Patients_PatientId",
                        column: x => x.PatientId,
                        principalTable: "Patients",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Demandes",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Reference = table.Column<string>(type: "text", nullable: false),
                    Date = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ServiceId = table.Column<int>(type: "integer", nullable: false),
                    PatientId = table.Column<int>(type: "integer", nullable: true),
                    Motif = table.Column<string>(type: "text", nullable: false),
                    Gravite = table.Column<string>(type: "text", nullable: false),
                    Devenir = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Demandes", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Demandes_Services_ServiceId",
                        column: x => x.ServiceId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Lits",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    ServiceId = table.Column<int>(type: "integer", nullable: false),
                    Code = table.Column<string>(type: "text", nullable: false),
                    Statut = table.Column<string>(type: "text", nullable: false),
                    MotifBlocage = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Lits", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Lits_Services_ServiceId",
                        column: x => x.ServiceId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Passages",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Reference = table.Column<string>(type: "text", nullable: false),
                    PatientId = table.Column<int>(type: "integer", nullable: false),
                    Arrivee = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ModeEntree = table.Column<string>(type: "text", nullable: false),
                    Motif = table.Column<string>(type: "text", nullable: false),
                    MotifLibre = table.Column<string>(type: "text", nullable: true),
                    ServiceViseId = table.Column<int>(type: "integer", nullable: true),
                    Statut = table.Column<string>(type: "text", nullable: false),
                    Categorie = table.Column<int>(type: "integer", nullable: true),
                    CategorieModele = table.Column<int>(type: "integer", nullable: true),
                    ValideePar = table.Column<string>(type: "text", nullable: true),
                    TriageLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CorrectionAncienne = table.Column<int>(type: "integer", nullable: true),
                    CorrectionNouvelle = table.Column<int>(type: "integer", nullable: true),
                    CorrectionMotif = table.Column<string>(type: "text", nullable: true),
                    CorrectionAuteur = table.Column<string>(type: "text", nullable: true),
                    CorrectionLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    DecisionAction = table.Column<string>(type: "text", nullable: true),
                    DecisionServiceId = table.Column<int>(type: "integer", nullable: true),
                    DecisionMotif = table.Column<string>(type: "text", nullable: true),
                    DecisionRecommandation = table.Column<string>(type: "text", nullable: true),
                    DecisionDivergence = table.Column<bool>(type: "boolean", nullable: false),
                    DecisionLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    xmin = table.Column<uint>(type: "xid", rowVersion: true, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Passages", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Passages_Patients_PatientId",
                        column: x => x.PatientId,
                        principalTable: "Patients",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Passages_Services_ServiceViseId",
                        column: x => x.ServiceViseId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateTable(
                name: "RendezVous",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Reference = table.Column<string>(type: "text", nullable: false),
                    PatientId = table.Column<int>(type: "integer", nullable: false),
                    ServiceId = table.Column<int>(type: "integer", nullable: false),
                    Date = table.Column<DateOnly>(type: "date", nullable: false),
                    Heure = table.Column<string>(type: "text", nullable: false),
                    Motif = table.Column<string>(type: "text", nullable: false),
                    Statut = table.Column<string>(type: "text", nullable: false),
                    Rappel = table.Column<string>(type: "text", nullable: true),
                    DemandeParPatient = table.Column<bool>(type: "boolean", nullable: false),
                    EstChirurgie = table.Column<bool>(type: "boolean", nullable: false),
                    DureeMinutes = table.Column<int>(type: "integer", nullable: true),
                    LitAvalServiceId = table.Column<int>(type: "integer", nullable: true),
                    DureeSejourJours = table.Column<int>(type: "integer", nullable: true),
                    PerteDeChance = table.Column<string>(type: "text", nullable: true),
                    SalleBloc = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RendezVous", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RendezVous_Patients_PatientId",
                        column: x => x.PatientId,
                        principalTable: "Patients",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RendezVous_Services_ServiceId",
                        column: x => x.ServiceId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Sejours",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    Reference = table.Column<string>(type: "text", nullable: false),
                    PatientId = table.Column<int>(type: "integer", nullable: false),
                    ServiceId = table.Column<int>(type: "integer", nullable: false),
                    LitId = table.Column<int>(type: "integer", nullable: true),
                    Entree = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    Sortie = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    MotifBlocage = table.Column<string>(type: "text", nullable: true),
                    Statut = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Sejours", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Sejours_Lits_LitId",
                        column: x => x.LitId,
                        principalTable: "Lits",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.SetNull);
                    table.ForeignKey(
                        name: "FK_Sejours_Patients_PatientId",
                        column: x => x.PatientId,
                        principalTable: "Patients",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Sejours_Services_ServiceId",
                        column: x => x.ServiceId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Triages",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    PassageId = table.Column<int>(type: "integer", nullable: false),
                    Pas = table.Column<int>(type: "integer", nullable: true),
                    Pad = table.Column<int>(type: "integer", nullable: true),
                    Fc = table.Column<int>(type: "integer", nullable: true),
                    Fr = table.Column<int>(type: "integer", nullable: true),
                    Temperature = table.Column<double>(type: "double precision", nullable: true),
                    Spo2 = table.Column<int>(type: "integer", nullable: true),
                    Glycemie = table.Column<double>(type: "double precision", nullable: true),
                    Poids = table.Column<double>(type: "double precision", nullable: true),
                    Avpu = table.Column<string>(type: "text", nullable: true),
                    Glasgow = table.Column<int>(type: "integer", nullable: true),
                    Eva = table.Column<int>(type: "integer", nullable: true),
                    CategorieManuelle = table.Column<int>(type: "integer", nullable: true),
                    EnregistreLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    EnregistrePar = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Triages", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Triages_Passages_PassageId",
                        column: x => x.PassageId,
                        principalTable: "Passages",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Demandes_ServiceId",
                table: "Demandes",
                column: "ServiceId");

            migrationBuilder.CreateIndex(
                name: "IX_Lits_ServiceId",
                table: "Lits",
                column: "ServiceId");

            migrationBuilder.CreateIndex(
                name: "IX_Parametres_Cle",
                table: "Parametres",
                column: "Cle",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Passages_PatientId",
                table: "Passages",
                column: "PatientId");

            migrationBuilder.CreateIndex(
                name: "IX_Passages_Reference",
                table: "Passages",
                column: "Reference",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Passages_ServiceViseId",
                table: "Passages",
                column: "ServiceViseId");

            migrationBuilder.CreateIndex(
                name: "IX_Passages_Statut",
                table: "Passages",
                column: "Statut");

            migrationBuilder.CreateIndex(
                name: "IX_Patients_Nom_Prenom",
                table: "Patients",
                columns: new[] { "Nom", "Prenom" });

            migrationBuilder.CreateIndex(
                name: "IX_Patients_Reference",
                table: "Patients",
                column: "Reference",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_PiecesJointes_PatientId",
                table: "PiecesJointes",
                column: "PatientId");

            migrationBuilder.CreateIndex(
                name: "IX_RendezVous_PatientId",
                table: "RendezVous",
                column: "PatientId");

            migrationBuilder.CreateIndex(
                name: "IX_RendezVous_ServiceId",
                table: "RendezVous",
                column: "ServiceId");

            migrationBuilder.CreateIndex(
                name: "IX_Sejours_LitId",
                table: "Sejours",
                column: "LitId");

            migrationBuilder.CreateIndex(
                name: "IX_Sejours_PatientId",
                table: "Sejours",
                column: "PatientId");

            migrationBuilder.CreateIndex(
                name: "IX_Sejours_ServiceId",
                table: "Sejours",
                column: "ServiceId");

            migrationBuilder.CreateIndex(
                name: "IX_Services_Code",
                table: "Services",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Services_EtablissementId",
                table: "Services",
                column: "EtablissementId");

            migrationBuilder.CreateIndex(
                name: "IX_Triages_PassageId",
                table: "Triages",
                column: "PassageId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Utilisateurs_Email",
                table: "Utilisateurs",
                column: "Email",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Audits");

            migrationBuilder.DropTable(
                name: "Demandes");

            migrationBuilder.DropTable(
                name: "Notifications");

            migrationBuilder.DropTable(
                name: "Parametres");

            migrationBuilder.DropTable(
                name: "PiecesJointes");

            migrationBuilder.DropTable(
                name: "Predictions");

            migrationBuilder.DropTable(
                name: "ReglesOrientation");

            migrationBuilder.DropTable(
                name: "RendezVous");

            migrationBuilder.DropTable(
                name: "Sejours");

            migrationBuilder.DropTable(
                name: "Triages");

            migrationBuilder.DropTable(
                name: "Utilisateurs");

            migrationBuilder.DropTable(
                name: "Lits");

            migrationBuilder.DropTable(
                name: "Passages");

            migrationBuilder.DropTable(
                name: "Patients");

            migrationBuilder.DropTable(
                name: "Services");

            migrationBuilder.DropTable(
                name: "Etablissements");
        }
    }
}
