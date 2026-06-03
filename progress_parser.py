import re

def parse_line(line):
    line = line.strip()
    if not line:
        return None

    if line.startswith('[START]'):
        m = re.match(r'\[START\] subject=(\S+) year=(\S+) total_skills=(\d+)', line)
        if m:
            return {'type': 'start', 'subject': m.group(1), 'year': m.group(2),
                    'total_skills': int(m.group(3))}

    elif line.startswith('[SKILL]'):
        m = re.match(r'\[SKILL\] (\d+)/(\d+) (.+)', line)
        if m:
            return {'type': 'skill', 'current': int(m.group(1)),
                    'total': int(m.group(2)), 'name': m.group(3)}

    elif line.startswith('[QUESTION]'):
        m = re.match(r'\[QUESTION\] q=(\d+) format=(\S+)', line)
        if m:
            return {'type': 'question', 'q': int(m.group(1)), 'format': m.group(2)}

    elif line.startswith('[SKIP]'):
        m = re.match(r'\[SKIP\] format=(\S+) skill=(.+)', line)
        if m:
            return {'type': 'skip', 'format': m.group(1), 'skill': m.group(2)}

    elif line.startswith('[SKILL_DONE]'):
        m = re.match(r'\[SKILL_DONE\] questions=(\d+)', line)
        if m:
            return {'type': 'skill_done', 'questions': int(m.group(1))}

    elif line.startswith('[DONE]'):
        m = re.match(r'\[DONE\] total_questions=(\d+) elapsed=(\d+)s skipped=(\d+)', line)
        if m:
            return {'type': 'done', 'total_questions': int(m.group(1)),
                    'elapsed': int(m.group(2)), 'skipped': int(m.group(3))}

    elif line.startswith('[ERROR]'):
        return {'type': 'error', 'message': line[7:].strip()}

    return None
