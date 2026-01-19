#!/bin/bash
BASE="/home/joaquim/kloufi-scrap"
source "$BASE/venv/bin/activate"
cd "$BASE/sites/electromenager/diardzair"
python3 main.py
deactivate
