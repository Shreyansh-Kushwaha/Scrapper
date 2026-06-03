from progress_parser import parse_line

def test_parse_start():
    r = parse_line('[START] subject=maths year=year-12 total_skills=290')
    assert r == {'type': 'start', 'subject': 'maths', 'year': 'year-12', 'total_skills': 290}

def test_parse_skill():
    r = parse_line('[SKILL] 5/290 Solve linear equations')
    assert r == {'type': 'skill', 'current': 5, 'total': 290, 'name': 'Solve linear equations'}

def test_parse_question():
    r = parse_line('[QUESTION] q=3 format=fill-in-blank')
    assert r == {'type': 'question', 'q': 3, 'format': 'fill-in-blank'}

def test_parse_skip():
    r = parse_line('[SKIP] format=interactive-graph skill=Plot a function')
    assert r == {'type': 'skip', 'format': 'interactive-graph', 'skill': 'Plot a function'}

def test_parse_skill_done():
    r = parse_line('[SKILL_DONE] questions=24')
    assert r == {'type': 'skill_done', 'questions': 24}

def test_parse_done():
    r = parse_line('[DONE] total_questions=5600 elapsed=6420s skipped=23')
    assert r == {'type': 'done', 'total_questions': 5600, 'elapsed': 6420, 'skipped': 23}

def test_parse_error():
    r = parse_line('[ERROR] Login failed — check credentials')
    assert r == {'type': 'error', 'message': 'Login failed — check credentials'}

def test_parse_unknown_returns_none():
    assert parse_line('some random line') is None

def test_parse_empty_returns_none():
    assert parse_line('') is None
