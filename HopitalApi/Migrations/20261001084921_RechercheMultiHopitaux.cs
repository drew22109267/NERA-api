using System;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace HopitalApi.Migrations
{
    /// <inheritdoc />
    public partial class RechercheMultiHopitaux : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_Services_Code",
                table: "Services");

            migrationBuilder.DropIndex(
                name: "IX_Services_EtablissementId",
                table: "Services");

            migrationBuilder.AddColumn<string>(
                name: "DiagnosticEntree",
                table: "Sejours",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Issue",
                table: "Sejours",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "RoleRecherche",
                table: "Etablissements",
                type: "text",
                nullable: false,
                defaultValue: "");

            migrationBuilder.CreateTable(
                name: "ColonnesSource",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EtablissementId = table.Column<int>(type: "integer", nullable: false),
                    Registre = table.Column<string>(type: "text", nullable: false),
                    VariableCode = table.Column<string>(type: "text", nullable: false),
                    NomColonne = table.Column<string>(type: "text", nullable: true),
                    ValeurFixe = table.Column<string>(type: "text", nullable: true),
                    Note = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ColonnesSource", x => x.Id);
                    table.ForeignKey(
                        name: "FK_ColonnesSource_Etablissements_EtablissementId",
                        column: x => x.EtablissementId,
                        principalTable: "Etablissements",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Correspondances",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EtablissementId = table.Column<int>(type: "integer", nullable: false),
                    VariableCode = table.Column<string>(type: "text", nullable: false),
                    Cle = table.Column<string>(type: "text", nullable: false),
                    ValeurBrute = table.Column<string>(type: "text", nullable: false),
                    ValeurNormalisee = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Correspondances", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Correspondances_Etablissements_EtablissementId",
                        column: x => x.EtablissementId,
                        principalTable: "Etablissements",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "LotsImport",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EtablissementId = table.Column<int>(type: "integer", nullable: false),
                    Registre = table.Column<string>(type: "text", nullable: false),
                    ServiceParDefautId = table.Column<int>(type: "integer", nullable: true),
                    NomFichier = table.Column<string>(type: "text", nullable: false),
                    ImporteLe = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    ImportePar = table.Column<string>(type: "text", nullable: true),
                    LignesLues = table.Column<int>(type: "integer", nullable: false),
                    LignesImportees = table.Column<int>(type: "integer", nullable: false),
                    LignesRejetees = table.Column<int>(type: "integer", nullable: false),
                    Doublons = table.Column<int>(type: "integer", nullable: false),
                    RapportJson = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_LotsImport", x => x.Id);
                    table.ForeignKey(
                        name: "FK_LotsImport_Etablissements_EtablissementId",
                        column: x => x.EtablissementId,
                        principalTable: "Etablissements",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "Consultations",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EtablissementId = table.Column<int>(type: "integer", nullable: false),
                    ServiceId = table.Column<int>(type: "integer", nullable: true),
                    LotImportId = table.Column<int>(type: "integer", nullable: false),
                    NumeroLigne = table.Column<int>(type: "integer", nullable: false),
                    IdAnonyme = table.Column<string>(type: "text", nullable: true),
                    ServiceBrut = table.Column<string>(type: "text", nullable: true),
                    Date = table.Column<DateOnly>(type: "date", nullable: false),
                    AgeValeur = table.Column<double>(type: "double precision", nullable: true),
                    AgeUnite = table.Column<string>(type: "text", nullable: true),
                    AgeMois = table.Column<double>(type: "double precision", nullable: true),
                    SexeBrut = table.Column<string>(type: "text", nullable: true),
                    Sexe = table.Column<string>(type: "text", nullable: true),
                    Quartier = table.Column<string>(type: "text", nullable: true),
                    SymptomesBrut = table.Column<string>(type: "text", nullable: true),
                    Motif = table.Column<string>(type: "text", nullable: true),
                    Fc = table.Column<int>(type: "integer", nullable: true),
                    Pas = table.Column<int>(type: "integer", nullable: true),
                    Pad = table.Column<int>(type: "integer", nullable: true),
                    Fr = table.Column<int>(type: "integer", nullable: true),
                    Temperature = table.Column<double>(type: "double precision", nullable: true),
                    Spo2 = table.Column<int>(type: "integer", nullable: true),
                    Poids = table.Column<double>(type: "double precision", nullable: true),
                    OrientationBrute = table.Column<string>(type: "text", nullable: true),
                    Orientation = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Consultations", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Consultations_Etablissements_EtablissementId",
                        column: x => x.EtablissementId,
                        principalTable: "Etablissements",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Consultations_LotsImport_LotImportId",
                        column: x => x.LotImportId,
                        principalTable: "LotsImport",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Consultations_Services_ServiceId",
                        column: x => x.ServiceId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Hospitalisations",
                columns: table => new
                {
                    Id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityByDefaultColumn),
                    EtablissementId = table.Column<int>(type: "integer", nullable: false),
                    ServiceId = table.Column<int>(type: "integer", nullable: true),
                    LotImportId = table.Column<int>(type: "integer", nullable: false),
                    NumeroLigne = table.Column<int>(type: "integer", nullable: false),
                    IdAnonyme = table.Column<string>(type: "text", nullable: true),
                    ServiceBrut = table.Column<string>(type: "text", nullable: true),
                    DateEntree = table.Column<DateOnly>(type: "date", nullable: false),
                    DateSortie = table.Column<DateOnly>(type: "date", nullable: true),
                    DureeJoursDeclaree = table.Column<int>(type: "integer", nullable: true),
                    AgeValeur = table.Column<double>(type: "double precision", nullable: true),
                    AgeUnite = table.Column<string>(type: "text", nullable: true),
                    AgeMois = table.Column<double>(type: "double precision", nullable: true),
                    SexeBrut = table.Column<string>(type: "text", nullable: true),
                    Sexe = table.Column<string>(type: "text", nullable: true),
                    Quartier = table.Column<string>(type: "text", nullable: true),
                    DiagnosticEntreeBrut = table.Column<string>(type: "text", nullable: true),
                    DiagnosticEntree = table.Column<string>(type: "text", nullable: true),
                    Bilan = table.Column<string>(type: "text", nullable: true),
                    TraitementInitial = table.Column<string>(type: "text", nullable: true),
                    DiagnosticSortieBrut = table.Column<string>(type: "text", nullable: true),
                    DiagnosticSortie = table.Column<string>(type: "text", nullable: true),
                    TraitementSortie = table.Column<string>(type: "text", nullable: true),
                    IssueBrute = table.Column<string>(type: "text", nullable: true),
                    Issue = table.Column<string>(type: "text", nullable: true),
                    Prix = table.Column<decimal>(type: "numeric(14,2)", precision: 14, scale: 2, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Hospitalisations", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Hospitalisations_Etablissements_EtablissementId",
                        column: x => x.EtablissementId,
                        principalTable: "Etablissements",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Hospitalisations_LotsImport_LotImportId",
                        column: x => x.LotImportId,
                        principalTable: "LotsImport",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_Hospitalisations_Services_ServiceId",
                        column: x => x.ServiceId,
                        principalTable: "Services",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Services_EtablissementId_Code",
                table: "Services",
                columns: new[] { "EtablissementId", "Code" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ColonnesSource_EtablissementId_Registre_VariableCode",
                table: "ColonnesSource",
                columns: new[] { "EtablissementId", "Registre", "VariableCode" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Consultations_EtablissementId_ServiceId_Date",
                table: "Consultations",
                columns: new[] { "EtablissementId", "ServiceId", "Date" });

            migrationBuilder.CreateIndex(
                name: "IX_Consultations_LotImportId",
                table: "Consultations",
                column: "LotImportId");

            migrationBuilder.CreateIndex(
                name: "IX_Consultations_ServiceId",
                table: "Consultations",
                column: "ServiceId");

            migrationBuilder.CreateIndex(
                name: "IX_Correspondances_EtablissementId_VariableCode_Cle",
                table: "Correspondances",
                columns: new[] { "EtablissementId", "VariableCode", "Cle" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Hospitalisations_EtablissementId_ServiceId_DateEntree",
                table: "Hospitalisations",
                columns: new[] { "EtablissementId", "ServiceId", "DateEntree" });

            migrationBuilder.CreateIndex(
                name: "IX_Hospitalisations_LotImportId",
                table: "Hospitalisations",
                column: "LotImportId");

            migrationBuilder.CreateIndex(
                name: "IX_Hospitalisations_ServiceId",
                table: "Hospitalisations",
                column: "ServiceId");

            migrationBuilder.CreateIndex(
                name: "IX_LotsImport_EtablissementId",
                table: "LotsImport",
                column: "EtablissementId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ColonnesSource");

            migrationBuilder.DropTable(
                name: "Consultations");

            migrationBuilder.DropTable(
                name: "Correspondances");

            migrationBuilder.DropTable(
                name: "Hospitalisations");

            migrationBuilder.DropTable(
                name: "LotsImport");

            migrationBuilder.DropIndex(
                name: "IX_Services_EtablissementId_Code",
                table: "Services");

            migrationBuilder.DropColumn(
                name: "DiagnosticEntree",
                table: "Sejours");

            migrationBuilder.DropColumn(
                name: "Issue",
                table: "Sejours");

            migrationBuilder.DropColumn(
                name: "RoleRecherche",
                table: "Etablissements");

            migrationBuilder.CreateIndex(
                name: "IX_Services_Code",
                table: "Services",
                column: "Code",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Services_EtablissementId",
                table: "Services",
                column: "EtablissementId");
        }
    }
}
