#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Toute la chaîne du mémoire, dans l'ordre, sur la dernière version de la saisie.
#
# À relancer à chaque nouvelle version du fichier exporté par l'outil de saisie (« Aperçu » →
# exporter tous les mois). Les données ne quittent pas l'ordinateur : donnees/ et resultats/
# ne sont jamais envoyés sur GitHub.
#
# Usage (dans un terminal Ubuntu / WSL, depuis le dossier modeles) :
#     bash lancer_tout.sh                       # tout, sauf la recherche longue des paramètres
#     ETAPES="1 2" bash lancer_tout.sh          # seulement certaines étapes
#     RAPIDE=1 bash lancer_tout.sh              # essai rapide (moins d'itérations)
#
# Réglages (variables d'environnement, valeurs par défaut entre crochets) :
#     SOURCE     CSV exporté de l'outil  [/mnt/c/Users/User/Desktop/MEMOIRE/saisie_ia/registre-ped-tous-les-mois.csv]
#     LITS       capacité de référence  [20]
#     LITS_FICHIER  capacité variable (date_debut;lits), si la date du passage de 15 à 20 lits est connue
#     COMPTAGES  méthodes de comptage   ["minuit journee"]
#     HORIZONS   horizons en jours      ["1 7"]
#
# Étapes :
#     1  conversion du CSV de l'outil et reconstitution de l'occupation (+ scénarios de 15 à 20 lits)
#     2  entraînement des niveaux 0 à 5 avec recherche des hyperparamètres par grille
#     3  banc des choix de conception (D1 à D11 : 23 modèles, noyau, perte, τ, variables…)
#     4  banc du prétraitement (P1 à P8)
#     5  sensibilité de chaque paramètre
#     6  sensibilité à la convention des jours
#     7  toutes les figures
#     8  modèle de survie J0 / J1 / J2
# La validation finale (septembre-octobre 2026) n'est PAS lancée ici : une seule fois, à la fin.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
set -u
cd "$(dirname "$0")"
PY="${PY:-$HOME/memoire-env/bin/python}"
SOURCE="${SOURCE:-/mnt/c/Users/User/Desktop/MEMOIRE/saisie_ia/registre-ped-tous-les-mois.csv}"
LITS="${LITS:-20}"
COMPTAGES="${COMPTAGES:-minuit journee}"
HORIZONS="${HORIZONS:-1 7}"
ETAPES="${ETAPES:-1 2 3 4 5 6 7 8}"
RAPIDE_OPT=""; [ "${RAPIDE:-0}" = "1" ] && RAPIDE_OPT="--rapide"
CAPACITE="--lits $LITS"; [ -n "${LITS_FICHIER:-}" ] && CAPACITE="--lits-fichier $LITS_FICHIER"
JOURNAL=resultats/journaux; mkdir -p "$JOURNAL" donnees
EXPORT=donnees/export_outil_PED.csv

etape() { [[ " $ETAPES " == *" $1 "* ]]; }
lancer() {   # lancer <nom du journal> <commande…> : affiche le début et la fin, garde tout dans le journal
  local nom=$1; shift
  echo "── $(date '+%H:%M') $nom"
  if "$@" > "$JOURNAL/$nom.log" 2>&1; then echo "   terminé ($JOURNAL/$nom.log)"; else echo "   ÉCHEC : voir $JOURNAL/$nom.log"; tail -5 "$JOURNAL/$nom.log"; fi
}

if etape 1; then
  lancer conversion "$PY" -m nera.depuis_outil "$SOURCE" --service PED --sortie "$EXPORT"
  for c in $COMPTAGES; do
    lancer "occupation_$c" "$PY" rapport_occupation.py "$EXPORT" --service PED $CAPACITE --inconnues estimee \
      --fenetre-censure p95 --rodage-debut --comptage "$c" --scenarios-lits 15 16 17 18 19 20
  done
fi
for c in $COMPTAGES; do
  etape 2 && lancer "niveaux_$c" "$PY" lancer_niveaux.py --service PED --horizons $HORIZONS --tau 0.8 --recherche grille --comptage "$c"
  etape 3 && lancer "banc_choix_$c" "$PY" benchmark_choix.py --service PED --horizons $HORIZONS --comptage "$c" $RAPIDE_OPT
  etape 5 && lancer "banc_parametres_$c" "$PY" benchmark_parametres.py --service PED --horizons $HORIZONS --comptage "$c" $RAPIDE_OPT
  etape 6 && lancer "sensibilite_$c" "$PY" sensibilite.py --service PED --horizons $HORIZONS --comptage "$c"
  etape 7 && lancer "figures_$c" "$PY" visualisations.py --service PED --comptage "$c" $RAPIDE_OPT
done
etape 4 && lancer banc_pretraitement "$PY" benchmark_pretraitement.py "$EXPORT" --service PED --lits "$LITS" --horizons $HORIZONS $RAPIDE_OPT
etape 8 && lancer survie "$PY" modele_survie.py "$EXPORT" --service PED --lits "$LITS" --causes
echo "── $(date '+%H:%M') fini. Rapports : resultats/*.md · tableaux : resultats/*.csv · figures : resultats/figures_*/"
