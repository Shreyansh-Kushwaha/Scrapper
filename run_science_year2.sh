#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  Aus Science Year 2 — 1-worker scraper
#  Usage:
#    Step 1 (once):   bash run_science_year2.sh setup
#    Step 2 (always): bash run_science_year2.sh worker0
#
#  If interrupted, just re-run worker0 again.
#  The checkpoint system skips already-completed skills.
# ─────────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

USERNAME="supersheldon2"
PASSWORD="97r&^FX#!%p^"
SUBJECT="science"
YEAR="year-2"
OUT="output/science/year-2"

case "$1" in

  setup)
    echo "Fetching Year 2 Science skill list..."
    mkdir -p "$OUT/worker_0"
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
open('$OUT/_batch_0.json','w').write(json.dumps(skills))
print(f'Done. {len(skills)} skills found.')
print('Now run: bash run_science_year2.sh worker0')
"
    ;;

  worker0)
    echo "Starting Worker 0..."
    python3 ixl_scraper_ui.py \
      --subject "$SUBJECT" --year "$YEAR" \
      --username "$USERNAME" --password "$PASSWORD" \
      --output-dir "$OUT/worker_0" \
      --skills-file "$OUT/_batch_0.json" \
      --mcq-only --headless
    ;;

  *)
    echo "Usage: bash run_science_year2.sh [setup|worker0]"
    ;;

esac
