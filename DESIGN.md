# Design

## Goal

Add intelligent per-aircraft history-date navigation to stock tar1090 without
switching to an aggregator-specific tar1090 fork.

For a single selected aircraft:

- History opens on the newest UTC date with known trace activity.
- The date picker enables/highlights dates for which that aircraft has trace history.
- Known empty dates are disabled.
- Previous/Next jump directly between observed dates rather than ±1 calendar day.
- Current live trace dates are merged in so today works before archive rollover.
- Missing/unreadable active-date data falls back to normal stock behavior.
- Deep links remain valid.
- Multi-select and replay retain upstream semantics.

## Static index

Historical availability is derived from filenames only:

```text
/var/globe_history/YYYY/MM/DD/traces/XX/trace_full_HEX.json
```

and indexed as:

```text
/var/globe_history/active-dates/XX/hexhex.json
```

Logical payload:

```json
{"dates":["2026-10-07","2026-10-05","2026-09-29"]}
```

The files themselves contain gzip-compressed JSON bytes. Stock tar1090's
lighttpd configuration sends `Content-Encoding: gzip` for `/globe_history/`.
For nginx, the web server must likewise mark the `active-dates` path as gzip;
`verify-install.sh` checks this through HTTP.

## Current-day edge

The archive index can lag the live trace. Browser logic also requests:

```text
data/traces/XX/trace_full_HEX.json
```

and unions any represented UTC dates with the archive dates.

## Upgrade model

The patcher is intentionally fail-closed and accepts only exact upstream
revisions listed in `SUPPORTED_BASES` inside `apply-active-dates.py`. When
upstream advances, compare the target files and add the new exact commit only
after all anchors are verified.

The permanent model is:

```text
stock wiedehopf/tar1090
        |
        v
small Active Dates patch
        |
        v
local tar1090 install
```

Do not maintain this as hand edits to `/usr/local/share/tar1090/html`; the
upstream installer can replace that tree.
