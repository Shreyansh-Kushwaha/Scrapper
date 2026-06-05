"""
IXL Year 1 English — Image Scraper
For every question:
  - Downloads all question images (stimulus + answer option images)
  - Records alt text (describes what the image shows)
  - Takes a full screenshot of the question area
  - Saves rich JSON with image paths + alt texts
  - Output: ixl_images/ folder + ixl_image_questions.json
"""

import json, re, time, os, hashlib, requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from datetime import datetime, timezone

USERNAME    = "supersheldon1"
PASSWORD    = "3ej#A!@QH%f6"
BASE_URL    = "https://uk.ixl.com"
OUTPUT_DIR  = Path("ixl_images")
OUTPUT_JSON = "ixl_image_questions.json"
MAX_Q       = 3     # questions per skill

# IXL toolbar image alt texts to skip
SKIP_ALTS = {"Scratchpad","Eraser","Highlighter - blue","Highlighter - yellow",
             "Highlighter - pink","Pencil - black","Pencil - blue","Pencil - red",
             "Pencil - green","Ruler","Protractor","Calculator"}

# 8 image-rich skills covering every image question type
SKILLS = [
    ("Choose the picture that rhymes with the word",
     "https://uk.ixl.com/english/year-1/choose-the-picture-that-rhymes-with-the-word",
     "Audio MCQ – Image Choices"),

    ("Which could happen in real life?",
     "https://uk.ixl.com/english/year-1/which-could-happen-in-real-life",
     "Image MCQ – Pick Image"),

    ("Match antonyms to pictures",
     "https://uk.ixl.com/english/year-1/match-antonyms-to-pictures",
     "Matching – Word to Image"),

    ("What will happen next?",
     "https://uk.ixl.com/english/year-1/what-will-happen-next",
     "Image MCQ – Pick Image"),

    ("Find the short a word",
     "https://uk.ixl.com/english/year-1/find-the-short-a-word",
     "Audio MCQ – Image Choices"),

    ("Choose the short a sentence that matches the picture",
     "https://uk.ixl.com/english/year-1/choose-the-short-a-sentence-that-matches-the-picture",
     "Image MCQ – Pick Text"),

    ("Compare pictures using adjectives",
     "https://uk.ixl.com/english/year-1/compare-pictures-using-adjectives",
     "Image MCQ – Text Choices"),

    ("Which feeling matches the picture?",
     "https://uk.ixl.com/english/year-1/which-feeling-matches-the-picture",
     "Image MCQ – Text Choices"),
]


def clean(t): return re.sub(r"\s+", " ", t or "").strip()


# ── Image downloader ──────────────────────────────────────────────────────────

def download_image(src: str, folder: Path, session: requests.Session) -> dict | None:
    """Download an image and return its local path + metadata."""
    if src.startswith("data:"):
        # base64 SVG or similar — skip (toolbar icons)
        return None

    full_url = src if src.startswith("http") else f"{BASE_URL}{src}"
    # Use a hash of the URL as the filename
    ext = "jpg"  # IXL media is usually JPEG
    fname = hashlib.md5(full_url.encode()).hexdigest()[:16] + f".{ext}"
    fpath = folder / fname

    if fpath.exists():
        return {"local_path": str(fpath), "url": full_url, "cached": True}

    try:
        resp = session.get(full_url, timeout=10)
        resp.raise_for_status()
        # Detect extension from content-type
        ct = resp.headers.get("content-type","")
        if "png" in ct:
            fname = fname.replace(".jpg", ".png")
            fpath = folder / fname
        elif "webp" in ct:
            fname = fname.replace(".jpg", ".webp")
            fpath = folder / fname
        fpath.write_bytes(resp.content)
        return {"local_path": str(fpath), "url": full_url, "size_bytes": len(resp.content), "content_type": ct}
    except Exception as e:
        return {"url": full_url, "error": str(e)[:60]}


# ── Question screenshot ───────────────────────────────────────────────────────

