import json
from datetime import datetime, timezone

MAX_LINE = 64 * 1024 * 1024


def parse_ts(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iter_json(path):
    """Each JSON object line of a file. Broken lines and oversized lines are skipped, never fatal."""
    try:
        f = open(path, 'rb')
    except OSError:
        return
    with f:
        while True:
            raw = f.readline(MAX_LINE + 1)
            if not raw:
                break
            if len(raw) > MAX_LINE:
                while raw and not raw.endswith(b'\n'):
                    raw = f.readline(MAX_LINE + 1)
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if isinstance(d, dict):
                yield d
