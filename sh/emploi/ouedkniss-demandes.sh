#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/emploi/ouedkniss-demandes"
python3 main.py
deactivate