def screenshot_question(page, folder: Path, label: str) -> str | None:
    """Take a screenshot of the .question-and-submission-view area."""
    el = page.query_selector(".question-and-submission-view")
    if not el:
        el = page.query_selector(".question-component")
    if not el:
        return None
    fname = re.sub(r"[^a-z0-9]+", "_", label.lower())[:40] + ".png"
    fpath = folder / fname
    try:
        el.screenshot(path=str(fpath))
        return str(fpath)
    except Exception:
        return None


# ── Extract images from current page ─────────────────────────────────────────

def extract_images(page, session: requests.Session, img_folder: Path) -> list[dict]:
    """Find all question images, download them, return structured records."""
    images = []

    # Target: images inside the active (non-disabled) question area
    selectors = [
        ".question-and-submission-view img",
        ".question-component img",
        "[class*='TileMultipleChoices'] img",
        "[class*='SelectableTile']:not([class*='nonInteractive']) img",
        "[class*='stimulus'] img",
        "[class*='Stimulus'] img",
        "[class*='picture'] img",
    ]

    seen_srcs = set()
    for sel in selectors:
        for img in page.query_selector_all(sel):
            src = img.get_attribute("src") or ""
            alt = clean(img.get_attribute("alt") or "")

            # Skip toolbar icons and data-URIs
            if not src or src in seen_srcs:
                continue
            if src.startswith("data:"):
                continue
            if alt in SKIP_ALTS:
                continue
            seen_srcs.add(src)

            # Get parent element context (is this a choice tile?)
            parent_cls = ""
            try:
                parent = page.evaluate("el => el.closest('[class]')?.className || ''", img)
                parent_cls = parent[:80]
            except Exception:
                pass

            is_choice = "SelectableTile" in parent_cls or "TileMultipleChoices" in parent_cls

            # Download
            dl = download_image(src, img_folder, session)

            record = {
                "alt_text":       alt,
                "src_url":        src if src.startswith("http") else f"{BASE_URL}{src}",
                "is_answer_choice": is_choice,
                "parent_class":   parent_cls,
            }
            if dl:
                record.update(dl)

            images.append(record)
            print(f"        img: alt={alt!r:35}  choice={is_choice}  dl={'ok' if dl and 'error' not in dl else 'fail'}",
                  flush=True)

    return images


# ── Submit and advance ────────────────────────────────────────────────────────

def click_crisp(page, label):
    for b in page.query_selector_all("button.crisp-button"):
        if (b.inner_text() or "").strip() == label and b.bounding_box():
            try:
                b.scroll_into_view_if_needed(); time.sleep(0.15)
                b.click(force=True, timeout=5000); return True
            except Exception: pass
    return False

def qc_text(page):
    el = page.query_selector(".question-component")
    return clean(el.inner_text() if el else "")

def is_real(txt): return len(txt) > 15 and not txt.startswith("Submit")

def advance(page, prev):
    try:
        page.locator(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        ).first.click(force=True, timeout=5000); time.sleep(0.4)
    except Exception: pass
    if not click_crisp(page, "Submit"): page.keyboard.press("Enter")
    time.sleep(1.5)
    for lbl in ("Got it","Next","Continue","OK"):
        if click_crisp(page, lbl): time.sleep(0.8); break
    deadline = time.time() + 12
    while time.time() < deadline:
        cur = qc_text(page)
        if is_real(cur) and cur[:80] != prev[:80]: return True
        for lbl in ("Got it","Next","Continue"):
            if click_crisp(page, lbl): time.sleep(0.6); break
        time.sleep(0.4)
    return False


# ── Login ─────────────────────────────────────────────────────────────────────

def login(page):
    print("Logging in …", flush=True)
    page.goto("https://uk.ixl.com/signin", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)
    page.fill("#siusername", USERNAME); time.sleep(0.4)
    page.fill("#sipassword", PASSWORD); time.sleep(0.4)
    page.click("button.submit-button[type='submit']"); time.sleep(4)
    if page.query_selector(".subaccount-selection-form"):
        page.evaluate(
            "document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] .signin-avatar').click()"
        ); time.sleep(3)
    print(f"  {page.title()}\n", flush=True)


