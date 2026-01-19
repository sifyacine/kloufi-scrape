#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/multimedia/webstar-electro"
python3 main.py
deactivate
