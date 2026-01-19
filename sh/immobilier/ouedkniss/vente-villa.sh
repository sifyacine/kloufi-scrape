#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/immobilier/ouedkniss"
python3 main.py --transaction vente --bien villa
deactivate