# ── Scrape one skill ──────────────────────────────────────────────────────────

def scrape_skill(page, session, name, url, q_type):
    print(f"\n{'─'*60}", flush=True)
    print(f"Skill : {name}", flush=True)
    print(f"Type  : {q_type}", flush=True)

    skill_folder = OUTPUT_DIR / re.sub(r"[^a-z0-9]+", "_", name.lower())[:35]
    skill_folder.mkdir(parents=True, exist_ok=True)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000); time.sleep(2)
    except PWTimeout:
        print("  Timeout.", flush=True); return []

    # Wait for question
    deadline = time.time() + 12
    while time.time() < deadline:
        if is_real(qc_text(page)): break
        time.sleep(0.5)
    else:
        print("  No question.", flush=True); return []

    results, seen = [], set()

    for q_idx in range(MAX_Q):
        cur = qc_text(page)
        if not is_real(cur): break
        fp = cur[:80]
        if fp in seen:
            if not advance(page, cur): break
            continue
        seen.add(fp)

        q_folder = skill_folder / f"q{q_idx+1}"
        q_folder.mkdir(exist_ok=True)

        print(f"\n  Q{q_idx+1}: {cur[:80]}…", flush=True)

        # Screenshot the question area
        ss_path = screenshot_question(page, q_folder, f"q{q_idx+1}")
        print(f"  Screenshot: {ss_path}", flush=True)

        # Extract + download images
        images = extract_images(page, session, q_folder)

        # Extract text choices (if any)
        text_choices = []
        mcq = page.query_selector_all(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])")
        for el in mcq:
            t = clean(el.inner_text())
            has_img = bool(el.query_selector("img"))
            if t and not has_img:
                text_choices.append(t)

        record = {
            "question_id":       f"ixl-y1-{re.sub(r'[^a-z0-9]+','-',name.lower())[:25]}-q{q_idx+1}",
            "year":              "Year 1",
            "subject":           "English",
            "skill_name":        name,
            "skill_url":         url,
            "question_type":     q_type,
            "question_index":    q_idx + 1,
            "question_text":     cur,
            "text_options":      text_choices,
            "images":            images,
            "screenshot":        ss_path,
            "num_images":        len(images),
            "has_image_options": any(i.get("is_answer_choice") for i in images),
            "scraped_at":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        results.append(record)
        print(f"  Images: {len(images)}  |  Text choices: {text_choices}", flush=True)

        if not advance(page, cur): break

    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    )

    all_records = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(
            user_agent=session.headers["User-Agent"],
            locale="en-GB", viewport={"width":1280,"height":900})
        page = ctx.new_page()
        login(page)

        for i, (name, url, q_type) in enumerate(SKILLS, 1):
            print(f"\n[{i}/{len(SKILLS)}]", flush=True)
            records = scrape_skill(page, session, name, url, q_type)
            all_records.extend(records)
            print(f"  → collected {len(records)} question(s)", flush=True)

        browser.close()

    # Save JSON
    Path(OUTPUT_JSON).write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8")

    total_imgs = sum(r["num_images"] for r in all_records)
    print(f"\n{'═'*55}", flush=True)
    print(f"Questions  : {len(all_records)}", flush=True)
    print(f"Total imgs : {total_imgs}", flush=True)
    print(f"JSON saved : {OUTPUT_JSON}", flush=True)
    print(f"Images in  : {OUTPUT_DIR}/", flush=True)

    # Show sample
    if all_records:
        r = all_records[0]
        print(f"\n── Sample record ───────────────────────────────────────", flush=True)
        r_display = dict(r)
        r_display["images"] = [
            {k:v for k,v in img.items() if k != "local_path"} for img in r["images"]
        ]
        print(json.dumps(r_display, indent=2)[:1800], flush=True)


if __name__ == "__main__":
    main()
