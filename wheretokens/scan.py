"""One scan: read every source, attribute, fold into daily cells, write inventory.json in the data folder."""
import json
import os
import time
from datetime import datetime, timedelta, timezone

from . import __version__, claude, codex, config, cursor, prices

INVENTORY = 'inventory.json'
FIELDS = ['day', 'tool', 'project', 'reason', 'model', 'input', 'output', 'cache_read', 'cache_write',
          'total', 'usd', 'unpriced_tokens', 'messages', 'stated_usd']


def fold(rows):
    cells = {}
    for r in rows:
        k = (r['day'], r['tool'], r['project'], r['reason'], r['model'])
        c = cells.setdefault(k, [0, 0, 0, 0, 0, 0.0, 0, 0, 0.0])
        for i, f in enumerate(('input', 'output', 'cache_read', 'cache_write', 'total')):
            c[i] += r[f]
        if r['usd'] is None:
            c[6] += r['total']
        else:
            c[5] += r['usd']
        c[7] += 1
        c[8] += r.get('stated_usd') or 0.0
    return [list(k) + [round(x, 6) if isinstance(x, float) else x for x in v] for k, v in sorted(cells.items())]


def run(days=None):
    started = time.time()
    cfg = config.load()
    prices.apply_overrides(cfg)
    attributor = config.Attributor(cfg)
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    data = config.data_dir()
    c_rows, c_stats = claude.read(attributor, since)
    x_rows, x_stats = codex.read(attributor, since)
    u_rows, u_stats = cursor.rows(data)
    out = {
        'version': __version__,
        'scanned_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'seconds': round(time.time() - started, 2),
        'window_days': days,
        'valuation': prices.VALUATION,
        'prices': {'claude': {'date': prices.CLAUDE_PRICE_DATE, 'source': prices.CLAUDE_PRICE_SOURCE},
                   'codex': {'date': prices.CODEX_PRICE_DATE, 'source': prices.CODEX_PRICE_SOURCE}},
        'sources': {
            'Claude Code': {'looked_in': [config.tilde(p) for p in claude.roots()], **c_stats},
            'Codex': {'looked_in': [config.tilde(p) for p in codex.roots()], **x_stats},
            'Cursor': {'looked_in': [config.tilde(os.path.join(data, cursor.FILE))], 'imported': u_stats is not None, **(u_stats or {})},
        },
        'rules': len(attributor.rules),
        'fields': FIELDS,
        'cells': fold(c_rows + x_rows + u_rows),
    }
    path = os.path.join(data, INVENTORY)
    config.private_write(path, out)
    return out, path


def load():
    path = os.path.join(config.data_dir(), INVENTORY)
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)
