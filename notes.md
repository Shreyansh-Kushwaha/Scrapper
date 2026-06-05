# IXL Year 12 Maths Scraper — Project Notes

---

## Skill Breakdown (Year 12 Maths — 290 total skills)

| Action | Format | Count |
|--------|--------|-------|
| Scrape | Fill in Blank | 162 |
| Scrape | Fill in Blank (with Graph) | 54 |
| Scrape | Multiple Choice | 51 |
| Skip + count only | Interactive Graph | 18 |
| Skip + count only | Graph Interaction | 4 |
| Skip + count only | Unknown | 1 |
| **Total scrapeable** | | **267** |
| **Total skipped** | | **23** |

### What each format means
- **Fill in Blank** — Type the answer (number, expression, equation). e.g. "Solve for v = ___"
- **Fill in Blank (with Graph)** — Read a static graph on screen, type the answer. e.g. "Find the gradient from this graph"
- **Multiple Choice** — Click one of 4 answer tiles. e.g. "Is this a function? yes / no"
- **Interactive Graph** — User must draw/plot directly on a canvas. SKIPPED — needs Desmos-level UI
- **Graph Interaction** — Click/match on a graph. SKIPPED — not practical for quiz app
- **Unknown** — Could not detect format. SKIPPED

---

## Max Questions Per Skill — Tested (UPDATED)

We ran repeat-detection tests on 2 skills to find the real pool size before IXL loops back.

### Test 1 — MCQ: "Convert between radians and degrees"
- **Result: 11 unique questions** (51 seconds to find out)
- IXL only tests 7 angles: 30°, 45°, 60°, 90°, 150°, 270°, 330°
- Appears as 11 because IXL **shuffles the MCQ choices** each time — same stem, different option order
- Conceptually unique stems: **7**
- Script stalled at Q11 because that question switched to Fill in Blank format (mixed types in one skill!)

### Test 2 — Fill in Blank: "Solve linear equations"
- **Result: 29 unique questions** (~15 minutes to find out)
- IXL generates equations with random coefficients but the pool is finite
- Q30 repeated Q1 exactly (`Solve for c. -17c = -19c - 10`) — pool confirmed exhausted at 29

### Key Finding
| Format | Tested Skill | Max Unique Qs | Notes |
|--------|-------------|---------------|-------|
| MCQ | Convert between radians and degrees | **~7–11** | Fixed angle set, shuffled choices |
| Fill in Blank | Solve linear equations | **29** | Random coefficients but finite pool |

**IXL pools are much smaller than expected.** A cap of 50 questions per skill would result in heavy repetition for most skills.

### Updated Scraping Strategy
- **No hard cap** — stop automatically on first repeated question (repeat-detection approach)
- Stop condition: when the same question stem appears for the 2nd time → pool exhausted

### Updated Total Question Estimate
| Format | Skills | Avg unique/skill | Est. total |
|--------|--------|-----------------|------------|
| Fill in Blank | 162 | ~25 | ~4,050 |
| Fill in Blank (with Graph) | 54 | ~20 | ~1,080 |
| Multiple Choice | 51 | ~10 | ~510 |
| **Total** | **267** | | **~5,600 questions** |

---

## Time Estimate (UPDATED)

| Factor | Original | Updated |
|--------|----------|---------|
| Hard cap per skill | 50 questions | None — stop on repeat |
| Avg unique questions per skill | ~40 | ~20–25 |
| Time per question | ~4–5s | ~2s (optimised waits) |
| Time per skill | ~3–4 min | ~1–1.5 min |
| Total scrapeable skills | 267 | 267 |
| Skills per agent (5 agents) | ~53 | ~53 |
| Time per agent | ~3–3.5 hours | **~1.5–2 hours** |
| **Total wall-clock (5 agents)** | ~3.5 hours | **~1.5–2 hours** |

**Revised total questions: ~5,600** (down from original 7,000–10,000 estimate)

---

## Storage Estimate (UPDATED)

| What | Estimated Size |
|------|---------------|
| Questions JSON (~5,600 rows) | ~20 MB |
| Screenshots for graph questions (~1,080 PNGs) | ~80–100 MB |
| `<img>` tags downloaded from question HTML | ~10–30 MB |
| **Total** | **~110–150 MB** |

