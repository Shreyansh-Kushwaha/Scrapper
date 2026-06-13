#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  Aus Maths Year 6 — 3-worker scraper
#  Usage:
#    Step 1 (once):   bash run_maths_year6.sh setup
#    Step 2 (always): bash run_maths_year6.sh worker0    ← Terminal 1
#    Step 3 (always): bash run_maths_year6.sh worker1    ← Terminal 2
#    Step 4 (always): bash run_maths_year6.sh worker2    ← Terminal 3
#
#  If interrupted, just re-run the worker again.
#  The checkpoint system skips already-completed skills.
# ─────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

USERNAME="supersheldon2"
PASSWORD="97r&^FX#!%p^"
SUBJECT="maths"
YEAR="year-6"
OUT="output/maths/year-6"

case "$1" in

  setup)
    echo "Fetching Year 6 Maths skill list and splitting into 3 batches..."
    mkdir -p "$OUT/worker_0" "$OUT/worker_1" "$OUT/worker_2"
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
open('$OUT/_batch_0.json','w').write(json.dumps(skills[0::3]))
open('$OUT/_batch_1.json','w').write(json.dumps(skills[1::3]))
open('$OUT/_batch_2.json','w').write(json.dumps(skills[2::3]))
print(f'Done. Batch 0: {len(skills[0::3])} | Batch 1: {len(skills[1::3])} | Batch 2: {len(skills[2::3])} skills')
print('Now run worker0, worker1, worker2 in separate terminals.')
"
    ;;

  worker0)
    echo "Starting Worker 0 (batch 0)..."
    python3 ixl_scraper_ui.py \
      --subject "$SUBJECT" --year "$YEAR" \
      --username "$USERNAME" --password "$PASSWORD" \
      --output-dir "$OUT/worker_0" \
      --skills-file "$OUT/_batch_0.json" \
      --mcq-only --headless
    ;;

  worker1)
    echo "Starting Worker 1 (batch 1)..."
    python3 ixl_scraper_ui.py \
      --subject "$SUBJECT" --year "$YEAR" \
      --username "$USERNAME" --password "$PASSWORD" \
      --output-dir "$OUT/worker_1" \
      --skills-file "$OUT/_batch_1.json" \
      --mcq-only --headless
    ;;

  worker2)
    echo "Starting Worker 2 (batch 2)..."
    python3 ixl_scraper_ui.py \
      --subject "$SUBJECT" --year "$YEAR" \
      --username "$USERNAME" --password "$PASSWORD" \
      --output-dir "$OUT/worker_2" \
      --skills-file "$OUT/_batch_2.json" \
      --mcq-only --headless
    ;;

  *)
    echo "Usage: bash run_maths_year6.sh [setup|worker0|worker1|worker2]"
    ;;

esac
