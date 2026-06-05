"""
Diagnostic: submit a wrong answer on 3 skill types and dump all class tokens
visible after the feedback screen appears.
Run once before the full scrape to confirm correct-answer selectors.
"""
import json, re, time, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

USERNAME = "supersheldon1"
PASSWORD = "3ej#A!@QH%f6"

TEST_SKILLS = [
    # (name, url, format)
    ("Identify functions",        "https://uk.ixl.com/maths/year-12/identify-functions",        "MCQ"),
    ("Solve linear equations",    "https://uk.ixl.com/maths/year-12/solve-linear-equations",    "FillBlank"),
    ("Reference angles",          "https://uk.ixl.com/maths/year-12/reference-angles",          "FillBlankGraph"),
]

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def click_crisp(page, label):
    for b in page.query_selector_all("button.crisp-button"):
        if (b.inner_text() or "").strip() == label and b.bounding_box():
            try:
                b.scroll_into_view_if_needed()
                time.sleep(0.1)
                b.click(force=True, timeout=4000)
                return True
            except Exception:
                pass
    return False

def dump_classes(page, context_msg):
    """Find all class tokens present after submission."""
    html = page.content()
    all_classes = re.findall(r'class="([^"]+)"', html)
    tokens = set()
    for c in all_classes:
        for tok in c.split():
            if any(k in tok.lower() for k in [
                'correct', 'answer', 'solution', 'wrong', 'right',
                'feedback', 'result', 'error', 'success', 'check',
                'tile', 'skin', 'reveal'
            ]):
                tokens.add(tok)

    print(f"\n  [{context_msg}] Relevant class tokens:")
    for tok in sorted(tokens):
        print(f"    {tok}")

    # Also try specific selectors
    probes = [
        "[class*='correct']",
        "[class*='Correct']",
        "[class*='TileSkin']",
        "[class*='correctAnswer']",
        "[class*='correct-answer']",
        ".correct-answer",
        "[class*='solution']",
        "[class*='feedback']",
        "[class*='reveal']",
        "[class*='wrongAnswer']",
        "[class*='wrong']",
    ]
    print(f"\n  Selector probe results:")
    for sel in probes:
        try:
            els = page.query_selector_all(sel)
            if els:
                texts = [clean(e.inner_text())[:60] for e in els if clean(e.inner_text())]
                print(f"    {sel:<45} → {len(els)} els  text={texts[:3]}")
        except Exception:
            pass

    # Check for any crisp buttons visible
    print(f"\n  Visible crisp buttons:")
    for b in page.query_selector_all("button.crisp-button"):
        try:
            txt = clean(b.inner_text())
            if txt:
                print(f"    '{txt}'")
        except Exception:
            pass


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-GB", viewport={"width":1280,"height":900}
    )
    page = ctx.new_page()

    print("Logging in...", flush=True)
    page.goto("https://uk.ixl.com/signin", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1)
    page.fill("#siusername", USERNAME)
    page.fill("#sipassword", PASSWORD)
    page.click("button.submit-button[type='submit']")
    time.sleep(4)
    if page.query_selector(".subaccount-selection-form"):
        page.evaluate("document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] .signin-avatar').click()")
        time.sleep(3)

    for name, url, fmt in TEST_SKILLS:
        print(f"\n{'='*60}", flush=True)
        print(f"SKILL: {name}  [{fmt}]", flush=True)

        page.goto(url, wait_until="domcontentloaded", timeout=15000)

        # Wait for question
        deadline = time.time() + 10
        while time.time() < deadline:
            el = page.query_selector(".question-component")
            if el and len(clean(el.inner_text())) > 10:
                break
            time.sleep(0.3)

        qtext = clean((page.query_selector(".question-component") or page).inner_text())[:150]
        print(f"  Question: {qtext}", flush=True)

        # Get MCQ options BEFORE submitting
        if fmt == "MCQ":
            tiles = page.query_selector_all("[class*='SelectableTile']:not([class*='nonInteractive'])")
            options = [clean(t.inner_text()) for t in tiles if clean(t.inner_text())]
            print(f"  Options: {options}", flush=True)

        print("\n  --- BEFORE SUBMIT ---", flush=True)
        dump_classes(page, "before")

        # Submit a wrong answer
        if fmt == "MCQ":
            # Click last tile (most likely wrong)
            tiles = page.query_selector_all("[class*='SelectableTile']:not([class*='nonInteractive'])")
            if tiles:
                tiles[-1].click(force=True)
                time.sleep(0.3)
        else:
            # Fill in blank with garbage
            for inp in page.query_selector_all("input[type='text'], input[type='number']"):
                try:
                    if inp.is_visible():
                        inp.fill("WRONG999")
                except Exception:
                    pass

        # Submit
        if not click_crisp(page, "Submit"):
            page.keyboard.press("Enter")
        time.sleep(2.5)

        print("\n  --- AFTER SUBMIT (feedback screen) ---", flush=True)
        dump_classes(page, "after submit")

        # Try dismissing and checking again
        for lbl in ("Got it", "Next", "Continue", "OK"):
            if click_crisp(page, lbl):
                time.sleep(0.8)
                break

        print("\n  --- AFTER DISMISS ---", flush=True)
        dump_classes(page, "after dismiss")

    browser.close()

print("\nDone.", flush=True)
