"""Synthetic transcripts for tests, the stranger check and screenshots. Never real data.

python3 tests/synth.py HOME_DIR   writes a believable month of Claude Code, Codex and Cursor records under HOME_DIR.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone


def _w(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')


def claude_msg(ts, mid, cwd, model='claude-sonnet-5-5', inp=1200, out=400, read=20000, w5m=3000, tools=(), sid='s1', text='synthetic'):
    content = [{'type': 'text', 'text': text}] + [
        {'type': 'tool_use', 'id': 'tu_%s_%d' % (mid, i), 'name': name, 'input': {'file_path': path}} for i, (name, path) in enumerate(tools)]
    return {'type': 'assistant', 'timestamp': ts.isoformat().replace('+00:00', 'Z'), 'sessionId': sid, 'cwd': cwd,
            'message': {'id': mid, 'model': model, 'content': content,
                        'usage': {'input_tokens': inp, 'output_tokens': out, 'cache_read_input_tokens': read,
                                  'cache_creation_input_tokens': w5m}}}


def codex_file(path, cwd, model, start, steps, reset_at=None):
    """steps: list of (input, cached, output). Writes cumulative token_count events, with optional reset."""
    recs = [{'type': 'session_meta', 'timestamp': start.isoformat(), 'payload': {'id': os.path.basename(path), 'cwd': cwd}},
            {'type': 'turn_context', 'timestamp': start.isoformat(), 'payload': {'model': model, 'cwd': cwd}}]
    tot = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0, 'reasoning_output_tokens': 0, 'total_tokens': 0}
    for i, (inp, cached, out) in enumerate(steps):
        if reset_at == i:
            tot = {k: 0 for k in tot}
        last = {'input_tokens': inp, 'cached_input_tokens': cached, 'output_tokens': out, 'reasoning_output_tokens': out // 3, 'total_tokens': inp + out}
        for k in tot:
            tot[k] += last[k]
        ts = (start + timedelta(minutes=3 * i + 1)).isoformat()
        recs.append({'type': 'event_msg', 'timestamp': ts, 'payload': {'type': 'token_count', 'info': {'total_token_usage': dict(tot), 'last_token_usage': last}}})
        recs.append({'type': 'event_msg', 'timestamp': ts, 'payload': {'type': 'token_count', 'info': None}})  # rate-limit notice
    _w(path, recs)


def month(home, seed=7, days=30):
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    code = os.path.join(home, 'code')
    projects = {'shop-api': 1.0, 'field-notes': 0.45, 'data-pipeline': 0.7, 'landing-page': 0.25}
    for p in projects:
        os.makedirs(os.path.join(code, p), exist_ok=True)
    claude_dir = os.path.join(home, '.claude', 'projects')
    n = 0
    for d in range(days):
        day = now - timedelta(days=d, hours=rnd.randint(0, 6))
        for p, weight in projects.items():
            if rnd.random() > weight:
                continue
            recs = []
            sid = 'sess-%d-%s' % (d, p)
            for k in range(rnd.randint(4, 18)):
                n += 1
                ts = day + timedelta(minutes=2 * k)
                model = rnd.choice(['claude-sonnet-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5'])
                m = claude_msg(ts, 'msg_%06d' % n, os.path.join(code, p), model=model, inp=rnd.randint(200, 3000),
                               out=rnd.randint(150, 2500), read=rnd.randint(8000, 90000), w5m=rnd.randint(0, 8000), sid=sid)
                # Streamed: a placeholder first record, then the final record of the same message.
                first = json.loads(json.dumps(m))
                first['message']['usage']['output_tokens'] = 2
                recs += [first, m]
            _w(os.path.join(claude_dir, '-code-' + p, sid + '.jsonl'), recs)
        if d % 3 == 0:  # a home-folder session that edits one project: placed by files touched
            sid = 'home-%d' % d
            recs = [claude_msg(day + timedelta(hours=2, minutes=k), 'msg_h%d_%d' % (d, k), home, inp=900, out=700, read=30000,
                               tools=[('Edit', os.path.join(code, 'field-notes', 'draft.md'))], sid=sid) for k in range(5)]
            # and one that reads several projects: unknown
            recs += [claude_msg(day + timedelta(hours=3, minutes=k), 'msg_u%d_%d' % (d, k), home, inp=800, out=500, read=40000,
                                tools=[('Read', os.path.join(code, 'shop-api', 'a.py')), ('Read', os.path.join(code, 'landing-page', 'b.html'))], sid=sid)
                     for k in range(6)]
            _w(os.path.join(claude_dir, '-home', sid + '.jsonl'), recs)
    codex_dir = os.path.join(home, '.codex', 'sessions')
    for d in range(0, days, 2):
        start = now - timedelta(days=d, hours=4)
        steps = [(rnd.randint(20000, 120000), rnd.randint(10000, 60000) // 2, rnd.randint(500, 6000)) for _ in range(rnd.randint(3, 9))]
        steps = [(i, min(c, i), o) for i, c, o in steps]
        where = os.path.join(code, 'data-pipeline') if d % 4 == 0 else home
        codex_file(os.path.join(codex_dir, start.strftime('%Y/%m/%d'), 'rollout-%d.jsonl' % d), where, 'gpt-6.1-sol', start, steps)
    csv_path = os.path.join(home, 'Downloads', 'cursor-usage-export.csv')
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write('Date,Kind,Model,Input (w/ Cache Write),Input (w/o Cache Write),Cache Read,Output Tokens,Total Tokens,Cost\n')
        for d in range(0, days, 3):
            t = (now - timedelta(days=d)).isoformat()
            a, b, c, o = 1000, 4000, 30000, 2000
            f.write('%s,Included in Pro,auto,%d,%d,%d,%d,%d,Included\n' % (t, a, b, c, o, a + b + c + o))
    return csv_path


if __name__ == '__main__':
    print(month(sys.argv[1]))
