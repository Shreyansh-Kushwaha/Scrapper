# IXL Scraper UI Dashboard — Design Spec

**Date:** 2026-06-03  
**Status:** Approved

---

## 1. Goal

Replace command-line scraper invocations with a browser-based dashboard that lets you:
1. **Configure** — pick subject, year, credentials, and options
2. **Launch & monitor** — start a scrape and watch live log output with progress stats
3. **Review** — browse, filter, and export the scraped questions

---

## 2. Scope

### Subjects
- Maths, English, Science (3 subjects)

### Year groups
- Reception, Year 1 through Year 13 (14 year groups)
- Total combinations: 42

### Question types scraped
| Type | Action |
|------|--------|
| Multiple Choice (MCQ) | Scrape — capture stem + 4 options + correct answer |
| Fill in Blank | Scrape — capture stem + correct answer(s) |
| Word Bank | Scrape — capture stem + word pool + correct placements |
| Click to Select | Scrape — capture stem + selectable items + correct selection |
| Sort / Sequence | Scrape — capture items + correct order |
| Drag and Drop | Scrape — capture items + correct mapping |
| Matching | Scrape — capture pairs |
| Audio-based | **Skip** — not scrapeable without audio playback |
| Interactive Graph / Canvas | **Skip** — requires drawing on canvas |

### Images
All `<img>` tags inside question HTML are downloaded, deduplicated by MD5 hash, and saved to `output/{subject}/{year}/images/`. The `image_paths` field in each question JSON references the local filenames.

---

## 3. Architecture

```
Browser (Vanilla JS + HTML)
  │
  ├── GET  /              → Serves index.html (single page, 3 tabs)
  ├── POST /run           → Spawns unified scraper subprocess → returns {run_id}
  ├── GET  /stream        → SSE endpoint — streams subprocess stdout line-by-line
  ├── POST /stop          → Kills the running subprocess
  ├── GET  /api/questions → Returns questions JSON for the review table
  └── GET  /api/runs      → Lists completed scrape runs (for review tab selector)
  
Flask App (app.py)
  │
  ├── subprocess.Popen(["python3", "ixl_scraper_ui.py",
  │       "--subject", subject, "--year", year,
  │       "--max-questions", max_q, "--output-dir", output_dir,
  │       "--headless", headless], stdout=PIPE, stderr=STDOUT)
  │
  └── Output: output/{subject}/{year}/questions.json  +  images/
```

- One Flask app, port 5000
- A global `running` lock — only one scraper process at a time
- No database — output JSON files are the source of truth

---

## 4. New Unified Scraper: `ixl_scraper_ui.py`

The existing scrapers (`ixl_scraper_full.py`, `ixl_year1_5_scraper.py`) are hardcoded to specific URLs and subjects. A new unified scraper replaces them for UI-driven runs.

### CLI interface
```
python3 ixl_scraper_ui.py \
  --subject maths \
  --year year-12 \
  --username supersheldon1 \
  --password "..." \
  --max-questions 50 \
  --output-dir output/maths/year-12 \
  --headless
```

### URL construction
| Year group | IXL URL slug |
|------------|-------------|
| Reception | `reception` |
| Year 1–13 | `year-1` … `year-13` |

Full URL: `https://uk.ixl.com/{subject}/{year_slug}`  
e.g. `https://uk.ixl.com/maths/year-12`, `https://uk.ixl.com/english/reception`

### Progress output (printed to stdout — parsed by Flask/SSE)
The scraper prints structured lines so the UI can parse stats without refactoring the scraper:
```
[START] subject=maths year=year-12 total_skills=290
[SKILL] 1/290 Solve linear equations
[QUESTION] q=1 format=fill-in-blank
[QUESTION] q=2 format=fill-in-blank
[SKILL_DONE] questions=24
[SKIP] format=interactive-graph skill=Plot a function
[DONE] total_questions=5600 elapsed=6420s
[ERROR] Login failed — check credentials
```

### Question JSON schema (per question)
```json
{
  "question_id":    "ixl-maths-year-12-solve-linear-equations-q1",
  "subject":        "maths",
  "year":           "year-12",
  "skill_name":     "Solve linear equations",
  "skill_url":      "https://uk.ixl.com/maths/year-12/solve-linear-equations",
  "question_index": 1,
  "format":         "fill-in-blank",
  "question_text":  "Solve for c. -17c = -19c - 10. c =",
  "options":        [],
  "correct_answer": "-20",
  "blank_count":    1,
  "has_image":      false,
  "image_paths":    [],
  "scraped_at":     "2026-06-03T07:15:01Z",
  "quiz_ready":     true
}
```

