#!/usr/bin/env python3
"""
IXL Unified Scraper — all subjects, all year groups
Prints structured [TAG] progress lines for the Flask UI.

Usage:
  python3 ixl_scraper_ui.py --subject maths --year year-12 \
    --username supersheldon1 --password "..." \
    --max-questions 0 --output-dir output/maths/year-12 --headless
"""
import argparse, json, re, time, hashlib, requests, sys
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL   = "https://au.ixl.com"
LOGIN_URL  = f"{BASE_URL}/signin"

SKIP_ALTS = {
    "Scratchpad","Eraser","Highlighter - blue","Highlighter - yellow",
    "Highlighter - pink","Pencil - black","Pencil - blue","Pencil - red",
    "Pencil - green","Ruler","Protractor","Calculator"
}

SKIP_FORMATS = {'audio', 'interactive-graph', 'graph-interaction', 'canvas'}

TYPE_MAP = {
    "MULTIPLE_CHOICE":   "multiple-choice",
    "FILL_IN_THE_BLANK": "fill-in-blank",
    "FILL_IN":           "fill-in-blank",
    "WORD_BANK":         "word-bank",
    "CLICK_ON":          "click-to-select",
    "SORT":              "sort/sequence",
    "SEQUENCE":          "sort/sequence",
    "DRAG":              "drag-and-drop",
    "ORDER":             "ordering",
    "MATCH":             "matching",
    "SELECT":            "select-from-dropdown",
    "UNDERLINE":         "underline/highlight",
    "AUDIO":             "audio",
    "GRAPH_INTERACTION": "graph-interaction",
    "INTERACTIVE_GRAPH": "interactive-graph",
    "CANVAS":            "canvas",
}


# ── Progress output ────────────────────────────────────────────────────────────

def p_start(subject, year, total):
    print(f"[START] subject={subject} year={year} total_skills={total}", flush=True)

def p_skill(i, total, name):
    print(f"[SKILL] {i}/{total} {name}", flush=True)

def p_question(q, fmt):
    print(f"[QUESTION] q={q} format={fmt}", flush=True)

def p_skip(fmt, skill):
    print(f"[SKIP] format={fmt} skill={skill}", flush=True)

def p_skill_done(questions):
    print(f"[SKILL_DONE] questions={questions}", flush=True)

def p_done(total_q, elapsed, skipped):
    print(f"[DONE] total_questions={total_q} elapsed={int(elapsed)}s skipped={skipped}", flush=True)

def p_error(msg):
    print(f"[ERROR] {msg}", flush=True)

def p_resume(skipped_count, total):
    print(f"[RESUME] already_done={skipped_count} remaining={total - skipped_count} total={total}", flush=True)

def p_skill_resume(name):
    print(f"[SKILL_SKIP] {name} (checkpoint — already done)", flush=True)


# ── Utilities ──────────────────────────────────────────────────────────────────

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def make_question_id(subject, year, skill_name, q_index):
    slug = re.sub(r"[^a-z0-9]+", "-", skill_name.lower()).strip("-")
    return f"ixl-{subject}-{year}-{slug}-q{q_index}"

def detect_type(html):
    for token, label in TYPE_MAP.items():
        if token in html:
            return label
    return "other"

def should_skip(qtype):
    return any(s in qtype for s in SKIP_FORMATS)


# ── Login ──────────────────────────────────────────────────────────────────────

def login(page, username, password):
    print(f"Logging in as {username} ...", flush=True)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)
    page.fill("#siusername", username)
    time.sleep(0.3)
    page.fill("#sipassword", password)
    time.sleep(0.3)
    page.click("button.submit-button[type='submit']")
    time.sleep(4)

    if page.query_selector(".subaccount-selection-form"):
        try:
            # Click the first available child avatar (any child name)
            page.evaluate(
                "const a = document.querySelector('[data-cy^=\"subaccount-selection-\"] .signin-avatar');"
                "if (a) a.click();"
            )
            time.sleep(3)
        except Exception:
            pass  # subaccount click failed — login may still be valid

    # Require the URL to clearly indicate a logged-in student context.
    # "signin" not in url is too broad — the subaccount selection page also
    # lacks "signin" in its URL, so a failed subaccount click would slip through.
    url  = page.url.lower()
    title = page.title()
    logged_in = (
        "Student Dashboard" in title
        or "/maths" in url
        or "/english" in url
        or "/science" in url
        or "myprogress" in url
        or ("ixl.com" in url and "signin" not in url and "account" not in url)
    )
    if not logged_in:
        p_error("Login failed — check credentials")
        return False
    print("Login OK", flush=True)
    return True


