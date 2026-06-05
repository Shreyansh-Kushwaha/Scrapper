"""
IXL Year-9 English scraper
Collects all 141 skill links from the index, then visits each skill and
captures up to MAX_Q_PER_SKILL questions per skill.

Output: ixl_questions.json  +  ixl_questions.csv
"""

import json
import time
import re
import csv
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

INDEX_URL       = "https://uk.ixl.com/english/year-9"
OUTPUT_JSON     = "ixl_questions.json"
OUTPUT_CSV      = "ixl_questions.csv"
MAX_Q_PER_SKILL = 5      # IXL keeps regenerating questions; we cap here
POLITE_DELAY    = 1.5    # seconds between page loads


# ── helpers ──────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_question(page) -> dict | None:
    """
    Parse the current IXL question page into a structured dict.
    Returns None if no question is visible.
    """
    q: dict = {}

    # ── detect question type from CSS class tokens ────────────────────────
    # IXL encodes the type as an all-caps word in the choice element's class list.
    html = page.content()
    type_match = re.search(
        r'class="[^"]*\b(MULTIPLE_CHOICE|FILL_IN_THE_BLANK|FILL_IN|WORD_BANK|'
        r'CLICK_ON|SORT|DRAG|ORDER|MATCH|SEQUENCE)\b',
        html,
    )
    q["type"] = type_match.group(1).lower().replace("_", "-") if type_match else "unknown"

    # ── question component (full text: passage + stem + choices) ─────────
    qc = page.query_selector(".question-component")
    if not qc:
        return None
    full_text = clean(qc.inner_text())

    # ── choices ───────────────────────────────────────────────────────────
    # Interactive (non-example) choices: class contains MULTIPLE_CHOICE and
    # 'natural' but NOT 'nonInteractive'.
    choice_els = page.query_selector_all(
        "[class*='MULTIPLE_CHOICE'][class*='natural']:not([class*='nonInteractive'])"
    )
    choices = [clean(el.inner_text()) for el in choice_els if clean(el.inner_text())]

    # For fill-in / word-bank / click-on types, choices live elsewhere
    if not choices:
        for sel in [
            "[class*='word-bank'] [class*='tile']",
            "[class*='wordBank'] [class*='tile']",
            "[draggable='true']",
            "[class*='WORD_BANK']",
            "[class*='FILL_IN']",
        ]:
            els = page.query_selector_all(sel)
            if els:
                choices = [clean(e.inner_text()) for e in els if clean(e.inner_text())]
                break
    q["choices"] = choices

    # ── question stem (everything BEFORE the first choice text) ──────────
    if choices:
        first_choice = choices[0]
        idx = full_text.find(first_choice)
        stem = full_text[:idx].strip() if idx > 0 else full_text
    else:
        stem = full_text
    q["question"] = stem[:2000]   # cap at 2000 chars (passages can be long)

    if not q["question"]:
        return None

    return q


def advance_question(page):
    """Click Submit/Next or press Enter to move to the next question."""
    for sel in [
        "button.submit",
        "button[class*='submit']",
        "button[class*='next']",
        "[class*='submit-btn']",
        "[aria-label='Submit']",
        "input[type='submit']",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                return
        except Exception:
            pass
    page.keyboard.press("Enter")


# ── stage 1: collect skill URLs from index page ───────────────────────────────

def get_skill_links(page) -> list[dict]:
    print(f"Loading index: {INDEX_URL}")
    page.goto(INDEX_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    skills = []
    seen = set()
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

    print(f"Found {len(skills)} skills.")
    return skills


# ── stage 2: scrape questions from one skill ─────────────────────────────────

def scrape_skill(page, skill: dict) -> list[dict]:
    url  = skill["url"]
    name = skill["name"]

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(POLITE_DELAY)
    except PWTimeout:
        print(f"    Timeout: {url}")
        return []

    questions = []
    seen_stems: set[str] = set()

    for attempt in range(MAX_Q_PER_SKILL):
        try:
            page.wait_for_selector(".question-component", timeout=8000)
        except PWTimeout:
            break

        q = extract_question(page)
        if q:
            fp = q["question"][:80]
            if fp not in seen_stems:
                q["skill"]          = name
                q["skill_url"]      = url
                q["question_index"] = attempt + 1
                questions.append(q)
                seen_stems.add(fp)
                preview = fp[:55] + "…" if len(fp) > 55 else fp
                print(f"    Q{attempt+1} [{q['type']}] {preview}")

        # Answer randomly (first visible choice) and advance
        try:
            first_choice = page.query_selector(
                "[class*='MULTIPLE_CHOICE'][class*='natural']:not([class*='nonInteractive'])"
            )
            if first_choice and first_choice.is_visible():
                first_choice.click()
                time.sleep(0.4)
        except Exception:
            pass

        try:
            advance_question(page)
            time.sleep(1.2)
        except Exception:
            break

    return questions


# ── main ─────────────────────────────────────────────────────────────────────

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
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        skills = get_skill_links(page)
        if not skills:
            print("No skills found — page structure may have changed.")
            browser.close()
            return

        for i, skill in enumerate(skills, 1):
            print(f"\n[{i}/{len(skills)}] {skill['name']}")
            qs = scrape_skill(page, skill)
            all_questions.extend(qs)
            time.sleep(POLITE_DELAY)

        browser.close()

    # ── persist results ───────────────────────────────────────────────────
    Path(OUTPUT_JSON).write_text(
        json.dumps(all_questions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n✓ {len(all_questions)} questions saved → {OUTPUT_JSON}")

    if all_questions:
        fieldnames = ["skill", "question_index", "type", "question", "choices", "skill_url"]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in all_questions:
                row = dict(row)
                row["choices"] = " | ".join(row.get("choices", []))
                writer.writerow(row)
        print(f"✓ CSV saved → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
