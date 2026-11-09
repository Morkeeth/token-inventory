"""tokens: where did my coding-agent tokens go? Everything runs on this machine."""
import argparse
import json
import os
import sys
from datetime import date, timedelta

from . import __version__, config, cursor, scan

SAMPLE = {
    'code_roots': ['~/code', '~/work'],
    'rules': [{'match': '~/work/client-a/*', 'project': 'Client A'},
              {'match': '~/notes', 'project': 'Writing'}],
    'prices': {'claude': {}, 'codex': {}},
}


def _money(x):
    return '$%s' % format(round(x, 2), ',.2f')


def _tokens(n):
    for unit, size in (('B', 1e9), ('M', 1e6), ('k', 1e3)):
        if n >= size:
            return '%.1f%s' % (n / size, unit)
    return str(int(n))


def summarise(inv, days):
    first = (date.today() - timedelta(days=days - 1)).isoformat() if days else '0000'
    F = {f: i for i, f in enumerate(inv['fields'])}
    tools, projects, total = {}, {}, {'tokens': 0, 'usd': 0.0, 'unpriced': 0}
    for c in inv['cells']:
        if c[F['day']] < first:
            continue
        for bucket in (tools.setdefault(c[F['tool']], {'tokens': 0, 'usd': 0.0, 'unpriced': 0, 'stated': 0.0}),
                       projects.setdefault(c[F['project']], {'tokens': 0, 'usd': 0.0, 'unpriced': 0}), total):
            bucket['tokens'] += c[F['total']]
            bucket['usd'] += c[F['usd']]
            bucket['unpriced'] += c[F['unpriced_tokens']]
        tools[c[F['tool']]]['stated'] += c[F['stated_usd']]
    return tools, projects, total


def report(inv, days, out=sys.stdout):
    tools, projects, total = summarise(inv, days)
    span = 'last %d days' % days if days else 'all time'
    w = out.write
    w('Where did the tokens go, %s\n' % span)
    w('Estimate at public list price, not what you paid.\n\n')
    if not total['tokens']:
        w('No usage records in this window.\n')
        for name, s in inv['sources'].items():
            w('  %-12s looked in %s\n' % (name, ', '.join(s['looked_in'])))
        return
    w('  %-26s %10s %12s\n' % ('Tool', 'Tokens', 'Estimate'))
    for name, t in sorted(tools.items(), key=lambda kv: -kv[1]['tokens']):
        note = '  (export states %s)' % _money(t['stated']) if name == 'Cursor' else (
            '  (+%s tokens with no price)' % _tokens(t['unpriced']) if t['unpriced'] else '')
        est = 'no price' if name == 'Cursor' else _money(t['usd'])
        w('  %-26s %10s %12s%s\n' % (name, _tokens(t['tokens']), est, note))
    w('  %-26s %10s %12s\n\n' % ('All tools', _tokens(total['tokens']), _money(total['usd'])))
    w('  %-26s %12s %7s\n' % ('Project', 'Estimate', 'Share'))
    ranked = sorted(projects.items(), key=lambda kv: (kv[0] == config.UNKNOWN, -kv[1]['usd'], -kv[1]['tokens']))
    for name, p in ranked[:15]:
        share = 100 * p['usd'] / total['usd'] if total['usd'] else 0
        w('  %-26s %12s %6.0f%%\n' % (name[:26], _money(p['usd']), share))
    if len(ranked) > 15:
        w('  ... %d more in the dashboard\n' % (len(ranked) - 15))
    unk = projects.get(config.UNKNOWN)
    if unk and total['usd']:
        w('\nunknown = no evidence of a project. Add a rule to place it (tokens config).\n')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='tokens', description='Count your own Claude Code, Codex and Cursor usage. Nothing leaves this machine.')
    ap.add_argument('--version', action='version', version='%(prog)s ' + __version__)
    sub = ap.add_subparsers(dest='cmd')
    s = sub.add_parser('scan', help='read your local records and write the inventory')
    s.add_argument('--days', type=int, help='only read the last N days (default: all time)')
    r = sub.add_parser('report', help='print a summary in the terminal')
    r.add_argument('--days', type=int, default=7, help='window in days, 0 for all time (default 7)')
    r.add_argument('--json', action='store_true', help='print the raw inventory as JSON')
    v = sub.add_parser('serve', help='open the dashboard on http://127.0.0.1')
    v.add_argument('--port', type=int, default=int(os.environ.get('TOKENS_PORT', 7788)))
    v.add_argument('--open', action='store_true', help='open it in your browser')
    i = sub.add_parser('import-cursor', help='import a Cursor usage export (.csv)')
    i.add_argument('csv')
    sub.add_parser('config', help='show where the config lives and an example')
    sub.add_parser('where', help='show every folder this tool reads and writes')
    a = ap.parse_args(argv)

    if a.cmd == 'scan':
        inv, path = scan.run(a.days)
        n = sum(c[inv['fields'].index('messages')] for c in inv['cells'])
        print('Scanned in %ss. %d counted records. Saved to %s' % (inv['seconds'], n, config.tilde(path)))
        print('Next: tokens report, or tokens serve')
    elif a.cmd == 'report':
        inv = scan.load() or scan.run()[0]
        if a.json:
            json.dump(inv, sys.stdout, indent=1)
            print()
        else:
            report(inv, a.days or None)
    elif a.cmd == 'serve':
        from .server import serve
        serve(a.port, a.open)
    elif a.cmd == 'import-cursor':
        try:
            out = cursor.import_file(a.csv, config.data_dir())
        except (ValueError, OSError) as e:
            sys.exit('tokens: %s' % e)
        print('Imported %d Cursor rows (%d copies dropped). Run tokens scan to include them.' % (out['stats']['rows'], out['stats']['copies']))
    elif a.cmd == 'config':
        p = config.config_path()
        print('Config file: %s (%s)' % (config.tilde(p), 'found' if os.path.isfile(p) else 'not created; none needed'))
        print('Example, all keys optional:\n')
        print(json.dumps(SAMPLE, indent=2))
    elif a.cmd == 'where':
        from . import claude, codex
        print('Reads   Claude Code  %s' % ', '.join(config.tilde(p) for p in claude.roots()))
        print('Reads   Codex        %s' % ', '.join(config.tilde(p) for p in codex.roots()))
        print('Reads   Config       %s' % config.tilde(config.config_path()))
        print('Writes  Inventory    %s' % config.tilde(config.data_dir()))
        print('Sends   nothing. No network calls, no telemetry.')
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
