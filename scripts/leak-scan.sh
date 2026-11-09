#!/bin/sh
# Refuse to ship personal paths, names, addresses or keys. LICENSE carries the copyright holder and is exempt.
# Extra terms can be passed in LEAK_TERMS (one regex alternative per word, separated by |).
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"
TERMS='/Users/[a-z]|/home/[a-z]+/|morkeeth|omorke|@gmail|@proton|sk-ant-|sk-proj-|ghp_|github_pat_|AKIA[0-9A-Z]{12}|xox[bp]-|BEGIN [A-Z ]*PRIVATE KEY'
[ -n "${LEAK_TERMS:-}" ] && TERMS="$TERMS|$LEAK_TERMS"
FILES=$(git ls-files 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
# The public repository address is meant to be public; it is the one allowed mention.
HITS=$(printf '%s\n' $FILES | grep -v -e '^LICENSE$' -e '^scripts/leak-scan.sh$' | xargs grep -n -I -i -E "$TERMS" 2>/dev/null \
  | sed -E 's#github\.com/Morkeeth/token-inventory##g' | grep -i -E "$TERMS" || true)
if [ -n "$HITS" ]; then
  echo "LEAK SCAN FAILED:"
  echo "$HITS"
  exit 1
fi
echo "Leak scan clean: $(printf '%s\n' $FILES | wc -l | tr -d ' ') files checked."
