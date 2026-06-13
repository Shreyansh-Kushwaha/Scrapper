#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  Year 9 English — 2-worker scraper
#  Usage:
#    Step 1 (once):   bash run_year9.sh setup
#    Step 2 (always): bash run_year9.sh worker0    ← Terminal 1
#    Step 3 (always): bash run_year9.sh worker1    ← Terminal 2
#
#  If interrupted, just re-run worker0 / worker1 again.
#  The checkpoint system skips already-completed skills.
# ─────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

USERNAME="supersheldon2"
PASSWORD="97r&^FX#!%p^"
SUBJECT="english"
YEAR="year-9"
OUT="output/english/year-9"

case "$1" in

  setup)
    echo "Fetching Year 9 skill list and splitting into 2 batches..."
    mkdir -p "$OUT/worker_0" "$OUT/worker_1"
    python3 -c "
import json, subprocess
result = subprocess.run(
    ['python3','ixl_scraper_ui.py',
     '--subject','$SUBJECT','--year','$YEAR',
     '--username','$USERNAME','--password','$PASSWORD',
     '--discover-only','--headless'],
    capture_output=True, text=True
)
skills = json.loads([l[8:] for l in result.stdout.splitlines() if l.startswith('[SKILLS]')][0])
open('$OUT/_batch_0.json','w').write(json.dumps(skills[::2]))
open('$OUT/_batch_1.json','w').write(json.dumps(skills[1::2]))
print(f'Done. Batch 0: {len(skills[::2])} skills | Batch 1: {len(skills[1::2])} skills')
print('Now run:  bash run_year9.sh worker0   (Terminal 1)')
print('     and: bash run_year9.sh worker1   (Terminal 2, wait ~10s)')
"
    ;;

  worker0)
    echo "Starting Worker 0 (batch 0)..."
    python3 ixl_scraper_ui.py \
      --subject "$SUBJECT" \
      --year "$YEAR" \
      --username "$USERNAME" \
      --password "$PASSWORD" \
      --output-dir "$OUT/worker_0" \
      --skills-file "$OUT/_batch_0.json" \
      --mcq-only \
      --headless
    ;;

  worker1)
    echo "Starting Worker 1 (batch 1)..."
    python3 ixl_scraper_ui.py \
      --subject "$SUBJECT" \
      --year "$YEAR" \
      --username "$USERNAME" \
      --password "$PASSWORD" \
      --output-dir "$OUT/worker_1" \
      --skills-file "$OUT/_batch_1.json" \
      --mcq-only \
      --headless
    ;;

  *)
    echo "Usage: bash run_year9.sh [setup|worker0|worker1]"
    echo ""
    echo "  setup    — fetch skills and create batch files (run once)"
    echo "  worker0  — run worker 0 in Terminal 1"
    echo "  worker1  — run worker 1 in Terminal 2 (wait ~10s after worker0)"
    ;;

esac
