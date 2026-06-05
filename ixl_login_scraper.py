"""
IXL Authenticated Scraper
- Logs in, selects "Child 1" subaccount
- Scrapes questions from a test skill with all question types categorized
- Output: test_questions.json + test_questions.csv
"""

import json, re, time, csv
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── credentials ──────────────────────────────────────────────────────────────
USERNAME = "supersheldon1"
PASSWORD = "3ej#A!@QH%f6"
LOGIN_URL = "https://uk.ixl.com/signin"

# ── test target ───────────────────────────────────────────────────────────────
TEST_URL   = "https://uk.ixl.com/english/year-9/which-sentence-is-more-formal"
TEST_LABEL = "Which sentence is more formal? (Year 9 English)"

# ── settings ──────────────────────────────────────────────────────────────────
MAX_Q       = 20
DELAY       = 1.5
OUTPUT_JSON = "test_questions.json"
OUTPUT_CSV  = "test_questions.csv"

# ── type map ──────────────────────────────────────────────────────────────────
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


# ── helpers ───────────────────────────────────────────────────────────────────

def clean(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def login(page) -> bool:
    print("Step 1 — loading sign-in page …")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)

    page.fill("#siusername", USERNAME)
    time.sleep(0.4)
    page.fill("#sipassword", PASSWORD)
    time.sleep(0.4)
    page.click("button.submit-button[type='submit']")
    time.sleep(4)

    print(f"  URL after submit : {page.url}")

    # ── handle subaccount selection ("Who are you?") ───────────────────
    if page.query_selector(".subaccount-selection-form"):
        print("Step 2 — selecting 'Child 1' subaccount …")
        # Clicking the avatar div directly submits the form + navigates
        with page.expect_navigation(timeout=15000):
            page.click("[data-cy='subaccount-selection-Child 1'] .signin-avatar")
        time.sleep(2)

    print(f"  Final URL : {page.url}")
    print(f"  Title     : {page.title()}")
    return "signin" not in page.url.lower()


def detect_type(html: str) -> str:
    for token, label in TYPE_MAP.items():
        if token in html:
            return label
    return "other"


def extract_question(page) -> dict | None:
    html  = page.content()
    qtype = detect_type(html)

    qc = page.query_selector(".question-component")
    if not qc:
        return None
    full_text = clean(qc.inner_text())
    if len(full_text) < 10:
        return None

    # ── per-type choice extraction ────────────────────────────────────────
    choices = []

    if "multiple-choice" in qtype:
        els = page.query_selector_all(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        )
        choices = [clean(e.inner_text()) for e in els if clean(e.inner_text())]

    elif "word-bank" in qtype:
        for sel in ["[class*='WORD_BANK'] [class*='tile']", "[class*='wordBank']", "[class*='word-bank'] *"]:
            els = page.query_selector_all(sel)
            found = [clean(e.inner_text()) for e in els if clean(e.inner_text())]
            if found:
                choices = found
                break

    elif "select-from-dropdown" in qtype:
        for sel in ["select option", "[class*='dropdown'] [class*='option']"]:
            els = page.query_selector_all(sel)
            found = [clean(e.inner_text()) for e in els if clean(e.inner_text())]
            if found:
                choices = found
                break

    elif "click-to-select" in qtype or "underline" in qtype:
        for sel in ["[class*='CLICK_ON']", "[class*='token']", "[class*='clickable']", "[class*='selectable']"]:
            els = page.query_selector_all(sel)
            found = [clean(e.inner_text()) for e in els if clean(e.inner_text())]
            if found:
                choices = found
                break

    elif any(k in qtype for k in ("drag", "sort", "order", "match")):
        for sel in ["[draggable='true']", "[class*='draggable']", "[class*='drag-item']", "[class*='sortable']"]:
            els = page.query_selector_all(sel)
            found = [clean(e.inner_text()) for e in els if clean(e.inner_text())]
            if found:
                choices = found
                break

    # ── extract stem (everything before first choice) ─────────────────────
    stem = full_text
    if choices:
        idx = full_text.find(choices[0])
        if idx > 0:
            stem = full_text[:idx].strip()

    # ── fill-in blank placeholders ────────────────────────────────────────
    blanks = []
    if "fill" in qtype:
        inputs = page.query_selector_all("input[type='text'], input[type='number']")
        blanks = [clean(inp.get_attribute("placeholder") or "") for inp in inputs]

    result = {
        "type":     qtype,
        "question": stem[:3000],
        "choices":  choices,
    }
    if blanks:
        result["blanks"] = blanks
    return result if result["question"] else None


