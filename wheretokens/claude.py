"""Claude Code: ~/.claude/projects/**/*.jsonl, metadata fields only.

Kept from each record: timestamp, message id, model, token counters, the working folder, and the
path ARGUMENT of file tools (used in memory for attribution, then dropped). Prompt text, reply text,
file contents and tool results are never read into any number.
"""
import glob
import os
from datetime import datetime

from . import prices
from .config import clean
from .util import iter_json, parse_ts

FILE_TOOLS = ('Read', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Glob', 'Grep')


def roots():
    extra = os.environ.get('TOKENS_CLAUDE_DIRS')
    if extra:
        return [os.path.expanduser(p) for p in extra.split(os.pathsep) if p]
    base = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')
    return [os.path.join(base, 'projects')]


def files(dirs=None):
    out = []
    for d in dirs or roots():
        out += glob.glob(os.path.join(d, '**', '*.jsonl'), recursive=True)
    return sorted(set(out))


def _touched(msg):
    found = []
    blocks = msg.get('content') if isinstance(msg.get('content'), list) else []
    for b in blocks:
        if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') in FILE_TOOLS and isinstance(b.get('input'), dict):
            for arg in ('file_path', 'path', 'notebook_path'):
                v = b['input'].get(arg)
                if isinstance(v, str) and v.startswith('/'):
                    found.append(v)
    return found


def _key(d, msg):
    """Claude Code writes one line per content block of the same API message and repeats the usage
    on each. Summing lines over-counts. One count per API message id."""
    return msg.get('id') or d.get('requestId') or d.get('uuid')


def read(attributor, since=None, dirs=None):
    """One row per counted message: (local day, project, reason, model, tokens, usd or None).

    The records of one message do not all carry the same usage: the first record of a streamed
    message can carry a placeholder output count. So each message is counted at its record with the
    largest total. Ties keep the first record.
    """
    turns, stats = {}, {'files': 0, 'records_repeated': 0, 'placeholders_replaced': 0, 'no_identity': 0, 'bad_timestamp': 0}
    for f in files(dirs):
        if since and os.path.getmtime(f) < since.timestamp():
            continue
        stats['files'] += 1
        for d in iter_json(f):
            if d.get('type') != 'assistant':
                continue
            msg = d.get('message')
            if not isinstance(msg, dict) or not msg.get('usage'):
                continue
            ts = parse_ts(d.get('timestamp'))
            if ts is None:
                stats['bad_timestamp'] += 1
                continue
            if since and ts < since:
                continue
            key = _key(d, msg)
            if key is None:
                stats['no_identity'] += 1
                key = ('anon', f, d.get('timestamp'))
            usd, tok = prices.price_claude(msg.get('model'), msg['usage'])
            files_touched = _touched(msg)
            if key in turns:
                t = turns[key]
                stats['records_repeated'] += 1
                t['files'] += files_touched
                if tok['total'] > t['tok']['total']:
                    if not t['replaced']:
                        stats['placeholders_replaced'] += 1
                        t['replaced'] = True
                    t['tok'], t['usd'] = tok, usd
                continue
            turns[key] = {'ts': ts, 'model': prices.normalise_model(msg.get('model')), 'cwd': d.get('cwd') or '',
                          'files': files_touched, 'tok': tok, 'usd': usd, 'replaced': False}
    rows = []
    for t in turns.values():
        project, reason = attributor.attribute(t['cwd'], t['files'])
        k = t['tok']
        rows.append({'day': t['ts'].astimezone().strftime('%Y-%m-%d'), 'tool': 'Claude Code', 'project': project,
                     'reason': reason, 'model': clean(t['model']), 'input': k['input'], 'output': k['output'],
                     'cache_read': k['cache_read'], 'cache_write': k['cache_write_5m'] + k['cache_write_1h'],
                     'total': k['total'], 'usd': t['usd']})
    stats['messages'] = len(turns)
    return rows, stats
