#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/multimedia/algerieannonces"
python3 main.py
deactivate
