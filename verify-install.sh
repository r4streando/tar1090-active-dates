#!/bin/bash
# Verify the Active Dates frontend, static index, HTTP encoding, and timer.
set -euo pipefail

INSTANCE=${1:-tar1090}
BASE="http://127.0.0.1/${INSTANCE}"
INDEX_ROOT=/var/globe_history/active-dates

echo "== tar1090 version =="
curl -fsS "$BASE/version.json"; echo

echo
echo "== Active Dates frontend include =="
INDEX_HTML=$(curl -fsS "$BASE/")
ACTIVITY_JS=$(grep -oE 'activityHistory_[0-9a-f]+\.js|activityHistory\.js' <<<"$INDEX_HTML" | head -n1 || true)
if [[ -z "$ACTIVITY_JS" ]]; then
    echo "ERROR: activityHistory.js is not referenced by installed index.html" >&2
    exit 1
fi
echo "$ACTIVITY_JS"
curl -fsS "$BASE/$ACTIVITY_JS" >/dev/null
echo "frontend module: OK"

echo
echo "== Active-date index =="
if [[ ! -d "$INDEX_ROOT" ]]; then
    echo "ERROR: $INDEX_ROOT is missing" >&2
    exit 1
fi
COUNT=$(find "$INDEX_ROOT" -mindepth 2 -maxdepth 2 -type f -name '*.json' | wc -l)
echo "per-aircraft index files: $COUNT"
SAMPLE=$(find "$INDEX_ROOT" -mindepth 2 -maxdepth 2 -type f -name '*.json' | head -n1 || true)
if [[ -z "$SAMPLE" ]]; then
    echo "ERROR: no per-aircraft index files found" >&2
    exit 1
fi

echo "sample: $SAMPLE"
gzip -t "$SAMPLE"
gzip -cd "$SAMPLE" | python3 -m json.tool | head -40

ICAO=$(basename "$SAMPLE" .json)
SHARD=$(basename "$(dirname "$SAMPLE")")
echo
echo "== HTTP active-date index =="
echo "$BASE/globe_history/active-dates/$SHARD/$ICAO.json"
curl -fsS --compressed "$BASE/globe_history/active-dates/$SHARD/$ICAO.json" \
    | python3 -m json.tool | head -40
echo "HTTP gzip handling: OK"

echo
echo "== Timer =="
systemctl --no-pager --full status tar1090-active-dates.timer || true
systemctl --no-pager --full status tar1090-active-dates.service || true

echo
echo "Verification complete."
