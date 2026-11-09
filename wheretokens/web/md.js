'use strict';
// A small Markdown renderer for METHODOLOGY.md, so the page and the file can never disagree.
// Covers what that file uses: headings, paragraphs, lists, tables, code blocks, inline code, bold, links.
function markdown(src) {
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => /^(https?:|#|[\w.-]+\.(md|html)$)/.test(u) ? '<a href="' + u + '">' + t + '</a>' : t);
  const lines = src.replace(/\r/g, '').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {
      const buf = [];
      for (i++; i < lines.length && !/^```/.test(lines[i]); i++) buf.push(esc(lines[i]));
      out.push('<pre><code>' + buf.join('\n') + '</code></pre>'); i++; continue;
    }
    const h = l.match(/^(#{1,3})\s+(.*)/);
    if (h) { out.push('<h' + h[1].length + '>' + inline(h[2]) + '</h' + h[1].length + '>'); i++; continue; }
    if (/^\|/.test(l)) {
      const rows = [];
      for (; i < lines.length && /^\|/.test(lines[i]); i++) rows.push(lines[i].replace(/^\||\|$/g, '').split('|').map((c) => c.trim()));
      const body = rows.filter((r, k) => k !== 1 || !r.every((c) => /^:?-+:?$/.test(c)));
      out.push('<div class="scroll"><table><thead><tr>' + body[0].map((c) => '<th>' + inline(c) + '</th>').join('') + '</tr></thead><tbody>' +
        body.slice(1).map((r) => '<tr>' + r.map((c) => '<td>' + inline(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>');
      continue;
    }
    const li = l.match(/^(\s*)([-*]|\d+\.)\s+(.*)/);
    if (li) {
      const tag = /\d/.test(li[2]) ? 'ol' : 'ul';
      const items = [];
      for (; i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i]); i++) items.push('<li>' + inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, '')) + '</li>');
      out.push('<' + tag + '>' + items.join('') + '</' + tag + '>'); continue;
    }
    if (!l.trim()) { i++; continue; }
    const para = [];
    for (; i < lines.length && lines[i].trim() && !/^(#|\||```|\s*([-*]|\d+\.)\s)/.test(lines[i]); i++) para.push(lines[i]);
    out.push('<p>' + inline(para.join(' ')) + '</p>');
  }
  return out.join('\n');
}

if (document.getElementById('doc')) fetch(document.getElementById('doc').dataset.src || 'METHODOLOGY.md').then((r) => r.text()).then((t) => { document.getElementById('doc').innerHTML = markdown(t); });
