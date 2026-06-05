"""
Year 1 English – Question Format Analyser
Visits 20 diverse skills and deep-inspects the DOM to classify every
question format (audio, image, MCQ, drag-drop, fill-in, etc.)
"""
import time, re, json
from playwright.sync_api import sync_playwright

USERNAME = "supersheldon1"
PASSWORD = "3ej#A!@QH%f6"

SKILLS_20 = [
    # ── Alphabet & letters ────────────────────────────────────────────────
    ("Find the letter in the alphabet: uppercase",
     "https://uk.ixl.com/english/year-1/find-the-letter-in-the-alphabet-uppercase"),
    ("Choose the letter that you hear: uppercase",
     "https://uk.ixl.com/english/year-1/choose-the-letter-that-you-hear-uppercase"),
    ("Put the letters in ABC order",
     "https://uk.ixl.com/english/year-1/put-the-letters-in-abc-order"),
    # ── Phonics / vowels / consonants ─────────────────────────────────────
    ("Sort consonants and vowels",
     "https://uk.ixl.com/english/year-1/sort-consonants-and-vowels"),
    ("How many syllables does the word have?",
     "https://uk.ixl.com/english/year-1/how-many-syllables-does-the-word-have"),
    ("Choose the picture that rhymes with the word",
     "https://uk.ixl.com/english/year-1/choose-the-picture-that-rhymes-with-the-word"),
    ("Which consonant blend does the word start with?",
     "https://uk.ixl.com/english/year-1/which-consonant-blend-does-the-word-start-with"),
    # ── Short vowel words ─────────────────────────────────────────────────
    ("Find the short a word",
     "https://uk.ixl.com/english/year-1/find-the-short-a-word"),
    ("Complete the short a word",
     "https://uk.ixl.com/english/year-1/complete-the-short-a-word"),
    ("Choose the short a sentence that matches the picture",
     "https://uk.ixl.com/english/year-1/choose-the-short-a-sentence-that-matches-the-picture"),
    # ── Sight words ───────────────────────────────────────────────────────
    ("Read sight words set 1",
     "https://uk.ixl.com/english/year-1/read-sight-words-set-1-ate-he-of-that-was"),
    ("Complete the sentence with the correct sight word",
     "https://uk.ixl.com/english/year-1/complete-the-sentence-with-the-correct-sight-word"),
    ("Spell the sight word",
     "https://uk.ixl.com/english/year-1/spell-the-sight-word"),
    # ── Vocabulary & comprehension ────────────────────────────────────────
    ("Which could happen in real life?",
     "https://uk.ixl.com/english/year-1/which-could-happen-in-real-life"),
    ("What will happen next?",
     "https://uk.ixl.com/english/year-1/what-will-happen-next"),
    ("Use colour words",
     "https://uk.ixl.com/english/year-1/use-colour-words"),
    ("Match antonyms to pictures",
     "https://uk.ixl.com/english/year-1/match-antonyms-to-pictures"),
    # ── Grammar & sentences ───────────────────────────────────────────────
    ("Is it a telling sentence or an asking sentence?",
     "https://uk.ixl.com/english/year-1/is-it-a-telling-sentence-or-an-asking-sentence"),
    ("Find the complete sentence",
     "https://uk.ixl.com/english/year-1/find-the-complete-sentence"),
    ("Unscramble the words to make a complete sentence",
     "https://uk.ixl.com/english/year-1/unscramble-the-words-to-make-a-complete-sentence"),
]

def clean(t): return re.sub(r"\s+", " ", t or "").strip()

