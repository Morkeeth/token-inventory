"""Cursor: the usage export you download from your Cursor dashboard (a CSV file).

Cursor keeps no local token counters this tool can read, and this tool never logs in anywhere.
`tokens import-cursor FILE.csv` reads the file you point at and keeps sums per day, model and kind.
No list price is applied. The Cost column is kept as "cost as stated in the export": it can be a
number, or Included, or Free, and the file does not say what was billed. It is never added to the
list-price estimate. Cursor rows have no working folder, so their project is unknown.
"""
import csv
import json
import os
from datetime import datetime

from .config import clean

FILE = 'cursor-usage.json'
NEEDED = ('Date', 'Kind', 'Model', 'Total Tokens', 'Cost')


def _int(v):
    v = str(v or '').strip().replace(',', '')
    return int(v) if v.isdigit() else 0


def _cost(v):
    v = str(v or '').strip()
    try:
        return float(v.replace('$', '').replace(',', '')), 'number'
    except ValueError:
        return None, v.lower() if v.lower() in ('included', 'free') else ('blank' if not v else 'other')


def read_csv(path):
    with open(os.path.expanduser(path), encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        missing = [c for c in NEEDED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError('this is not a Cursor usage export: column %s is missing' % ', '.join(missing))
        cells, seen, stats = {}, set(), {'rows': 0, 'copies': 0, 'bad_date': 0, 'cost_kinds': {}}
        for r in reader:
            key = tuple(r.get(c) for c in reader.fieldnames)
            if key in seen:
                stats['copies'] += 1
                continue
            seen.add(key)
            try:
                when = datetime.fromisoformat(str(r['Date']).replace('Z', '+00:00')).astimezone()
            except ValueError:
                stats['bad_date'] += 1
                continue
            stats['rows'] += 1
            stated, kind = _cost(r['Cost'])
            stats['cost_kinds'][kind] = stats['cost_kinds'].get(kind, 0) + 1
            k = (when.strftime('%Y-%m-%d'), clean(r['Model'] or '(unknown)'), clean(r['Kind'] or '(unknown)', 40))
            c = cells.setdefault(k, {'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0, 'total': 0, 'stated_usd': 0.0, 'rows': 0})
            c['cache_write'] += _int(r.get('Input (w/ Cache Write)'))
            c['input'] += _int(r.get('Input (w/o Cache Write)'))
            c['cache_read'] += _int(r.get('Cache Read'))
            c['output'] += _int(r.get('Output Tokens'))
            c['total'] += _int(r['Total Tokens'])
            c['stated_usd'] += stated or 0.0
            c['rows'] += 1
    return {'cells': [dict(day=d, model=m, kind=k, **v) for (d, m, k), v in sorted(cells.items())], 'stats': stats}


def import_file(path, data_dir):
    real = os.path.realpath(os.path.expanduser(path))
    if not real.lower().endswith('.csv') or not os.path.isfile(real):
        raise ValueError('give the path of the .csv file you downloaded from Cursor')
    out = read_csv(real)
    with open(os.path.join(data_dir, FILE), 'w', encoding='utf-8') as f:
        json.dump(out, f)
    return out


def rows(data_dir):
    path = os.path.join(data_dir, FILE)
    if not os.path.isfile(path):
        return [], None
    with open(path, encoding='utf-8') as f:
        saved = json.load(f)
    out = [{'day': c['day'], 'tool': 'Cursor', 'project': 'unknown', 'reason': 'unknown', 'model': c['model'],
            'input': c['input'], 'output': c['output'], 'cache_read': c['cache_read'], 'cache_write': c['cache_write'],
            'total': c['total'], 'usd': None, 'stated_usd': c['stated_usd']} for c in saved.get('cells', [])]
    return out, saved.get('stats')
