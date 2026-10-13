@echo off
rem Convertit les photos d'un registre (HEIC, JPEG, PNG) en JPEG lisibles par saisie.html.
rem Les originaux ne sont jamais modifies ; les metadonnees (GPS, date, telephone) sont supprimees.
rem Double-cliquer, puis indiquer le dossier des photos originales et le dossier de sortie.
cd /d "%~dp0"
set /p SOURCE=Dossier des photos originales (ex. C:\Registres\pediatrie) :
set /p DESTINATION=Dossier de sortie (ex. photos_pediatrie) :
if "%DESTINATION%"=="" set DESTINATION=photos_converties
powershell -NoProfile -ExecutionPolicy Bypass -File "convertir_photos.ps1" -Source "%SOURCE%" -Destination "%DESTINATION%"
pause
