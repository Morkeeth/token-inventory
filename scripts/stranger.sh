#!/bin/sh
# Cold start: a fresh HOME, synthetic records, an install from this checkout, then every command.
# Fails loudly on the first broken step.
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
export HOME="$WORK/home"
mkdir -p "$HOME"
unset XDG_DATA_HOME XDG_CONFIG_HOME TOKENS_DATA TOKENS_CONFIG CLAUDE_CONFIG_DIR CODEX_HOME TOKENS_CLAUDE_DIRS TOKENS_CODEX_DIRS 2>/dev/null || true
PORT=${PORT:-7791}
step() { printf '\n== %s\n' "$1"; }

step "empty machine: no records yet"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q "$REPO"
T="$WORK/venv/bin/tokens"
"$T" --version
"$T" report | tee "$WORK/empty.txt"
grep -q "No usage records" "$WORK/empty.txt"

step "synthetic month of Claude Code, Codex and Cursor records"
CSV=$(python3 -I "$REPO/tests/synth.py" "$HOME")
"$T" where
"$T" import-cursor "$CSV"
"$T" scan
"$T" report --days 30 | tee "$WORK/report.txt"
grep -q "Claude Code" "$WORK/report.txt"
grep -q "Codex" "$WORK/report.txt"
grep -q "unknown" "$WORK/report.txt"

step "optional config: a rule places the home-folder Codex work"
mkdir -p "$HOME/.config/where-did-the-tokens-go"
printf '{"rules":[{"match":"%s","project":"home experiments"}]}\n' "$HOME" > "$HOME/.config/where-did-the-tokens-go/config.json"
"$T" scan
"$T" report --days 30 | grep -q "home experiments"
rm "$HOME/.config/where-did-the-tokens-go/config.json"
"$T" scan

step "dashboard on 127.0.0.1"
"$T" serve --port "$PORT" > "$WORK/serve.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for i in 1 2 3 4 5 6 7 8 9 10; do curl -sf "http://127.0.0.1:$PORT/" >/dev/null && break; sleep 0.5; done
for p in / /methodology.html /METHODOLOGY.md /app.js /style.css /md.js /api/inventory; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT$p")
  echo "$code $p"
  [ "$code" = 200 ]
done
code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: evil.example' "http://127.0.0.1:$PORT/api/inventory")
echo "$code /api/inventory with a foreign Host header"
[ "$code" = 403 ]
if curl -s "http://127.0.0.1:$PORT/api/inventory" | grep -q "$WORK"; then echo "home path leaked into the API"; exit 1; fi
if lsof -nP -iTCP -sTCP:LISTEN -a -p "$PID" 2>/dev/null | grep -v 127.0.0.1 | grep -q LISTEN; then echo "listening beyond 127.0.0.1"; exit 1; fi

step "PASS"
echo "Stranger flow passed in a fresh HOME: $HOME"
echo "To view: HOME=$HOME $T serve --port $PORT"
