"""
IXL Full Authenticated Scraper
- Logs in as "Child 1"
- Iterates every skill on uk.ixl.com/english/year-9
- Up to MAX_Q_PER_SKILL unique questions per skill
- Question types: multiple-choice, fill-in-the-blank, word-bank, click-to-select,
  sort/sequence, drag-and-drop, ordering, matching, other
- Output: ixl_all_questions.json  +  ixl_all_questions.csv

Run: PYTHONUNBUFFERED=1 python3 ixl_scraper_full.py
"""

import json, re, time, csv, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── credentials ───────────────────────────────────────────────────────────────
USERNAME  = "supersheldon1"
PASSWORD  = "3ej#A!@QH%f6"
LOGIN_URL = "https://uk.ixl.com/signin"
INDEX_URL = "https://uk.ixl.com/english/year-9"

# ── settings ──────────────────────────────────────────────────────────────────
MAX_Q_PER_SKILL   = 10    # unique questions to collect per skill
QUESTION_TIMEOUT  = 8000  # ms to wait for a question to appear
ADVANCE_WAIT      = 2.0   # seconds after each submit before polling for new Q
MAX_WAIT_NEW_Q    = 8.0   # max seconds to poll for a new (different) question
OUTPUT_JSON       = "ixl_all_questions.json"
OUTPUT_CSV        = "ixl_all_questions.csv"

# ── question type detection ───────────────────────────────────────────────────
TYPE_MAP = {
    "MULTIPLE_CHOICE":   "multiple-choice",
    "FILL_IN_THE_BLANK": "fill-in-the-blank",
    "FILL_IN":           "fill-in-the-blank",
    "WORD_BANK":         "word-bank",
    "CLICK_ON":          "click-to-select",
    "SORT":              "sort/sequence",
    "DRAG":              "drag-and-drop",
    "ORDER":             "ordering",
    "MATCH":             "matching",
    "SEQUENCE":          "sort/sequence",
    "SELECT":            "select-from-dropdown",
    "UNDERLINE":         "underline/highlight",
}


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def detect_type(html: str) -> str:
    for token, label in TYPE_MAP.items():
        if token in html:
            return label
    return "other"


# ── question extraction ───────────────────────────────────────────────────────

def get_question_text(page) -> str:
    """Return the current .question-component inner text, or ''."""
    qc = page.query_selector(".question-component")
    return clean(qc.inner_text() if qc else "")


