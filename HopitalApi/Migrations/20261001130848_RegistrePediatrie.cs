using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HopitalApi.Migrations
{
    /// <inheritdoc />
    public partial class RegistrePediatrie : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "AncienNouveau",
                table: "Hospitalisations",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "AncienNouveauBrut",
                table: "Hospitalisations",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<DateOnly>(
                name: "DateEnregistrement",
                table: "Hospitalisations",
                type: "date",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "DateSortieCalculee",
                table: "Hospitalisations",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<double>(
                name: "DensiteParasitaire",
                table: "Hospitalisations",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Fc",
                table: "Hospitalisations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Fr",
                table: "Hospitalisations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "GeTdr",
                table: "Hospitalisations",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "GeTdrBrut",
                table: "Hospitalisations",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Pad",
                table: "Hospitalisations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Pas",
                table: "Hospitalisations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "Poids",
                table: "Hospitalisations",
                type: "double precision",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "Spo2",
                table: "Hospitalisations",
                type: "integer",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "Temperature",
                table: "Hospitalisations",
                type: "double precision",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AncienNouveau",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "AncienNouveauBrut",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "DateEnregistrement",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "DateSortieCalculee",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "DensiteParasitaire",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Fc",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Fr",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "GeTdr",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "GeTdrBrut",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Pad",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Pas",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Poids",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Spo2",
                table: "Hospitalisations");

            migrationBuilder.DropColumn(
                name: "Temperature",
                table: "Hospitalisations");
        }
    }
}
