"""
IXL Year 1–5 English Scraper  (authenticated)
- Dynamically picks 2 skills per year from the IXL index pages
- Scrapes 5 unique questions per skill (10 skills × 5 = up to 50 questions)
- Saves rich JSON with full question metadata

Run: PYTHONUNBUFFERED=1 python3 ixl_year1_5_scraper.py
"""

import json, re, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

USERNAME    = "supersheldon1"
PASSWORD    = "3ej#A!@QH%f6"
OUTPUT_JSON = "ixl_year1_5_questions.json"

YEARS            = [1, 2, 3, 4, 5]
SKILLS_PER_YEAR  = 2
MAX_Q_PER_SKILL  = 5
MAX_WAIT_NEW_Q   = 14.0   # seconds to poll for next question

# Skip navigation-only slugs
NAV_SLUGS = {"skills", "games", "recommendations", "diagnostic",
             "shop", "logout", "signin", "awards", "analytics"}

TYPE_MAP = {
    "MULTIPLE_CHOICE":   "Multiple Choice",
    "FILL_IN_THE_BLANK": "Fill in the Blank",
    "FILL_IN":           "Fill in the Blank",
    "WORD_BANK":         "Word Bank",
    "CLICK_ON":          "Click to Select",
    "SORT":              "Sort / Sequence",
    "DRAG":              "Drag and Drop",
    "ORDER":             "Ordering",
    "MATCH":             "Matching",
    "SEQUENCE":          "Sort / Sequence",
    "SELECT":            "Select from Dropdown",
    "UNDERLINE":         "Underline / Highlight",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def clean(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()

def detect_type(html: str) -> str:
    for token, label in TYPE_MAP.items():
        if token in html:
            return label
    return "Other"

def qc_text(page) -> str:
    el = page.query_selector(".question-component")
    return clean(el.inner_text() if el else "")

def is_real(txt: str) -> bool:
    return len(txt) > 15 and not txt.strip().startswith("Submit")

def click_crisp(page, label: str) -> bool:
    for b in page.query_selector_all("button.crisp-button"):
        if (b.inner_text() or "").strip() == label and b.bounding_box():
            try:
                b.scroll_into_view_if_needed()
                time.sleep(0.15)
                b.click(force=True, timeout=5000)
                return True
            except Exception:
                pass
    return False


# ── login ─────────────────────────────────────────────────────────────────────

def login(page):
    print("Logging in …", flush=True)
    page.goto("https://uk.ixl.com/signin", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)
    page.fill("#siusername", USERNAME); time.sleep(0.4)
    page.fill("#sipassword", PASSWORD); time.sleep(0.4)
    page.click("button.submit-button[type='submit']"); time.sleep(4)
    if page.query_selector(".subaccount-selection-form"):
        print("  Selecting Child 1 …", flush=True)
        page.evaluate(
            "document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] .signin-avatar').click()"
        )
        time.sleep(3)
    print(f"  {page.title()}\n", flush=True)


# ── fetch skill URLs from one year's index ────────────────────────────────────

def get_skills_for_year(page, year: int, n: int) -> list[dict]:
    url = f"https://uk.ixl.com/english/year-{year}"
    page.goto(url, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    prefix = f"/english/year-{year}/"
    skills, seen = [], set()

    for a in page.query_selector_all("a[href]"):
        try:
            href = a.get_attribute("href") or ""
            name = clean(a.inner_text())
            # Must be under this year's prefix
            if prefix not in href:
                continue
            # Must be a real skill (not navigation)
            slug = href.rstrip("/").split("/")[-1]
            if slug in NAV_SLUGS or not slug:
                continue
            # Deduplicate
            if href in seen or not name or len(name) > 120:
                continue
            seen.add(href)
            full_url = href if href.startswith("http") else f"https://uk.ixl.com{href}"
            skills.append({
                "year":    year,
                "subject": "English",
                "name":    name,
                "url":     full_url,
                "slug":    slug,
            })
            if len(skills) >= n:
                break
        except Exception:
            continue

    print(f"  Year {year}: {[s['name'][:40] for s in skills]}", flush=True)
    return skills


# ── extract one question ──────────────────────────────────────────────────────

def extract(page, skill: dict, q_index: int) -> dict | None:
    full = qc_text(page)
    if not is_real(full):
        return None

    html  = page.content()
    qtype = detect_type(html)

    # ── choices ───────────────────────────────────────────────────────────
    choices: list[str] = []

    if "Multiple Choice" in qtype:
        els = page.query_selector_all(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        )
        choices = [clean(e.inner_text()) for e in els if clean(e.inner_text())]

    elif "Word Bank" in qtype:
        for sel in ["[class*='WORD_BANK'] [class*='tile']",
                    "[class*='wordBank'] span", "[class*='word-bank'] span"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found:
                choices = found; break

    elif qtype in ("Click to Select", "Underline / Highlight"):
        for sel in ["[class*='CLICK_ON']", "[class*='token']", "[class*='clickable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found:
                choices = found; break

    elif any(k in qtype for k in ("Drag", "Sort", "Order", "Match")):
        for sel in ["[draggable='true']", "[class*='drag-item']", "[class*='draggable']",
                    "[class*='SORT'] *", "[class*='DRAG'] *"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found:
                choices = found; break

    # ── strip choice text from stem ───────────────────────────────────────
    question_text = full
    passage       = ""
    if choices:
        idx = full.find(choices[0])
        if idx > 0:
            question_text = full[:idx].strip()

    # ── split reading passage from question stem ──────────────────────────
    stem_low = question_text.lower()
    if any(stem_low.startswith(p) for p in
           ("read the passage", "read the text", "review the text",
            "read the following", "read the poem")):
        # Question sentence is the last sentence ending with '?'
        sentences = re.split(r'(?<=[.!?])\s+', question_text)
        q_part = ""
        body_parts = []
        for s in sentences:
            if s.strip().endswith("?") and len(s) < 200:
                q_part = s.strip()
            else:
                body_parts.append(s.strip())
        if q_part:
            passage       = " ".join(body_parts)
            question_text = sentences[0] + " " + q_part  # instruction + question

    blanks = []
    if "Fill" in qtype:
        blanks = [
            clean(i.get_attribute("placeholder") or "")
            for i in page.query_selector_all("input[type='text'], input[type='number']")
        ]

    year = skill["year"]
    name = skill["name"]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())[:30]

    return {
        # identity
        "question_id":         f"ixl-y{year}-{slug}-q{q_index}",
        # classification
        "year":                f"Year {year}",
        "year_number":         year,
        "subject":             skill["subject"],
        "skill_name":          name,
        "skill_url":           skill["url"],
        # question content
        "question_index":      q_index,
        "question_type":       qtype,
        "question_text":       question_text[:4000],
        "passage":             passage[:3000],
        # answer options
        "options":             choices,
        "num_options":         len(choices),
        # flags
        "has_passage":         bool(passage),
        "is_multiple_choice":  "Multiple Choice" in qtype,
        "is_fill_in_blank":    "Fill" in qtype,
        "is_word_bank":        "Word Bank" in qtype,
        "is_ordering":         any(k in qtype for k in ("Sort","Drag","Order","Match")),
        "blank_hints":         blanks,
        # provenance
        "source":              "IXL Learning (uk.ixl.com)",
        "scraped_at":          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ── submit and wait for next question ────────────────────────────────────────

def advance(page, prev: str) -> bool:
    # Click first MCQ choice
    try:
        page.locator(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        ).first.click(force=True, timeout=5000)
        time.sleep(0.4)
    except Exception:
        pass

    # Fill text inputs
    for inp in page.query_selector_all("input[type='text']"):
        try:
            if inp.is_visible(): inp.fill("a"); break
        except Exception:
            pass

    # Submit
    if not click_crisp(page, "Submit"):
        page.keyboard.press("Enter")
    time.sleep(1.5)

    # Dismiss feedback
    for lbl in ("Got it", "Next", "Continue", "OK"):
        if click_crisp(page, lbl): time.sleep(0.8); break

    # Poll for new real question
    deadline = time.time() + MAX_WAIT_NEW_Q
    while time.time() < deadline:
        cur = qc_text(page)
        if is_real(cur) and cur[:80] != prev[:80]:
            return True
        for lbl in ("Got it", "Next", "Continue"):
            if click_crisp(page, lbl): time.sleep(0.6); break
        time.sleep(0.4)
    return False


# ── scrape one skill ──────────────────────────────────────────────────────────

def scrape_skill(page, skill: dict) -> list[dict]:
    try:
        page.goto(skill["url"], wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
    except PWTimeout:
        print("    Timeout loading skill.", flush=True); return []

    # Wait up to 12s for a real question
    deadline = time.time() + 12
    while time.time() < deadline:
        if is_real(qc_text(page)): break
        time.sleep(0.5)
    else:
        print("    No question appeared.", flush=True); return []

    results: list[dict] = []
    seen:    set[str]   = set()

    while len(results) < MAX_Q_PER_SKILL:
        cur = qc_text(page)
        if not is_real(cur): break

        fp = cur[:80]
        if fp not in seen:
            seen.add(fp)
            try:
                q = extract(page, skill, len(results) + 1)
            except Exception:
                traceback.print_exc(); q = None
            if q:
                results.append(q)
                preview = q["question_text"][:68].replace("\n", " ")
                print(
                    f"    Q{len(results)} [{q['question_type']:<22}] {preview}…",
                    flush=True,
                )

        if len(results) >= MAX_Q_PER_SKILL:
            break

        if not advance(page, cur):
            print(f"    ← {len(results)} question(s) collected", flush=True)
            break

    return results


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    all_q: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        login(page)

        # Collect skills from each year's index
        print("Collecting skills from Year 1–5 indexes …", flush=True)
        all_skills: list[dict] = []
        for year in YEARS:
            skills = get_skills_for_year(page, year, SKILLS_PER_YEAR)
            all_skills.extend(skills)

        total = len(all_skills)
        print(f"\nScraping {total} skills ({MAX_Q_PER_SKILL} questions each) …\n",
              flush=True)

        for i, skill in enumerate(all_skills, 1):
            print(
                f"[{i:2d}/{total}]  Year {skill['year']}  ·  {skill['name']}",
                flush=True,
            )
            qs = scrape_skill(page, skill)
            all_q.extend(qs)
            print(f"         → {len(qs)} question(s) collected\n", flush=True)

        browser.close()

    # ── summary ───────────────────────────────────────────────────────────
    from collections import Counter
    print(f"{'═'*60}", flush=True)
    print(f"Grand total: {len(all_q)} questions\n", flush=True)

    print("By year:", flush=True)
    for yr, n in sorted(Counter(q["year"] for q in all_q).items()):
        print(f"  {yr:<12} {n}", flush=True)

    print("\nBy question type:", flush=True)
    for t, n in Counter(q["question_type"] for q in all_q).most_common():
        print(f"  {t:<30} {n}", flush=True)

    print("\nBy skill:", flush=True)
    for s, n in sorted(Counter(q["skill_name"] for q in all_q).items()):
        print(f"  {s:<50} {n}", flush=True)

    # ── save JSON ─────────────────────────────────────────────────────────
    out = Path(OUTPUT_JSON)
    out.write_text(json.dumps(all_q, indent=2, ensure_ascii=False), encoding="utf-8")
    sz = out.stat().st_size
    print(f"\n✓ Saved {len(all_q)} questions → {OUTPUT_JSON}  ({sz:,} bytes)", flush=True)

    # Print a sample record
    if all_q:
        print("\n── Sample question (Q1) ─────────────────────────────────────",
              flush=True)
        print(json.dumps(all_q[0], indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