### Image handling
- All `<img>` elements inside the question container are fetched
- Saved as `{md5_hash}.jpg` in `output/{subject}/{year}/images/`
- Skipped if already present (MD5 cache) — reuses logic from `ixl_image_scraper.py`
- `image_paths` in the question JSON lists filenames (relative to output dir)

### Skipped question types
When a question is skipped (audio, interactive graph), the scraper prints `[SKIP]` and moves on — no entry written to the output JSON. The final `[DONE]` line includes a `skipped=N` count.

---

## 5. UI — Three-Tab Dashboard

### Tab 1: Configure & Launch
| Field | Type | Options |
|-------|------|---------|
| Subject | Dropdown | Maths, English, Science |
| Year | Dropdown | Reception, Year 1 … Year 13 |
| IXL Username | Text input | Pre-filled from last run |
| IXL Password | Password input | |
| Max questions per skill | Number | Default: 0 = repeat-detection mode (stops when same stem seen twice); set >0 to override with a hard cap |
| Headless mode | Toggle | Default: on |
| Run button | Button | Disabled while a run is active |
| Status indicator | Text | "No scraper running" / "Running: maths year-12" |

### Tab 2: Live Progress
- **Stats bar** (4 cards): Skills Done, Questions Found, Skipped, Est. Time Left
  - Parsed from `[SKILL_DONE]`, `[QUESTION]`, `[SKIP]`, `[START]` lines
  - Est. Time Left = `(elapsed_seconds / skills_done) × skills_remaining` — updated after each `[SKILL_DONE]`
- **Log panel**: scrollable monospace area, auto-scrolls to bottom
  - `[SKILL]` lines shown in indigo
  - `[SKIP]` lines shown in amber
  - `[ERROR]` lines shown in red
  - `[DONE]` line shown in green
- **Stop button**: POST `/stop`, shown only while running

### Tab 3: Review Data
- **Run selector** dropdown — pick which completed `subject/year` run to view
- **Filters**: Subject, Year (pre-filled from run selector), Format (All / MCQ / Fill in Blank / etc.)
- **Search**: full-text filter on question_text
- **Table**: Skill | Format badge | Question text | Answer | Has image
- **Export CSV** button — downloads filtered view as CSV

---

## 6. File Structure

```
scrapper/
├── app.py                        # Flask app — all routes + SSE streaming
├── ixl_scraper_ui.py             # New unified scraper (all subjects/years)
├── templates/
│   └── index.html                # Single HTML page, 3 tabs
├── static/
│   └── app.js                    # SSE listener, tab logic, stats parsing
├── output/
│   ├── maths/
│   │   └── year-12/
│   │       ├── questions.json
│   │       └── images/
│   ├── english/
│   │   └── year-9/
│   │       ├── questions.json
│   │       └── images/
│   └── science/
│       └── year-7/
│           ├── questions.json
│           └── images/
└── docs/superpowers/specs/
    └── 2026-06-03-scraper-ui-design.md
```

Existing scraper scripts (`ixl_scraper_full.py`, `ixl_year1_5_scraper.py`, etc.) are kept as-is — the new `ixl_scraper_ui.py` is additive.

---

## 7. Data Flow — SSE Streaming

1. User selects subject + year, enters credentials, clicks **Run**
2. Browser POSTs `{subject, year, username, password, max_q, headless}` to `/run`
3. Flask sets `running=True`, spawns subprocess, returns `{status: "started"}`
4. Browser switches to Live Progress tab, opens `EventSource('/stream')`
5. Flask generator: `for line in proc.stdout: yield f"data: {line}\n\n"`
6. `app.js` receives each line:
   - Appends to log panel
   - Parses `[SKILL]`, `[QUESTION]`, `[SKIP]`, `[DONE]` patterns → updates stat cards
7. On `[DONE]` or `[ERROR]`: SSE closes, Flask sets `running=False`
8. User switches to Review tab, selects the completed run to browse questions

---

## 8. Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Login fails | Scraper prints `[ERROR] Login failed` → shown in red in log |
| Subprocess crashes | Flask sends `data: [ERROR] scraper exited with code N\n\n` then closes SSE |
| Double-run attempt | `/run` returns `{error: "already running"}`, UI shows warning |
| Output dir missing | Flask creates it before spawning subprocess |
| Password field empty | Client-side validation blocks form submission |

---

## 9. Out of Scope

- Running multiple scrapes in parallel
- Authentication via OAuth / IXL API (not available)
- Editing or annotating questions in the UI
- Deploying the Flask app to a remote server
- Audio question support
