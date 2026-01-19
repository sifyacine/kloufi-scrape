#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/immobilier/hebdoimmobilier-dz"
python3 main.py
deactivate