def interact_and_advance(page):
    """Click a valid choice, submit, then try to advance past feedback."""
    # Pick first interactive choice for MCQ
    for sel in [
        "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])",
        "[class*='MULTIPLE_CHOICE'][class*='natural']:not([class*='nonInteractive'])",
    ]:
        els = page.query_selector_all(sel)
        for el in els:
            try:
                if el.is_visible():
                    el.click()
                    time.sleep(0.3)
                    break
            except Exception:
                pass
        break

    # Fill text inputs (for fill-in questions)
    for inp in page.query_selector_all("input[type='text']:visible"):
        try:
            inp.fill("a")
            break
        except Exception:
            pass

    # Submit
    submitted = False
    for sel in ["button.submit[type='submit']", "button.submit", "button[class*='submit']", "[aria-label='Submit']"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                submitted = True
                break
        except Exception:
            pass
    if not submitted:
        page.keyboard.press("Enter")

    time.sleep(0.8)

    # After answering, IXL may show a "Next" or "Keep going" button
    for sel in ["button[class*='next']", "[aria-label='Next']", "[class*='nextQuestion']", "button.next"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                return
        except Exception:
            pass


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    questions: list[dict] = []

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

        # ── login ─────────────────────────────────────────────────────────
        logged_in = login(page)
        status = "OK" if logged_in else "FAILED (continuing anyway)"
        print(f"Login: {status}\n")

        # ── navigate to test skill ────────────────────────────────────────
        print(f"Navigating to: {TEST_LABEL}")
        page.goto(TEST_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        print(f"Page title: {page.title()}\n")

        # ── scrape loop ───────────────────────────────────────────────────
        seen: set[str] = set()
        attempt = 0

        while len(questions) < MAX_Q and attempt < MAX_Q * 4:
            attempt += 1
            try:
                page.wait_for_selector(".question-component", timeout=8000)
            except PWTimeout:
                print(f"  attempt {attempt}: no .question-component visible — stopping.")
                break

            q = extract_question(page)
            if q:
                fp = q["question"][:80]
                if fp not in seen:
                    seen.add(fp)
                    q["skill"]          = TEST_LABEL
                    q["skill_url"]      = TEST_URL
                    q["question_index"] = len(questions) + 1
                    questions.append(q)
                    preview = q["question"][:65].replace("\n", " ")
                    print(f"  Q{len(questions):3d} [{q['type']:<22}] {preview}…")

            interact_and_advance(page)
            time.sleep(DELAY)

        browser.close()

    # ── summary ───────────────────────────────────────────────────────────
    from collections import Counter
    print(f"\n{'─'*55}")
    print(f"Unique questions captured: {len(questions)}")
    for t, n in Counter(q["type"] for q in questions).most_common():
        print(f"  {t:<28} {n}")

    # ── save ──────────────────────────────────────────────────────────────
    Path(OUTPUT_JSON).write_text(
        json.dumps(questions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved JSON → {OUTPUT_JSON}")

    fieldnames = ["skill", "question_index", "type", "question", "choices", "skill_url"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in questions:
            r = dict(row)
            r["choices"] = " | ".join(r.get("choices", []))
            writer.writerow(r)
    print(f"Saved CSV  → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
