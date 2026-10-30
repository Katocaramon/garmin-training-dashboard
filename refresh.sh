#!/bin/bash
# Scarica i dati nuovi da Garmin e ricostruisce la dashboard.
cd "$(dirname "$0")" || exit 1
python3 pull.py || { echo "Download non riuscito: controlla .env.local (la chiave potrebbe essere scaduta)."; exit 1; }
python3 build.py && open dashboard.html
