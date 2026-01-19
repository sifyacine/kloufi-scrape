#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/immobilier/algeriahome/location"
python3 main.py
deactivate
