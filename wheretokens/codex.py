"""Codex: rollout files under ~/.codex/sessions and ~/.codex/archived_sessions.

Codex logs CUMULATIVE token counters. Each file is differenced on its own, in time order:
  - a repeated snapshot (same counters) is dropped
  - a counter that goes DOWN is a reset: that row is excluded, not guessed, and becomes the new baseline
  - an event copied into a forked or resumed session (same timestamp, model and counters) counts once
  - an increment is priced only when it equals the "last request" counters Codex logged beside it;
    otherwise it is counted as tokens with no price, because one aggregate delta cannot say which
    request size or long-context rate applied
Kept: timestamp, model, counters, working folder. No prompt or reply text.
"""
import glob
import json
import os

from . import prices
from .config import clean
from .util import iter_json, parse_ts

FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
          'output_tokens', 'reasoning_output_tokens', 'total_tokens')
OPTIONAL = ('cached_input_tokens', 'cache_write_input_tokens', 'reasoning_output_tokens')


def roots():
    extra = os.environ.get('TOKENS_CODEX_DIRS')
    if extra:
        return [os.path.expanduser(p) for p in extra.split(os.pathsep) if p]
    base = os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex')
    return [os.path.join(base, 'sessions'), os.path.join(base, 'archived_sessions')]


def files(dirs=None):
    out = []
    for d in dirs or roots():
        out += glob.glob(os.path.join(d, '**', '*.jsonl'), recursive=True)
    return sorted(set(out))


def normalise(raw):
    """Cache reads and writes are inside input; reasoning is inside output."""
    if not isinstance(raw, dict):
        raise ValueError('missing_usage')
    u = {}
    for k in FIELDS:
        v = raw.get(k, 0 if k in OPTIONAL else None)
        if type(v) is not int or v < 0:
            raise ValueError('invalid_usage')
        u[k] = v
    if (u['cached_input_tokens'] + u['cache_write_input_tokens'] > u['input_tokens']
            or u['reasoning_output_tokens'] > u['output_tokens']
            or u['total_tokens'] != u['input_tokens'] + u['output_tokens']):
        raise ValueError('invalid_usage')
    return u


def read(attributor, since=None, dirs=None):
    stats = {'files': 0, 'increments': 0, 'repeated_snapshots': 0, 'counter_resets': 0,
             'unreconciled': 0, 'invalid_usage': 0, 'bad_timestamp': 0}
    groups = {}
    paths = files(dirs)
    for path in paths:
        stats['files'] += 1
        model, cwd = '(unknown)', ''
        g = groups.setdefault(path, {})
        for d in iter_json(path):
            p = d.get('payload')
            if not isinstance(p, dict):
                continue
            if d.get('type') == 'session_meta':
                cwd = p.get('cwd') or cwd
            elif d.get('type') == 'turn_context':
                model = p.get('model') or model
                cwd = p.get('cwd') or cwd
            elif d.get('type') == 'event_msg' and p.get('type') == 'token_count':
                info = p.get('info')
                if info is None:  # rate-limit notices carry no usage
                    continue
                if not isinstance(info, dict):
                    stats['invalid_usage'] += 1
                    continue
                ts = parse_ts(d.get('timestamp'))
                if ts is None:
                    stats['bad_timestamp'] += 1
                    continue
                key = json.dumps([d.get('timestamp'), model, info.get('total_token_usage'), info.get('last_token_usage')], sort_keys=True)
                if key in g:
                    stats['repeated_snapshots'] += 1
                else:
                    g[key] = (ts, model, info.get('total_token_usage'), info.get('last_token_usage'), cwd)
    rows, seen = [], set()
    for path, group in sorted(groups.items()):
        previous = {k: 0 for k in FIELDS}
        seen_totals = set()
        # The window is applied after differencing: filtering first would charge all earlier usage to the first new row.
        for ts, model, raw_total, raw_last, cwd in sorted(group.values(), key=lambda r: r[0]):
            inside = since is None or ts >= since
            try:
                total = normalise(raw_total)
            except ValueError:
                stats['invalid_usage'] += inside
                continue
            sig = tuple(total[k] for k in FIELDS)
            if sig in seen_totals:
                stats['repeated_snapshots'] += inside
                continue
            seen_totals.add(sig)
            delta = {k: total[k] - previous[k] for k in FIELDS}
            if any(v < 0 for v in delta.values()):
                previous = total
                stats['counter_resets'] += inside
                continue
            previous = total
            if not inside or not delta['total_tokens']:
                continue
            try:
                delta = normalise(delta)
            except ValueError:
                stats['invalid_usage'] += 1
                continue
            event = (ts.isoformat(), model, sig)
            if event in seen:
                stats['repeated_snapshots'] += 1
                continue
            seen.add(event)
            try:
                reconciled = normalise(raw_last) == delta
            except ValueError:
                reconciled = False
            if not reconciled:
                stats['unreconciled'] += 1
            usd = prices.price_codex(model, delta) if reconciled else None
            project, reason = attributor.attribute(cwd)
            stats['increments'] += 1
            rows.append({'day': ts.astimezone().strftime('%Y-%m-%d'), 'tool': 'Codex', 'project': project,
                         'reason': reason, 'model': clean(model),
                         'input': delta['input_tokens'] - delta['cached_input_tokens'] - delta['cache_write_input_tokens'],
                         'output': delta['output_tokens'], 'cache_read': delta['cached_input_tokens'],
                         'cache_write': delta['cache_write_input_tokens'], 'total': delta['total_tokens'], 'usd': usd})
    return rows, stats
