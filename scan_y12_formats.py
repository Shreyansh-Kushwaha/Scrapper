"""
Fast format scanner for IXL Year 12 Maths.
Visits every skill, looks at first question only, records format type.
"""
import json, re, time, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

USERNAME = "supersheldon1"
PASSWORD = "3ej#A!@QH%f6"
INDEX_URL = "https://uk.ixl.com/maths/year-12"
OUTPUT = "y12_maths_formats.json"

NAV_SLUGS = {"skills","games","recommendations","diagnostic","shop","logout","signin","awards","analytics"}

TYPE_PATTERNS = [
    ("Audio MCQ",        r'audio|sound-player|AudioButton|listen-button'),
    ("Drag and Drop",    r'draggable|drag-item|DRAG|dragstart|dragover|dropzone|SORT|sortable'),
    ("Matching",         r'MATCH|matching|match-pair|connectLine|draw-line'),
    ("Ordering",         r'ORDER|ordering|rank-item|sequence'),
    ("Word Bank",        r'WORD_BANK|wordBank|word-bank'),
    ("Fill in Blank",    r'FILL_IN_THE_BLANK|FILL_IN|fillinblank|input.*text|type.*answer'),
    ("Click/Select",     r'CLICK_ON|UNDERLINE|clickable-token|highlight-token|SELECT'),
    ("Graph/Plot",       r'graphie|numberline|coordinate|graph-container|plotly|desmos|canvas'),
    ("Multiple Choice",  r'MULTIPLE_CHOICE|SelectableTile|multiple-choice|answer-choice'),
    ("Dropdown",         r'SELECT|dropdown|select-answer'),
]

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def detect_format(page):
    try:
        html = page.content()
    except Exception:
        return "error"

    for label, pattern in TYPE_PATTERNS:
        if re.search(pattern, html):
            return label
    return "unknown"

def get_question_text(page):
    try:
        el = page.query_selector(".question-component")
        return clean(el.inner_text())[:200] if el else ""
    except Exception:
        return ""

def login(page):
    print("Logging in...", flush=True)
    page.goto("https://uk.ixl.com/signin", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1)
    page.fill("#siusername", USERNAME)
    page.fill("#sipassword", PASSWORD)
    page.click("button.submit-button[type='submit']")
    time.sleep(3)
    if page.query_selector(".subaccount-selection-form"):
        page.evaluate("document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] .signin-avatar').click()")
        time.sleep(2)
    print("Logged in.\n", flush=True)

def get_all_skills(page):
    print(f"Loading Year 12 Maths index...", flush=True)
    page.goto(INDEX_URL, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    skills, seen = [], set()
    for a in page.query_selector_all("a[href]"):
        try:
            href = a.get_attribute("href") or ""
            name = clean(a.inner_text())
            if "/maths/year-12/" not in href:
                continue
            slug = href.rstrip("/").split("/")[-1]
            if slug in NAV_SLUGS or not slug or not name or len(name) > 120:
                continue
            if href in seen:
                continue
            seen.add(href)
            url = href if href.startswith("http") else f"https://uk.ixl.com{href}"
            skills.append({"name": name, "url": url, "slug": slug})
        except Exception:
            continue

    print(f"Found {len(skills)} skills.\n", flush=True)
    return skills

def scan_skill(page, skill, index, total):
    url  = skill["url"]
    name = skill["name"]
    print(f"[{index}/{total}] {name[:60]}", flush=True, end=" ... ")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except PWTimeout:
        print("TIMEOUT", flush=True)
        return {"name": name, "url": url, "format": "timeout", "question_preview": ""}

    # Wait up to 8s for question to appear
    deadline = time.time() + 8
    while time.time() < deadline:
        el = page.query_selector(".question-component")
        if el and len(clean(el.inner_text())) > 10:
            break
        time.sleep(0.3)

    fmt   = detect_format(page)
    qtext = get_question_text(page)

    print(f"[{fmt}]  {qtext[:60]}", flush=True)

    return {
        "name":             name,
        "url":              url,
        "format":           fmt,
        "question_preview": qtext,
    }

def main():
    results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
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

        skills = get_all_skills(page)
        total  = len(skills)

        for i, skill in enumerate(skills, 1):
            result = scan_skill(page, skill, i, total)
            results.append(result)

        browser.close()

    # Summary
    from collections import Counter
    fmt_counts = Counter(r["format"] for r in results)
    print("\n" + "="*60, flush=True)
    print("FORMAT SUMMARY:", flush=True)
    for fmt, count in fmt_counts.most_common():
        print(f"  {fmt:<30} {count}", flush=True)

    Path(OUTPUT).write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n✓ Saved {len(results)} results → {OUTPUT}", flush=True)

if __name__ == "__main__":
    main()
