#!/bin/bash
set -euo pipefail

###############################################################################
# Kloufi - Crawl All (stable version)
###############################################################################

BASE="/home/joaquim/kloufi-scrap"
LOG_BASE="$BASE/logs"
LOCK="/tmp/kloufi-crawl-all.lock"

MAX_JOBS=30
TIMEOUT_JOB="120m"
SLEEP_CHECK=2

ulimit -u 500
ulimit -n 8192

###############################################################################
# CLEANUP
###############################################################################
cleanup() {
  echo "$(date '+%F %T') - CLEANUP"
  pkill -P $$ 2>/dev/null || true
  pkill -f playwright 2>/dev/null || true
}
trap cleanup EXIT INT TERM

###############################################################################
# PRE-CLEAN (AVANT LOCK)
###############################################################################
pkill -f "$BASE" 2>/dev/null || true
pkill -f playwright 2>/dev/null || true

###############################################################################
# LOCK
###############################################################################
exec 9>"$LOCK" || exit 1
flock -n 9 || exit 0

###############################################################################
# LOG GLOBAL
###############################################################################
exec >> "$LOG_BASE/crawl-all.log" 2>&1

echo "==================================================================="
echo "$(date '+%F %T') - START crawl-all"
echo "MAX_JOBS=$MAX_JOBS | TIMEOUT=$TIMEOUT_JOB"

###############################################################################
# RUNNER
###############################################################################
run() {
  local script="$1"
  local logfile="$2"

  while (( $(jobs -rp | wc -l) >= MAX_JOBS )); do
    sleep "$SLEEP_CHECK"
  done

  timeout --kill-after=60s "$TIMEOUT_JOB" \
    bash "$script" >> "$logfile" 2>&1 &
}


###############################################################################
# IMMOBILIER
###############################################################################
run "$BASE/sh/immobilier/beytic/vente.sh"           "$LOG_BASE/immobilier/beytic/vente.log"
run "$BASE/sh/immobilier/beytic/location.sh"        "$LOG_BASE/immobilier/beytic/location.log"
run "$BASE/sh/immobilier/lkeria/vente.sh"           "$LOG_BASE/immobilier/lkeria/vente.log"
run "$BASE/sh/immobilier/lkeria/vente-studio.sh"    "$LOG_BASE/immobilier/lkeria/vente-studio.log"
run "$BASE/sh/immobilier/lkeria/location.sh"        "$LOG_BASE/immobilier/lkeria/location.log"
run "$BASE/sh/immobilier/algerieannonces/vente.sh"  "$LOG_BASE/immobilier/algerieannonces/vente.log"
run "$BASE/sh/immobilier/algerieannonces/location.sh" "$LOG_BASE/immobilier/algerieannonces/location.log"
run "$BASE/sh/immobilier/krello.sh"                 "$LOG_BASE/immobilier/krello.log"
run "$BASE/sh/immobilier/ouedkniss/vente-appartement.sh" "$LOG_BASE/immobilier/ouedkniss/vente-appartement.log"
run "$BASE/sh/immobilier/ouedkniss/vente-villa.sh"       "$LOG_BASE/immobilier/ouedkniss/vente-villa.log"
run "$BASE/sh/immobilier/ouedkniss/vente-terrain.sh"     "$LOG_BASE/immobilier/ouedkniss/vente-terrain.log"
run "$BASE/sh/immobilier/ouedkniss/location-appartement.sh" "$LOG_BASE/immobilier/ouedkniss/location-appartement.log"
run "$BASE/sh/immobilier/ouedkniss/location-vacances.sh" "$LOG_BASE/immobilier/ouedkniss/location-vacances.log"
run "$BASE/sh/immobilier/residencedz/location.sh"    "$LOG_BASE/immobilier/residencedz/location.log"
run "$BASE/sh/immobilier/residencedz/vente.sh"       "$LOG_BASE/immobilier/residencedz/vente.log"


###############################################################################
# VOITURE
###############################################################################
run "$BASE/sh/voiture/tonobiles.sh"              "$LOG_BASE/voiture/tonobiles.log"
run "$BASE/sh/voiture/ouedkniss.sh"               "$LOG_BASE/voiture/ouedkniss.log"
run "$BASE/sh/voiture/autobessah.sh"               "$LOG_BASE/voiture/autobessah.log"
run "$BASE/sh/voiture/cardias.sh"                  "$LOG_BASE/voiture/cardias.log"
run "$BASE/sh/voiture/autoexportmarseille.sh"      "$LOG_BASE/voiture/autoexportmarseille.log"
run "$BASE/sh/voiture/dickreich.sh"                "$LOG_BASE/voiture/dickreich.log"
run "$BASE/sh/voiture/djcar.sh"                     "$LOG_BASE/voiture/djcar.log"
run "$BASE/sh/voiture/easyexport-neuf.sh"           "$LOG_BASE/voiture/easyexport-neuf.log"
run "$BASE/sh/voiture/easyexport-occasion.sh"       "$LOG_BASE/voiture/easyexport-occasion.log"
run "$BASE/sh/voiture/algerieannonces.sh"           "$LOG_BASE/voiture/algerieannonces.log"
run "$BASE/sh/voiture/autocango.sh"                 "$LOG_BASE/voiture/autocango.log"
run "$BASE/sh/voiture/mobile.sh"                    "$LOG_BASE/voiture/mobile.log"

###############################################################################
# EMPLOI
###############################################################################
run "$BASE/sh/emploi/algeriejob.sh"                 "$LOG_BASE/emploi/algeriejob.log"
run "$BASE/sh/emploi/emploitic.sh"                  "$LOG_BASE/emploi/emploitic.log"
run "$BASE/sh/emploi/ouedkniss-offres.sh"           "$LOG_BASE/emploi/ouedkniss-offres.log"
run "$BASE/sh/emploi/ouedkniss-demandes.sh"         "$LOG_BASE/emploi/ouedkniss-demandes.log"
run "$BASE/sh/emploi/emploipartner.sh"              "$LOG_BASE/emploi/emploipartner.log"

###############################################################################
# ELECTROMENAGER
###############################################################################
run "$BASE/sh/electromenager/homecenterdz.sh"       "$LOG_BASE/electromenager/homecenterdz.log"
run "$BASE/sh/electromenager/starmania.sh"          "$LOG_BASE/electromenager/starmania.log"
run "$BASE/sh/electromenager/websoog.sh"            "$LOG_BASE/electromenager/websoog.log"
run "$BASE/sh/electromenager/jumia.sh"              "$LOG_BASE/electromenager/jumia.log"

###############################################################################
# MULTIMEDIA
###############################################################################
run "$BASE/sh/multimedia/jumia-laptops.sh"          "$LOG_BASE/multimedia/jumia-laptops.log"
run "$BASE/sh/multimedia/jumia.sh"                  "$LOG_BASE/multimedia/jumia.log"
run "$BASE/sh/multimedia/ajini.sh"                  "$LOG_BASE/multimedia/ajini.log"

###############################################################################
# WAIT
###############################################################################
wait

echo "$(date '+%F %T') - END crawl-all"
echo "==================================================================="