def extract_question(page) -> dict | None:
    html  = page.content()
    qtype = detect_type(html)

    qc = page.query_selector(".question-component")
    if not qc:
        return None
    full = clean(qc.inner_text())
    if len(full) < 10:
        return None

    # ── choices by type ───────────────────────────────────────────────────
    choices: list[str] = []

    if "multiple-choice" in qtype:
        els = page.query_selector_all(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        )
        choices = [clean(e.inner_text()) for e in els if clean(e.inner_text())]

    elif "word-bank" in qtype:
        for sel in [
            "[class*='WORD_BANK'] [class*='tile']",
            "[class*='wordBank'] span",
            "[class*='word-bank'] span",
        ]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel) if clean(e.inner_text())]
            if found:
                choices = found
                break

    elif "click-to-select" in qtype or "underline" in qtype:
        for sel in ["[class*='CLICK_ON']", "[class*='token']", "[class*='clickable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel) if clean(e.inner_text())]
            if found:
                choices = found
                break

    elif any(k in qtype for k in ("drag", "sort", "order", "match")):
        for sel in ["[draggable='true']", "[class*='drag-item']", "[class*='draggable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel) if clean(e.inner_text())]
            if found:
                choices = found
                break

    elif "select-from-dropdown" in qtype:
        for sel in ["select option", "[class*='dropdown'] [class*='option']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel) if clean(e.inner_text())]
            if found:
                choices = found
                break

    # ── stem: full text minus first choice onward ────────────────────────
    stem = full
    if choices:
        idx = full.find(choices[0])
        if idx > 0:
            stem = full[:idx].strip()

    blanks: list[str] = []
    if "fill" in qtype:
        inputs = page.query_selector_all("input[type='text'], input[type='number']")
        blanks = [clean(i.get_attribute("placeholder") or "") for i in inputs]

    result: dict = {"type": qtype, "question": stem[:4000], "choices": choices}
    if blanks:
        result["blanks"] = blanks
    return result if result["question"] else None


# ── interaction ───────────────────────────────────────────────────────────────

def _click_crisp(page, label: str) -> bool:
    """Find a visible button.crisp-button with exact text, scroll+force-click it."""
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


def submit_answer(page):
    """Click a choice, submit, then dismiss any post-answer feedback screen."""
    # Click first interactive MCQ choice with force (bypasses overlay)
    try:
        page.locator(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        ).first.click(force=True, timeout=5000)
        time.sleep(0.4)
    except Exception:
        pass

    # Fill text inputs (fill-in-blank)
    for inp in page.query_selector_all("input[type='text']"):
        try:
            if inp.is_visible():
                inp.fill("a")
                break
        except Exception:
            pass

    # Click visible Submit
    if not _click_crisp(page, "Submit"):
        page.keyboard.press("Enter")

    time.sleep(1.5)

    # After an incorrect answer IXL shows "Got it" / "Next" before loading
    # the next question — dismiss it.
    for label in ("Got it", "Next", "Continue", "OK"):
        if _click_crisp(page, label):
            time.sleep(0.8)
            break


def wait_for_new_question(page, prev_text: str) -> bool:
    """
    Poll until .question-component has a real new question (different from
    prev_text, longer than 20 chars, and not just "Submit" transition text).
    Returns True if a new question appeared within MAX_WAIT_NEW_Q seconds.
    """
    deadline = time.time() + MAX_WAIT_NEW_Q
    while time.time() < deadline:
        current = get_question_text(page)
        is_real = (
            current
            and len(current) > 20
            and not current.startswith("Submit")
            and current[:80] != prev_text[:80]
        )
        if is_real:
            return True
        # If stuck on "Got it" / "Next" feedback screen, dismiss it
        for label in ("Got it", "Next", "Continue"):
            if _click_crisp(page, label):
                time.sleep(0.6)
                break
        time.sleep(0.4)
    return False


# ── login ─────────────────────────────────────────────────────────────────────

def login(page) -> bool:
    print("Logging in …", flush=True)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)

    page.fill("#siusername", USERNAME)
    time.sleep(0.4)
    page.fill("#sipassword", PASSWORD)
    time.sleep(0.4)
    page.click("button.submit-button[type='submit']")
    time.sleep(4)

    if page.query_selector(".subaccount-selection-form"):
        print("  Selecting 'Child 1' …", flush=True)
        page.evaluate(
            "document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] .signin-avatar').click()"
        )
        time.sleep(3)

    ok = "Student Dashboard" in page.title() or "signin" not in page.url.lower()
    print(f"  {'OK' if ok else 'FAILED (continuing)'}  — {page.title()}", flush=True)
    return ok


# ── index scrape ──────────────────────────────────────────────────────────────

def get_skill_links(page) -> list[dict]:
    print(f"\nLoading index …", flush=True)
    page.goto(INDEX_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    skills: list[dict] = []
    seen: set[str] = set()
    for a in page.query_selector_all("a[href]"):
        try:
            href = a.get_attribute("href") or ""
            name = clean(a.inner_text())
            if "/english/year-9/" in href and href not in seen and name:
                url = href if href.startswith("http") else f"https://uk.ixl.com{href}"
                skills.append({"name": name, "url": url})
                seen.add(href)
        except Exception:
            pass

    print(f"Found {len(skills)} skills.\n", flush=True)
    return skills


# ── skill scraper ─────────────────────────────────────────────────────────────

def scrape_skill(page, skill: dict) -> list[dict]:
    name = skill["name"]
    url  = skill["url"]

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
    except PWTimeout:
        print(f"    Timeout loading skill.", flush=True)
        return []

    results: list[dict] = []
    seen_stems: set[str] = set()

    # ── wait for first question ───────────────────────────────────────────
    try:
        page.wait_for_selector(".question-component", timeout=QUESTION_TIMEOUT)
    except PWTimeout:
        print(f"    No question found.", flush=True)
        return []

    prev_text = ""

    # Wait for the first real question to appear
    deadline = time.time() + 10
    while time.time() < deadline:
        if get_question_text(page) and len(get_question_text(page)) > 20:
            break
        time.sleep(0.5)

    while len(results) < MAX_Q_PER_SKILL:
        current_text = get_question_text(page)
        if not current_text or len(current_text) < 20 or current_text.startswith("Submit"):
            break

        # Deduplicate
        fp = current_text[:80]
        if fp not in seen_stems:
            seen_stems.add(fp)
            q = extract_question(page)
            if q:
                q["skill"]          = name
                q["skill_url"]      = url
                q["question_index"] = len(results) + 1
                results.append(q)
                preview = q["question"][:65].replace("\n", " ")
                print(
                    f"    Q{len(results):2d} [{q['type']:<22}] {preview}…",
                    flush=True,
                )

        # Submit and wait for a new (different) question
        prev_text = current_text
        submit_answer(page)

        # Poll until question changes
        if not wait_for_new_question(page, prev_text):
            break   # no new question appeared — skill exhausted

    return results


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    all_questions: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        login(page)
        skills = get_skill_links(page)

        if not skills:
            print("No skills found.", flush=True)
            browser.close()
            return

        for i, skill in enumerate(skills, 1):
            print(f"[{i:3d}/{len(skills)}] {skill['name']}", flush=True)
            qs = scrape_skill(page, skill)
            all_questions.extend(qs)

        browser.close()

    # ── summary ───────────────────────────────────────────────────────────
    from collections import Counter
    print(f"\n{'═'*55}", flush=True)
    print(f"Total questions: {len(all_questions)}", flush=True)
    for t, n in Counter(q["type"] for q in all_questions).most_common():
        print(f"  {t:<28} {n}", flush=True)

    # ── save JSON ─────────────────────────────────────────────────────────
    Path(OUTPUT_JSON).write_text(
        json.dumps(all_questions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved JSON → {OUTPUT_JSON}", flush=True)

    # ── save CSV ──────────────────────────────────────────────────────────
    fieldnames = ["skill", "question_index", "type", "question", "choices", "skill_url"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in all_questions:
            r = dict(row)
            r["choices"] = " | ".join(r.get("choices", []))
            writer.writerow(r)
    print(f"Saved CSV  → {OUTPUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
