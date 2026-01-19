#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/immobilier/lkeria/vente-studio"
python3 main.py
deactivate