def inspect(page, name, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2.5)
    except Exception as e:
        return {"skill": name, "url": url, "formats": ["ERROR"], "error": str(e)[:80]}

    html = page.content()
    r = {"skill": name, "url": url, "formats": [], "signals": [], "details": {}}

    # ── 1. Audio ───────────────────────────────────────────────────────────
    has_audio_class = bool(page.query_selector(
        "[class*='audio'], [class*='Audio'], [class*='speaker'], audio"))
    audio_btns = page.query_selector_all(
        "[class*='audio-button'], [class*='AudioButton'], [class*='audio-enabled'], [data-audio]")
    if has_audio_class or audio_btns:
        r["formats"].append("Audio")
        r["signals"].append(f"audio_class={has_audio_class}, audio_btns={len(audio_btns)}")

    # ── 2. Images in question area ─────────────────────────────────────────
    imgs = page.query_selector_all(".question-component img, [class*='TileMultipleChoices'] img")
    pic_tiles = page.query_selector_all(
        "[class*='PictureTile'], [class*='ImageTile'], [class*='image-tile'], [class*='picture-tile']")
    if imgs or pic_tiles:
        r["formats"].append("Image-Based")
        r["details"]["imgs_in_question"] = len(imgs)
        r["details"]["img_tiles"] = len(pic_tiles)
        r["signals"].append(f"imgs={len(imgs)}, img_tiles={len(pic_tiles)}")

    # ── 3. MCQ – text choices ──────────────────────────────────────────────
    mcq = page.query_selector_all(
        "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])")
    if mcq:
        texts = [clean(e.inner_text()) for e in mcq if clean(e.inner_text())]
        r["formats"].append("MCQ – Text Choices")
        r["details"]["options"] = texts
        r["signals"].append(f"MCQ tiles={len(mcq)}, texts={texts}")

    # ── 4. MCQ – image choices ─────────────────────────────────────────────
    img_choices = page.query_selector_all(
        "[class*='SelectableTile']:not([class*='nonInteractive']) img")
    if img_choices:
        r["formats"].append("MCQ – Image Choices")
        r["signals"].append(f"image choices={len(img_choices)}")

    # ── 5. Letter grid / alphabet picker ──────────────────────────────────
    single = page.query_selector_all(
        "[class*='SelectableTile'][class*='TEXT']:not([class*='nonInteractive'])")
    texts = [clean(e.inner_text()) for e in single]
    if len(single) > 10 and all(len(t) <= 2 for t in texts if t):
        r["formats"].append("Letter Grid Picker")
        r["details"]["grid_items"] = texts
        r["signals"].append(f"grid tiles={len(single)}, samples={texts[:5]}")

    # ── 6. Drag-and-Drop / Sort ────────────────────────────────────────────
    drag = page.query_selector_all("[draggable='true'], [class*='drag-item'], [class*='DragItem']")
    drop = page.query_selector_all("[class*='drop-target'], [class*='DropTarget'], [class*='DroppableZone']")
    if drag or drop:
        r["formats"].append("Drag-and-Drop / Sort")
        r["details"]["drag_items"] = len(drag)
        r["details"]["drop_zones"] = len(drop)
        r["signals"].append(f"drag={len(drag)}, drop={len(drop)}")

    # ── 7. Fill-in-the-Blank (typed input) ────────────────────────────────
    inputs = page.query_selector_all(
        "input[type='text']:not([id='siusername']), input[type='tel']")
    if inputs:
        placeholders = [e.get_attribute("placeholder") or "" for e in inputs]
        r["formats"].append("Fill-in-the-Blank (Typing)")
        r["details"]["inputs"] = len(inputs)
        r["details"]["placeholders"] = placeholders
        r["signals"].append(f"text_inputs={len(inputs)}, placeholders={placeholders}")

    # ── 8. Word Bank ───────────────────────────────────────────────────────
    wb = page.query_selector_all("[class*='WORD_BANK'], [class*='WordBank'], [class*='word-bank']")
    if wb:
        r["formats"].append("Word Bank")
        r["signals"].append(f"word_bank={len(wb)}")

    # ── 9. Click-to-Select (click a word/letter inside text) ──────────────
    click_on = page.query_selector_all("[class*='CLICK_ON'], [class*='clickable-word']")
    if click_on:
        r["formats"].append("Click-to-Select (in text)")
        r["signals"].append(f"click_on={len(click_on)}")

    # ── 10. Flashcard / Sight-word card ───────────────────────────────────
    fc = page.query_selector_all("[class*='flashcard'], [class*='FlashCard'], [class*='card-face']")
    if fc:
        r["formats"].append("Flashcard / Read-Aloud Card")
        r["signals"].append(f"flashcard={len(fc)}")

    # ── 11. Word-ordering / Unscramble (draggable word tiles) ─────────────
    # Detected via draggable tiles that contain multi-char text (words, not letters)
    drag_texts = [clean(e.inner_text()) for e in drag if clean(e.inner_text())]
    word_drags = [t for t in drag_texts if len(t) > 1]
    if word_drags and "Drag-and-Drop / Sort" not in r["formats"]:
        r["formats"].append("Word Ordering / Unscramble")
        r["signals"].append(f"word drag tiles={len(word_drags)}, words={word_drags[:5]}")
    elif word_drags and "Drag-and-Drop / Sort" in r["formats"]:
        # Refine existing drag tag
        r["details"]["drag_word_items"] = word_drags

    # ── 12. Matching ──────────────────────────────────────────────────────
    match = page.query_selector_all("[class*='MATCH'], [class*='Matching'], [class*='match-item']")
    if match:
        r["formats"].append("Matching / Pairing")
        r["signals"].append(f"match={len(match)}")

    # ── IXL internal type tokens present in HTML ───────────────────────────
    TOKENS = ["MULTIPLE_CHOICE","FILL_IN_THE_BLANK","FILL_IN","WORD_BANK",
              "CLICK_ON","SORT","DRAG","MATCH","SEQUENCE","AUDIO","GRID"]
    r["ixl_tokens"] = [t for t in TOKENS if t in html]

    # ── Question text ──────────────────────────────────────────────────────
    qc = page.query_selector(".question-component")
    r["question_text"] = clean(qc.inner_text())[:250] if qc else ""

    if not r["formats"]:
        r["formats"].append("Unknown / Not Detected")

    return r


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        locale="en-GB", viewport={"width":1280,"height":900})
    page = ctx.new_page()

    page.goto("https://uk.ixl.com/signin", wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)
    page.fill("#siusername", USERNAME); time.sleep(0.4)
    page.fill("#sipassword", PASSWORD); time.sleep(0.4)
    page.click("button.submit-button[type='submit']"); time.sleep(4)
    if page.query_selector(".subaccount-selection-form"):
        page.evaluate("document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] .signin-avatar').click()")
        time.sleep(3)
    print(f"Logged in: {page.title()}\n", flush=True)

    results = []
    for i, (name, url) in enumerate(SKILLS_20, 1):
        print(f"[{i:2d}/20] {name}", flush=True)
        r = inspect(page, name, url)
        results.append(r)
        print(f"        Formats  : {' + '.join(r['formats'])}", flush=True)
        print(f"        IXL tokens: {r['ixl_tokens']}", flush=True)
        print(f"        Q text    : {r['question_text'][:100]}", flush=True)
        print(flush=True)

    browser.close()

json.dump(results, open("/tmp/y1_analysis_data.json","w"), indent=2)
print("Done. Data → /tmp/y1_analysis_data.json", flush=True)
