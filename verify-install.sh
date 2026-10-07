#!/bin/bash
# Verify the Active Dates frontend, static index, HTTP encoding, and timer.
set -euo pipefail

INSTANCE=${1:-tar1090}
BASE="http://127.0.0.1/${INSTANCE}"
INDEX_ROOT=/var/globe_history/active-dates
ARCHIVE_ROOT=/var/globe_history

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
echo "== Archived globe-history traces =="
ARCHIVE_COUNT=$(find "$ARCHIVE_ROOT" -type f -path '*/traces/*/trace_full_*.json' 2>/dev/null | wc -l)
echo "archived trace_full files: $ARCHIVE_COUNT"

echo
echo "== Active-date index =="
if [[ ! -d "$INDEX_ROOT" ]]; then
    echo "ERROR: $INDEX_ROOT is missing" >&2
    exit 1
fi
COUNT=$(find "$INDEX_ROOT" -mindepth 2 -maxdepth 2 -type f -name '*.json' | wc -l)
echo "per-aircraft index files: $COUNT"

PENDING_FIRST_ARCHIVE=0
if [[ "$COUNT" -eq 0 ]]; then
    if [[ "$ARCHIVE_COUNT" -eq 0 ]]; then
        PENDING_FIRST_ARCHIVE=1
        echo "PENDING: globe_history has no permanent per-aircraft traces yet."
        echo "This is normal on a fresh receiver before its first UTC daily archive rollover."
        echo "The timer will index those files after readsb writes them."
    else
        echo "ERROR: globe_history contains archived traces but no Active Dates indexes were generated" >&2
        exit 1
    fi
else
    SAMPLE=$(find "$INDEX_ROOT" -mindepth 2 -maxdepth 2 -type f -name '*.json' | head -n1 || true)
    if [[ -z "$SAMPLE" ]]; then
        echo "ERROR: index count was nonzero but no sample index could be selected" >&2
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
fi

echo
echo "== Timer =="
systemctl --no-pager --full status tar1090-active-dates.timer || true
systemctl --no-pager --full status tar1090-active-dates.service || true

echo
if [[ "$PENDING_FIRST_ARCHIVE" -eq 1 ]]; then
    echo "Verification complete: frontend and timer are installed; archive index is pending the first UTC rollover."
else
    echo "Verification complete."
fi