---

## Architecture Plan

### Why NOT n8n for scraping
- n8n is for short workflow steps (API calls, transforms, webhooks)
- Running a 3-hour Playwright browser session inside n8n will crash — no Chrome installed, execution timeouts, memory limits

### Recommended Stack

```
┌─────────────────┐     triggers      ┌──────────────────┐
│   n8n workflow  │ ────────────────► │  GitHub Actions  │
│  (scheduler /   │                   │  (runs the actual│
│   monitor)      │ ◄──────────────── │   Playwright     │
│                 │   sends status    │   scraper)       │
└─────────────────┘                   └────────┬─────────┘
                                               │ saves to
                                               ▼
                                       ┌──────────────────┐
                                       │    Supabase      │
                                       │  - PostgreSQL DB │
                                       │    (questions)   │
                                       │  - Storage bucket│
                                       │    (images/PNGs) │
                                       │  - REST API      │
                                       │    (quiz app)    │
                                       └──────────────────┘
```

| Step | Tool | Why |
|------|------|-----|
| Run the scraper | GitHub Actions | Free, runs up to 6 hours, Chrome pre-installed |
| Store questions | Supabase (PostgreSQL) | Queryable, REST API ready, free tier |
| Store images | Supabase Storage | CDN-served URLs, 1 GB free |
| Schedule re-runs | GitHub Actions cron | Trigger monthly refresh automatically |
| Quiz app reads data | Supabase REST API | Direct queries, no custom backend needed |

### Why Supabase
- **Free tier**: 500 MB database + 1 GB file storage — enough for all Year 12 data
- **PostgreSQL**: Quiz app can filter questions by topic, format, year with SQL
- **Storage bucket**: Images served as direct URLs — embed in quiz app instantly
- **REST API**: No backend server needed, quiz app talks directly to Supabase

---

## Question JSON Schema (per question, quiz-app ready)

```json
{
  "question_id":       "ixl-y12-solve-linear-equations-q1",
  "year":              "Year 12",
  "subject":           "Maths",
  "skill_name":        "Solve linear equations",
  "skill_url":         "https://uk.ixl.com/maths/year-12/solve-linear-equations",
  "question_index":    1,
  "format":            "Fill in Blank",
  "question_text":     "Solve for v.  -1 - 16v = 19 - 15v   v =",
  "options":           [],
  "correct_answer":    "-20",
  "answer_captured":   true,
  "has_graph":         false,
  "screenshot_path":   null,
  "image_paths":       [],
  "blank_count":       1,
  "scraped_at":        "2026-06-03T12:00:00Z",
  "quiz_ready":        true
}
```

---

## Files Already Created

| File | Purpose |
|------|---------|
| `y12_maths_formats.json` | Format scan of all 290 Year 12 skills (done) |
| `ixl_scan_batch.py` | Fast format scanner (used for the format scan) |
| `y12_answer_selectors.py` | Diagnostic — confirmed correct-answer CSS selectors |
| `/tmp/ixl_y12_skills.json` | All 290 skill URLs (from scout agent) |
| `ixl_image_scraper.py` | Image downloader (MD5 naming, caching) — to be reused |

## Confirmed CSS Selectors (from diagnostic run)

| What | Selector | Notes |
|------|----------|-------|
| Correct answer block (all types) | `.correct-answer` | Appears after wrong submission |
| MCQ correct tile text | `.correct-answer [class*='SelectableTile']` | Contains "Correct answer, X" prefix |
| Fill in Blank answer input | `.correct-answer input.fillIn` | Disabled input showing correct value |
| Feedback dismiss button | `button.crisp-button` with text `"Got it"` | Click to advance |
| MCQ tiles | `[class*='SelectableTile']:not([class*='nonInteractive'])` | Clickable answer choices |

## Next Steps

1. Write `y12_scrape_batch.py` — main scraper using confirmed selectors
2. Write `y12_merge_results.py` — merge 5 batch outputs into final JSON
3. Set up GitHub Actions workflow (`.github/workflows/scrape_y12.yml`)
4. Set up Supabase project — create `questions` table + `images` storage bucket
5. Add Supabase upload step to scraper output
6. Run full scrape (~3.5 hours on GitHub Actions)
