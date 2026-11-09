import io
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import synth  # noqa: E402
from wheretokens import claude, cli, codex, config, cursor, prices, scan  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)


class Home(unittest.TestCase):
    """Each test runs in an empty HOME, so nothing of the machine running the test is read."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.env = {k: os.environ.get(k) for k in ('HOME', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'TOKENS_DATA', 'TOKENS_CONFIG',
                                                  'CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'TOKENS_CLAUDE_DIRS', 'TOKENS_CODEX_DIRS')}
        for k in self.env:
            os.environ.pop(k, None)
        os.environ['HOME'] = self.home

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def write(self, rel, records):
        synth._w(os.path.join(self.home, rel), records)

    def att(self, cfg=None):
        return config.Attributor(cfg)


class ClaudeCounting(Home):
    def test_one_count_per_message_at_largest_record(self):
        cwd = os.path.join(self.home, 'code', 'shop')
        m = synth.claude_msg(NOW, 'm1', cwd, inp=100, out=900, read=0, w5m=0)
        placeholder = json.loads(json.dumps(m))
        placeholder['message']['usage']['output_tokens'] = 2
        self.write('.claude/projects/p/a.jsonl', [placeholder, m, m])
        rows, stats = claude.read(self.att())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['output'], 900)
        self.assertEqual(rows[0]['total'], 1000)
        self.assertEqual(stats['records_repeated'], 2)
        self.assertEqual(stats['placeholders_replaced'], 1)

    def test_same_message_in_two_files_counts_once(self):
        m = synth.claude_msg(NOW, 'm1', self.home)
        self.write('.claude/projects/p/a.jsonl', [m])
        self.write('.claude/projects/p/sub/agent.jsonl', [m])
        rows, _ = claude.read(self.att())
        self.assertEqual(len(rows), 1)

    def test_unknown_model_is_unpriced_never_zero(self):
        self.write('.claude/projects/p/a.jsonl', [synth.claude_msg(NOW, 'm1', self.home, model='claude-future-9')])
        rows, _ = claude.read(self.att())
        self.assertIsNone(rows[0]['usd'])
        self.assertGreater(rows[0]['total'], 0)

    def test_prompt_text_never_reaches_the_inventory(self):
        cwd = os.path.join(self.home, 'code', 'shop')
        self.write('.claude/projects/p/a.jsonl', [synth.claude_msg(NOW, 'm1', cwd, text='TOP-SECRET-PROMPT',
                                                                   tools=[('Read', os.path.join(cwd, 'secret_file.py'))])])
        inv, path = scan.run()
        raw = Path(path).read_text()
        self.assertNotIn('TOP-SECRET-PROMPT', raw)
        self.assertNotIn('secret_file', raw)
        self.assertNotIn(self.home, raw)


class Prices(unittest.TestCase):
    def test_date_suffix_is_stripped(self):
        self.assertEqual(prices.normalise_model('claude-haiku-4-5-20251001'), 'claude-haiku-4-5')

    def test_claude_price_parts(self):
        usd, tok = prices.price_claude('claude-sonnet-5-5', {'input_tokens': 1_000_000, 'output_tokens': 1_000_000,
                                                             'cache_read_input_tokens': 1_000_000, 'cache_creation_input_tokens': 1_000_000})
        # input 2 + output 10 + read 2*0.05 + write 2*1.25
        self.assertAlmostEqual(usd, 2 + 10 + 0.1 + 2.5)
        self.assertEqual(tok['total'], 4_000_000)

    def test_fast_and_tier(self):
        fast, _ = prices.price_claude('claude-opus-5-5', {'input_tokens': 1_000_000, 'speed': 'fast'})
        self.assertAlmostEqual(fast, 8.0)
        small, _ = prices.price_claude('claude-haiku-5-5', {'input_tokens': 100_000})
        big, _ = prices.price_claude('claude-haiku-5-5', {'input_tokens': 100_001})
        self.assertAlmostEqual(small, 0.01)
        self.assertAlmostEqual(big, 100_001 * 0.5 / 1e6)

    def test_codex_long_context_is_per_request(self):
        u = {'input_tokens': 300_000, 'cached_input_tokens': 0, 'cache_write_input_tokens': 0, 'output_tokens': 1000}
        self.assertAlmostEqual(prices.price_codex('gpt-6.1-sol', u), (300_000 * 2 * 2 + 1000 * 10 * 1.5) / 1e6)

    def test_override_adds_a_rate(self):
        prices.apply_overrides({'prices': {'claude': {'claude-test-1': [1, 2]}}})
        usd, _ = prices.price_claude('claude-test-1', {'input_tokens': 1_000_000})
        self.assertAlmostEqual(usd, 1.0)
        del prices.CLAUDE['claude-test-1']


class CodexCounting(Home):
    def test_differencing_resets_and_copies(self):
        start = NOW - timedelta(hours=1)
        synth.codex_file(os.path.join(self.home, '.codex/sessions/a.jsonl'), os.path.join(self.home, 'code', 'pipe'),
                         'gpt-6.1-sol', start, [(1000, 400, 100), (2000, 0, 200), (500, 0, 50)], reset_at=2)
        # A forked session copies the same history: it must not count twice.
        Path(self.home, '.codex/archived_sessions').mkdir(parents=True)
        Path(self.home, '.codex/archived_sessions/b.jsonl').write_text(Path(self.home, '.codex/sessions/a.jsonl').read_text())
        rows, stats = codex.read(self.att())
        self.assertEqual(sum(r['total'] for r in rows), 1100 + 2200)  # the row after the reset is excluded
        self.assertEqual(stats['counter_resets'], 2)  # one per file; the copy's rows still count once
        self.assertTrue(all(r['project'] == 'pipe' and r['reason'] == 'folder' for r in rows))
        self.assertEqual(rows[0]['cache_read'], 400)
        self.assertEqual(rows[0]['input'], 600)

    def test_unreconciled_increment_has_no_price(self):
        recs = [{'type': 'turn_context', 'timestamp': NOW.isoformat(), 'payload': {'model': 'gpt-6.1-sol', 'cwd': self.home}},
                {'type': 'event_msg', 'timestamp': NOW.isoformat(), 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': {'input_tokens': 1000, 'output_tokens': 10, 'total_tokens': 1010},
                    'last_token_usage': {'input_tokens': 5, 'output_tokens': 1, 'total_tokens': 6}}}}]
        self.write('.codex/sessions/x.jsonl', recs)
        rows, stats = codex.read(self.att())
        self.assertIsNone(rows[0]['usd'])
        self.assertEqual(stats['unreconciled'], 1)
        self.assertEqual(rows[0]['project'], 'unknown')

    def test_window_applies_after_differencing(self):
        start = NOW - timedelta(days=10)
        synth.codex_file(os.path.join(self.home, '.codex/sessions/a.jsonl'), self.home, 'gpt-6.1-sol', start, [(1000, 0, 100)])
        recs = [json.loads(l) for l in Path(self.home, '.codex/sessions/a.jsonl').read_text().splitlines()]
        later = {'type': 'event_msg', 'timestamp': NOW.isoformat(), 'payload': {'type': 'token_count', 'info': {
            'total_token_usage': {'input_tokens': 1500, 'output_tokens': 150, 'reasoning_output_tokens': 33, 'total_tokens': 1650},
            'last_token_usage': {'input_tokens': 500, 'output_tokens': 50, 'total_tokens': 550}}}}
        self.write('.codex/sessions/a.jsonl', recs + [later])
        rows, _ = codex.read(self.att(), since=NOW - timedelta(days=1))
        self.assertEqual([r['total'] for r in rows], [550])


class Attribution(Home):
    def test_order(self):
        a = self.att({'rules': [{'match': os.path.join(self.home, 'work', 'client-a', '*'), 'project': 'Client A'}]})
        code = os.path.join(self.home, 'code')
        self.assertEqual(a.attribute(os.path.join(self.home, 'work', 'client-a', 'web')), ('Client A', 'rule'))
        self.assertEqual(a.attribute(os.path.join(code, 'shop', 'api', 'src')), ('shop', 'folder'))
        self.assertEqual(a.attribute(os.path.join(code, '.worktrees', 'shop-fix')), ('shop-fix', 'folder'))
        self.assertEqual(a.attribute(self.home, [os.path.join(code, 'blog', 'a.md')]), ('blog', 'files'))
        self.assertEqual(a.attribute(self.home, [os.path.join(code, 'blog', 'a.md'), os.path.join(code, 'shop', 'b')]), ('unknown', 'unknown'))
        self.assertEqual(a.attribute(self.home), ('unknown', 'unknown'))
        self.assertEqual(a.attribute(code), ('unknown', 'unknown'))


class SymlinkedHome(Home):
    def test_home_reached_through_a_symlink(self):
        # macOS: /var is /private/var. HOME as written and as resolved must both count as home.
        link = os.path.join(self.home, 'link')
        real = os.path.join(self.home, 'real')
        os.makedirs(os.path.join(real, 'code', 'blog'))
        os.symlink(real, link)
        os.environ['HOME'] = link
        a = self.att()
        self.assertEqual(a.attribute(link), ('unknown', 'unknown'))
        self.assertEqual(a.attribute(real), ('unknown', 'unknown'))
        self.assertEqual(a.attribute(os.path.join(real, 'code', 'blog')), ('blog', 'folder'))
        self.assertEqual(config.tilde(os.path.join(real, 'x')), '~/x')
        self.assertEqual(config.tilde(os.path.join(link, 'x')), '~/x')


class Cursor(Home):
    def test_import_keeps_stated_cost_apart(self):
        csv_path = synth.month(self.home, days=6)
        out = cursor.import_file(csv_path, config.data_dir())
        self.assertEqual(out['stats']['rows'], 2)
        rows, _ = cursor.rows(config.data_dir())
        self.assertTrue(all(r['usd'] is None and r['project'] == 'unknown' for r in rows))

    def test_rejects_other_csv(self):
        p = Path(self.home, 'x.csv')
        p.write_text('a,b\n1,2\n')
        with self.assertRaises(ValueError):
            cursor.import_file(str(p), config.data_dir())


class EndToEnd(Home):
    def test_month_scan_report_and_server(self):
        csv_path = synth.month(self.home)
        cli.main(['import-cursor', csv_path])
        inv, path = scan.run()
        self.assertTrue(path.startswith(os.path.join(self.home, '.local', 'share')))
        F = {f: i for i, f in enumerate(inv['fields'])}
        projects = {c[F['project']] for c in inv['cells']}
        self.assertTrue({'shop-api', 'field-notes', 'data-pipeline', 'unknown'} <= projects)
        self.assertEqual({c[F['tool']] for c in inv['cells']}, {'Claude Code', 'Codex', 'Cursor'})
        buf = io.StringIO()
        cli.report(inv, 30, buf)
        self.assertIn('unknown', buf.getvalue())
        self.assertIn('not what you paid', buf.getvalue())

        from wheretokens.server import Handler, ThreadingHTTPServer
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % httpd.server_address[1]
        try:
            for page in ('/', '/methodology.html', '/METHODOLOGY.md', '/guide.html', '/GUIDE.md', '/app.js', '/style.css', '/md.js'):
                with urllib.request.urlopen(base + page) as r:
                    self.assertEqual(r.status, 200, page)
            with urllib.request.urlopen(base + '/api/inventory') as r:
                body = json.loads(r.read())
            self.assertNotIn(self.home, json.dumps(body))
            req = urllib.request.Request(base + '/api/inventory', headers={'Host': 'evil.example'})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 403)
            req = urllib.request.Request(base + '/api/scan', method='POST', headers={'Origin': 'http://evil.example'})
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_data_is_readable_by_this_account_only(self):
        _, path = scan.run()
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(os.path.dirname(path)).st_mode & 0o777, 0o700)

    def test_empty_home_is_explained(self):
        inv, _ = scan.run()
        self.assertEqual(inv['cells'], [])
        buf = io.StringIO()
        cli.report(inv, 7, buf)
        self.assertIn('No usage records', buf.getvalue())


class Static(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_web_makes_no_outside_request(self):
        for f in (self.ROOT / 'wheretokens' / 'web').iterdir():
            text = f.read_text()
            if f.suffix in ('.html', '.js', '.css'):
                self.assertIsNone(re.search(r'(src|href)=["\']https?://|fetch\(["\']https?://|@import|url\(["\']?https?://', text), f.name)

    def test_document_copies_agree(self):
        for name in ('METHODOLOGY.md', 'GUIDE.md'):
            self.assertEqual((self.ROOT / name).read_text(), (self.ROOT / 'wheretokens' / 'web' / name).read_text(), name)


if __name__ == '__main__':
    unittest.main()
