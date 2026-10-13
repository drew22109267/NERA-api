#!/usr/bin/env bash
# Lance l'API dans WSL (Ubuntu), hors de portée de Smart App Control.
#
# - Le code source reste dans le dossier Windows (backend/HopitalApi) : on le modifie
#   comme d'habitude, puis on relance ce script.
# - La compilation se fait dans ~/hopital-build (disque Linux, plus rapide) pour ne pas
#   mélanger les fichiers bin/obj de Windows et de Linux.
# - L'API tourne depuis le dossier Windows : même appsettings.json, même dossier
#   « stockage » pour les pièces jointes, même base PostgreSQL (Windows, via localhost).
set -euo pipefail

SOURCE="/mnt/c/Users/User/Desktop/backend/HopitalApi"
BUILD="$HOME/hopital-build"
DOTNET="$HOME/.dotnet/dotnet"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

echo "→ Copie du code source…"
mkdir -p "$BUILD/src"
rsync -a --delete --exclude bin/ --exclude obj/ --exclude stockage/ "$SOURCE/" "$BUILD/src/"

echo "→ Compilation…"
"$DOTNET" build "$BUILD/src/HopitalApi.csproj" -c Debug -o "$BUILD/out" -nologo -v quiet

echo "→ Démarrage sur http://localhost:5080 (Ctrl+C pour arrêter)"
cd "$SOURCE"
ASPNETCORE_URLS="http://localhost:5080" ASPNETCORE_ENVIRONMENT="Development" exec "$DOTNET" "$BUILD/out/HopitalApi.dll"
