#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/emploi/ouedkniss-offres"
python3 main.py
deactivate