# ── Skill discovery ────────────────────────────────────────────────────────────

NAV_SLUGS = {"skills", "games", "awards", "videos", "worksheets", "problems"}

def get_skills(page, subject, year):
    index_url = f"{BASE_URL}/{subject}/{year}"
    print(f"Loading skill index: {index_url}", flush=True)
    page.goto(index_url, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    skills = []
    seen   = set()
    path_fragment = f"/{subject}/{year}/"

    for a in page.query_selector_all("a[href]"):
        try:
            href = a.get_attribute("href") or ""
            name = clean(a.inner_text())
            if path_fragment not in href or href in seen or not name:
                continue
            slug = href.rstrip("/").rsplit("/", 1)[-1]
            if slug in NAV_SLUGS or re.match(r"^\d+\s+\w+$", name):
                continue
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            skills.append({"name": name, "url": url})
            seen.add(href)
        except Exception:
            pass

    print(f"Found {len(skills)} skills.", flush=True)
    return skills


# ── Interaction helpers ────────────────────────────────────────────────────────

def click_crisp(page, label):
    try:
        buttons = page.query_selector_all("button.crisp-button")
    except Exception:
        # Page navigated away (e.g. correct MCQ answer auto-advanced)
        return True
    for b in buttons:
        if (b.inner_text() or "").strip() == label and b.bounding_box():
            try:
                b.scroll_into_view_if_needed()
                time.sleep(0.1)
                b.click(force=True, timeout=4000)
                return True
            except Exception:
                pass
    return False


def get_question_text(page):
    qc = page.query_selector(".question-component")
    return clean(qc.inner_text() if qc else "")


def extract_choices(page, qtype):
    choices = []
    if "multiple-choice" in qtype:
        els = page.query_selector_all(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        )
        choices = [clean(e.inner_text()) for e in els if clean(e.inner_text())]

    elif "word-bank" in qtype:
        for sel in ["[class*='WORD_BANK'] [class*='tile']",
                    "[class*='wordBank'] span", "[class*='word-bank'] span"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    elif "click-to-select" in qtype or "underline" in qtype:
        for sel in ["[class*='CLICK_ON']", "[class*='token']", "[class*='clickable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    elif any(k in qtype for k in ("drag", "sort", "order", "match", "sequence")):
        for sel in ["[draggable='true']", "[class*='drag-item']", "[class*='draggable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    elif "select-from-dropdown" in qtype:
        for sel in ["select option", "[class*='dropdown'] [class*='option']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    return choices


def capture_answer(page, qtype):
    """Submit a wrong answer and read the correct answer from .correct-answer.

    For MCQ: clicking the first tile may accidentally be correct, in which case
    IXL shows no .correct-answer div. We detect this by reading the tile text
    before clicking, then checking whether the question advanced without feedback.
    If so, the tile we clicked was the correct answer.
    """
    clicked_tile_text = ""

    if "multiple-choice" in qtype:
        try:
            tiles = page.query_selector_all(
                "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']"
                ":not([class*='nonInteractive'])"
            )
            if tiles:
                # Read the text of each tile upfront so we know what we clicked
                tile_texts = []
                for t in tiles:
                    try:
                        tile_texts.append(clean(t.inner_text()))
                    except Exception:
                        tile_texts.append("")

                # Try to click the LAST tile — for 2-option questions this avoids
                # the common pattern of the first option being correct.
                target = tiles[-1]
                clicked_tile_text = tile_texts[-1]
                try:
                    target.scroll_into_view_if_needed()
                    target.click(force=True, timeout=5000)
                except Exception:
                    # Fallback to first tile
                    tiles[0].click(force=True, timeout=5000)
                    clicked_tile_text = tile_texts[0]
            time.sleep(0.4)
        except Exception:
            pass
    else:
        for inp in page.query_selector_all("input[type='text'], input[type='number']"):
            try:
                if inp.is_visible():
                    inp.fill("zzz")
                    break
            except Exception:
                pass

    if not click_crisp(page, "Submit"):
        page.keyboard.press("Enter")
    time.sleep(1.5)

    correct = ""
    try:
        page.wait_for_selector(".correct-answer", timeout=5000)
        ca = page.query_selector(".correct-answer")
        if ca:
            if "multiple-choice" in qtype:
                tile = ca.query_selector("[class*='SelectableTile']")
                if tile:
                    txt = clean(tile.inner_text())
                    correct = re.sub(r"^Correct answer,?\s*", "", txt).strip()
                if not correct:
                    # Strip "Correct answer" prefix from raw text
                    raw = clean(ca.inner_text())
                    correct = re.sub(r"^Correct answer,?\s*", "", raw).strip()
            else:
                inp = ca.query_selector("input.fillIn")
                if inp:
                    correct = inp.get_attribute("value") or ""
                if not correct:
                    correct = clean(ca.inner_text())
    except Exception:
        # .correct-answer never appeared — we clicked the RIGHT answer.
        # IXL advances automatically on correct answers, so the tile we
        # clicked IS the correct answer.
        if "multiple-choice" in qtype and clicked_tile_text:
            correct = clicked_tile_text

    for label in ("Got it", "Next", "Continue", "OK"):
        if click_crisp(page, label):
            time.sleep(0.8)
            break

    return correct


def wait_for_new_question(page, prev_text):
    deadline = time.time() + 8
    while time.time() < deadline:
        current = get_question_text(page)
        if current and len(current) > 5 and not current.startswith("Submit"):
            # Different text — clearly a new question
            if current[:80] != prev_text[:80]:
                return True
            # Same text — only accept once feedback is gone AND new tiles are loaded
            has_tiles = bool(page.query_selector("[class*='SelectableTile']:not([class*='nonInteractive'])"))
            if not page.query_selector(".correct-answer") and has_tiles:
                return True
        for label in ("Got it", "Next", "Continue"):
            if click_crisp(page, label):
                time.sleep(0.5)
                break
        time.sleep(0.4)
    return False


# ── Image downloader ───────────────────────────────────────────────────────────

IMG_SELECTORS = [
    ".question-and-submission-view img",
    ".question-component img",
    "[class*='TileMultipleChoices'] img",
    "[class*='SelectableTile']:not([class*='nonInteractive']) img",
    "[class*='stimulus'] img",
    "[class*='Stimulus'] img",
    "[class*='picture'] img",
]


def download_images(page, img_dir, session):
    """Download all question images. Returns list of local filenames."""
    paths = []
    seen  = set()

    for sel in IMG_SELECTORS:
        for img in page.query_selector_all(sel):
            src = img.get_attribute("src") or ""
            alt = clean(img.get_attribute("alt") or "")
            if not src or src in seen or src.startswith("data:") or alt in SKIP_ALTS:
                continue
            seen.add(src)

            full_url = src if src.startswith("http") else f"{BASE_URL}{src}"
            fname    = hashlib.md5(full_url.encode()).hexdigest()[:16] + ".jpg"
            fpath    = img_dir / fname

            if fpath.exists():
                paths.append(fname)
                continue

            try:
                resp = session.get(full_url, timeout=10)
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                print(f"[DEBUG-IMG] url={full_url[:80]} status={resp.status_code} ct={ct}", flush=True)
                if "png" in ct:
                    fname = fname.replace(".jpg", ".png")
                    fpath = img_dir / fname
                elif "webp" in ct:
                    fname = fname.replace(".jpg", ".webp")
                    fpath = img_dir / fname
                elif "svg" in ct:
                    fname = fname.replace(".jpg", ".svg")
                    fpath = img_dir / fname
                fpath.write_bytes(resp.content)
                paths.append(fname)
            except Exception as e:
                print(f"[DEBUG-IMG] FAILED url={full_url[:80]} err={e}", flush=True)

    return paths


# ── Skill scraper ──────────────────────────────────────────────────────────────

def scrape_skill(page, skill, subject, year, max_questions, img_dir, mcq_only=False):
    """
    Scrape one skill. Returns (questions_list, skipped_count).
    Repeat-detection: stop when the same stem prefix appears twice.
    If max_questions > 0, also stop at that hard cap.
    If mcq_only is True, skip any skill whose first question is not multiple-choice.
    """
    name = skill["name"]
    url  = skill["url"]
    session = requests.Session()
    for ck in page.context.cookies():
        session.cookies.set(ck['name'], ck['value'],
                            domain=ck.get('domain', '').lstrip('.'))

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
    except PWTimeout:
        print(f"  Timeout loading skill.", flush=True)
        return [], 0

    html = page.content()
    qtype = detect_type(html)

    if should_skip(qtype):
        p_skip(qtype, name)
        return [], 1

    if mcq_only and qtype != "multiple-choice":
        p_skip(f"{qtype} (not MCQ)", name)
        return [], 1

    try:
        page.wait_for_selector(".question-component", timeout=15000)
    except PWTimeout:
        print(f"  No question found.", flush=True)
        return [], 0

    deadline = time.time() + 15
    while time.time() < deadline:
        t = get_question_text(page)
        if t and len(t) > 5:
            break
        time.sleep(0.5)

    results    = []
    seen_stems = {}
    skipped    = 0
    prev_text  = ""

    while True:
        if max_questions > 0 and len(results) >= max_questions:
            break

        current_text = get_question_text(page)
        if not current_text or len(current_text) < 5 or current_text.startswith("Submit"):
            break

        html  = page.content()
        qtype = detect_type(html)

        if should_skip(qtype):
            p_skip(qtype, name)
            skipped += 1
            prev_text = current_text
            capture_answer(page, qtype)
            if not wait_for_new_question(page, prev_text):
                break
            continue

        qc      = page.query_selector(".question-component")
        full    = clean(qc.inner_text() if qc else "")
        choices = extract_choices(page, qtype)
        stem    = full
        if choices:
            idx = full.find(choices[0])
            if idx > 0:
                stem = full[:idx].strip()

        blanks = []
        if "fill" in qtype:
            inputs = page.query_selector_all("input[type='text'], input[type='number']")
            blanks = [clean(i.get_attribute("placeholder") or "") for i in inputs]

        img_paths = download_images(page, img_dir, session)
        if not img_paths:
            # Dump HTML once to help diagnose missing images
            debug_html = Path(img_dir.parent / "_debug_page.html")
            if not debug_html.exists():
                debug_html.write_text(page.content(), encoding="utf-8")
        correct   = capture_answer(page, qtype)

        # Repeat detection:
        # - If question has distinguishing content (text answer or images), stop at first exact repeat.
        # - If question is pure image with no extractable text or images, cap at 10 per stem
        #   since we can't tell questions apart but don't want to loop forever.
        if correct or img_paths:
            content_key = hashlib.md5((stem + str(correct) + str(sorted(img_paths))).encode()).hexdigest()
            seen_stems[content_key] = seen_stems.get(content_key, 0) + 1
            if seen_stems[content_key] >= 2:
                break
        else:
            stem_key = hashlib.md5(stem.encode()).hexdigest()
            seen_stems[stem_key] = seen_stems.get(stem_key, 0) + 1
            if seen_stems[stem_key] >= 10:
                break

        q_index = len(results) + 1
        p_question(q_index, qtype)

        results.append({
            "question_id":    make_question_id(subject, year, name, q_index),
            "subject":        subject,
            "year":           year,
            "skill_name":     name,
            "skill_url":      url,
            "question_index": q_index,
            "format":         qtype,
            "question_text":  stem[:4000],
            "options":        choices,
            "correct_answer": correct,
            "blank_count":    len(blanks),
            "has_image":      bool(img_paths),
            "image_paths":    img_paths,
            "scraped_at":     datetime.now(timezone.utc).isoformat(),
            "quiz_ready":     bool(correct),
        })

        prev_text = current_text
        if not wait_for_new_question(page, prev_text):
            break

    return results, skipped


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="IXL Unified Scraper")
    parser.add_argument("--subject",         required=True, choices=["maths","english","science"])
    parser.add_argument("--year",            required=True)
    parser.add_argument("--username",        required=True)
    parser.add_argument("--password",        required=True)
    parser.add_argument("--max-questions",   type=int, default=0)
    parser.add_argument("--output-dir",      default=None)
    parser.add_argument("--skills-file",     default=None, help="JSON file with [{name,url}] list")
    parser.add_argument("--discover-only",   action="store_true", help="Login, list skills as JSON, exit")
    parser.add_argument("--headless",        action="store_true")
    parser.add_argument("--mcq-only",        action="store_true", help="Skip non-multiple-choice skills")
    parser.add_argument("--checkpoint-file", default=None,
                        help="File tracking completed skill URLs for resume support (default: output-dir/checkpoint.txt)")
    args = parser.parse_args()

    if not args.discover_only and not args.output_dir:
        p_error("--output-dir is required unless --discover-only is set")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=args.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--no-first-run",
                "--mute-audio",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-AU",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        if not login(page, args.username, args.password):
            browser.close()
            sys.exit(1)

        # ── Discover-only mode ────────────────────────────────────────────────
        if args.discover_only:
            skills = get_skills(page, args.subject, args.year)
            print(f"[SKILLS] {json.dumps(skills, ensure_ascii=False)}", flush=True)
            browser.close()
            sys.exit(0)

        # ── Normal scrape mode ────────────────────────────────────────────────
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        img_dir = output_dir / "images"
        img_dir.mkdir(exist_ok=True)

        if args.skills_file:
            skills = json.loads(Path(args.skills_file).read_text(encoding="utf-8"))
        else:
            skills = get_skills(page, args.subject, args.year)
            if not skills:
                p_error("No skills found on index page")
                browser.close()
                sys.exit(1)

        # ── Checkpoint / resume ───────────────────────────────────────────────
        checkpoint_file = Path(args.checkpoint_file) if args.checkpoint_file \
                          else output_dir / "checkpoint.txt"
        completed_urls = set()
        if checkpoint_file.exists():
            completed_urls = {
                line.strip() for line in
                checkpoint_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        if completed_urls:
            p_resume(len(completed_urls), len(skills))

        # Load questions already saved from a previous interrupted run
        existing_file = output_dir / "questions.json"
        all_questions = []
        if existing_file.exists() and completed_urls:
            try:
                all_questions = json.loads(existing_file.read_text(encoding="utf-8"))
            except Exception:
                all_questions = []

        p_start(args.subject, args.year, len(skills))

        total_skipped = 0
        start_time = time.time()

        for i, skill in enumerate(skills, 1):
            if skill["url"] in completed_urls:
                p_skill_resume(skill["name"])
                continue

            p_skill(i, len(skills), skill["name"])
            qs, skipped = scrape_skill(
                page, skill, args.subject, args.year,
                args.max_questions, img_dir,
                mcq_only=args.mcq_only,
            )
            total_skipped += skipped
            all_questions.extend(qs)
            p_skill_done(len(qs))

            # Mark skill complete in checkpoint before saving questions,
            # so a crash mid-save doesn't mark it done without data.
            existing_file.write_text(
                json.dumps(all_questions, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            with open(checkpoint_file, "a", encoding="utf-8") as cf:
                cf.write(skill["url"] + "\n")

        browser.close()

    elapsed = time.time() - start_time
    p_done(len(all_questions), elapsed, total_skipped)


if __name__ == "__main__":
    main()
