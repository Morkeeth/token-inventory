'use strict';
// Reads /api/inventory from this machine's own server. No other request is made.
let INV = null, DAYS = 7;
const $ = (id) => document.getElementById(id);
const money = (x) => '$' + (x >= 1000 ? Math.round(x).toLocaleString('en-US') : x.toFixed(2));
const toks = (n) => n >= 1e9 ? (n / 1e9).toFixed(1) + 'B' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(n);
const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '0%';
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const REASON = { rule: 'your rule', folder: 'working folder', files: 'files touched', unknown: 'no evidence' };

function localDay(d) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}

function view() {
  const F = Object.fromEntries(INV.fields.map((f, i) => [f, i]));
  const first = DAYS ? localDay(new Date(Date.now() - (DAYS - 1) * 864e5)) : '0000';
  const cells = INV.cells.filter((c) => c[F.day] >= first);
  const sum = (rows, key) => rows.reduce((a, c) => a + c[F[key]], 0);
  const group = (key) => {
    const m = new Map();
    for (const c of cells) {
      const k = c[F[key]];
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(c);
    }
    return m;
  };
  return { F, cells, sum, group, first };
}

function render() {
  const { F, cells, sum, group, first } = view();
  const allTokens = INV.cells.reduce((a, c) => a + c[F.total], 0);
  $('empty').hidden = allTokens > 0;
  $('view').hidden = allTokens === 0;
  if (!allTokens) {
    $('looked').innerHTML = Object.entries(INV.sources).map(([k, s]) => '<b>' + esc(k) + '</b>: ' + s.looked_in.map((p) => '<code>' + esc(p) + '</code>').join(', ')).join('<br>');
    return;
  }
  const usd = sum(cells, 'usd'), tokens = sum(cells, 'total');
  const projects = [...group('project')].map(([name, rows]) => ({
    name, usd: sum(rows, 'usd'), tokens: sum(rows, 'total'),
    reasons: [...new Set(rows.map((r) => r[F.reason]))],
  })).sort((a, b) => (a.name === 'unknown') - (b.name === 'unknown') || b.usd - a.usd || b.tokens - a.tokens);
  const unknown = projects.find((p) => p.name === 'unknown');
  $('usd').textContent = money(usd);
  $('span').textContent = DAYS ? 'last ' + DAYS + ' days' : 'all time';
  $('tok').textContent = toks(tokens);
  $('known').textContent = pct(usd - (unknown ? unknown.usd : 0), usd);

  // The slab: estimate by project, unknown last and hatched. When nothing is priced, tokens decide the width.
  const w = (p) => (usd ? p.usd : p.tokens);
  const named = projects.filter((p) => p.name !== 'unknown');
  const shades = ['--b1', '--b2', '--b3', '--b4'];
  $('slab').innerHTML = named.concat(unknown ? [unknown] : []).filter((p) => w(p) > 0).map((p, i) =>
    '<span title="' + esc(p.name) + ' · ' + money(p.usd) + '" class="' + (p.name === 'unknown' ? 'unk' : '') + '" style="flex-grow:' + w(p) +
    (p.name === 'unknown' ? '' : ';background:var(' + shades[Math.min(i, 3)] + ')') + '">' +
    (w(p) / (usd || tokens) >= 0.09 ? '<b>' + esc(p.name) + '</b>' : '') + '</span>').join('')
    .replace(/class="" style="([^"]*--b[34][^"]*)"/g, 'class="lt" style="$1"');

  const max = Math.max(...projects.map(w), 1e-9);
  $('projects').tBodies[0].innerHTML = projects.map((p) =>
    '<tr class="' + (p.name === 'unknown' ? 'unk' : '') + '"><td>' + esc(p.name) +
    '<span class="why">' + (p.name === 'unknown' ? 'no evidence of a project, see How it is counted' : 'by ' + p.reasons.map((r) => REASON[r] || r).join(', ')) + '</span></td>' +
    '<td class="bar"><div class="meter" style="width:' + (100 * w(p) / max).toFixed(1) + '%"></div></td>' +
    '<td class="n">' + money(p.usd) + '</td><td class="n hide-s">' + toks(p.tokens) + '</td><td class="n">' + pct(w(p), usd || tokens) + '</td></tr>').join('');

  $('tools').tBodies[0].innerHTML = [...group('tool')].map(([name, rows]) => {
    const t = sum(rows, 'total');
    const note = name === 'Cursor' ? '<span class="tag">export states ' + money(sum(rows, 'stated_usd')) + '</span>' : '';
    return '<tr><td>' + esc(name) + note + '</td><td class="n">' + toks(t) + '</td><td class="n">' + (name === 'Cursor' ? 'no list price' : money(sum(rows, 'usd'))) +
      '</td><td class="n hide-s">' + toks(sum(rows, 'unpriced_tokens')) + '</td><td class="n hide-s">' + pct(sum(rows, 'cache_read'), t) + '</td></tr>';
  }).join('');

  $('models').tBodies[0].innerHTML = [...group('model')].map(([name, rows]) => ({ name, t: sum(rows, 'total'), u: sum(rows, 'usd'), unpriced: sum(rows, 'unpriced_tokens') }))
    .sort((a, b) => b.u - a.u || b.t - a.t).slice(0, 12)
    .map((m) => '<tr><td>' + esc(m.name) + (m.unpriced && !m.u ? '<span class="tag">no price</span>' : '') + '</td><td class="n">' + toks(m.t) + '</td><td class="n">' + money(m.u) + '</td></tr>').join('');

  // Days: every day of the window, zero days included, so a quiet day reads as quiet.
  const byDay = new Map([...group('day')].map(([d, rows]) => [d, usd ? sum(rows, 'usd') : sum(rows, 'total')]));
  const daysWithData = [...byDay.keys()].sort();
  const start = DAYS ? first : daysWithData[0];
  const list = [];
  for (let d = new Date(start + 'T12:00:00'); localDay(d) <= localDay(new Date()); d = new Date(d.getTime() + 864e5)) list.push(localDay(d));
  const top = Math.max(...list.map((d) => byDay.get(d) || 0), 1e-9);
  $('days').innerHTML = list.map((d) => {
    const v = byDay.get(d) || 0;
    return '<i class="' + (v ? '' : 'zero') + '" title="' + d + ' · ' + (usd ? money(v) : toks(v)) + '" style="height:' + (v ? Math.max(2, 100 * v / top) : 1) + '%"></i>';
  }).join('');
  $('d0').textContent = list[0] || '';
  $('d1').textContent = list[list.length - 1] || '';
}

function meta() {
  const s = INV.sources;
  const parts = Object.entries(s).map(([k, v]) => k + ': ' + (k === 'Cursor' ? (v.imported ? v.rows + ' rows imported' : 'no export imported') : v.files + ' files'));
  $('meta').textContent = 'Scanned ' + INV.scanned_at.replace('T', ' ').slice(0, 16) + ' in ' + INV.seconds + 's. ' + parts.join(' · ') + '. Prices dated ' + INV.prices.claude.date + '.';
  $('folder').textContent = INV.data_folder;
}

async function load() {
  const r = await fetch('/api/inventory', { cache: 'no-store' });
  INV = await r.json();
  meta();
  render();
}

document.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
  DAYS = Number(b.dataset.days);
  document.querySelectorAll('.seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  render();
}));

$('rescan').addEventListener('click', async () => {
  const b = $('rescan');
  b.disabled = true; b.textContent = 'Reading…';
  try { await fetch('/api/scan', { method: 'POST' }); await load(); } finally { b.disabled = false; b.textContent = 'Rescan'; }
});

load().catch(() => { $('meta').textContent = 'Could not read the inventory. Is tokens serve still running?'; });
