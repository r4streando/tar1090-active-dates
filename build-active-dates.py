#!/usr/bin/env python3
"""Build static per-aircraft active-date indexes for tar1090 globe_history.

The index is derived only from trace filenames under:
  ROOT/YYYY/MM/DD/traces/XX/trace_full_HEX.json

Output files are gzip-compressed JSON (despite the .json suffix) because
upstream tar1090's lighttpd config advertises Content-Encoding: gzip for the
entire /globe_history/ URL space.

First run performs a full reconciliation. Later runs are incremental based on
trace-file mtimes. Use --full after manually deleting/pruning old globe_history
files so stale dates are removed from the index.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import re
import sys
import time

TRACE_RE = re.compile(r"^trace_full_([0-9a-fA-F]{6})\.json$")
YEAR_RE = re.compile(r"^\d{4}$")
TWO_RE = re.compile(r"^\d{2}$")
INDEX_DIR = "active-dates"
MARKER_NAME = ".last-scan-ns"


def valid_date_parts(year: str, month: str, day: str) -> str | None:
    if not YEAR_RE.match(year) or not TWO_RE.match(month) or not TWO_RE.match(day):
        return None
    try:
        d = dt.date(int(year), int(month), int(day))
    except ValueError:
        return None
    return d.isoformat()


def iter_trace_files(root: Path, since_ns: int | None = None):
    """Yield (path, icao_lower, YYYY-MM-DD) for archive trace files."""
    try:
        years = list(os.scandir(root))
    except FileNotFoundError:
        raise SystemExit(f"globe_history root does not exist: {root}")

    for y in years:
        if not y.is_dir(follow_symlinks=False) or not YEAR_RE.match(y.name):
            continue
        try:
            months = os.scandir(y.path)
        except OSError:
            continue
        with months:
            for m in months:
                if not m.is_dir(follow_symlinks=False) or not TWO_RE.match(m.name):
                    continue
                try:
                    days = os.scandir(m.path)
                except OSError:
                    continue
                with days:
                    for d in days:
                        if not d.is_dir(follow_symlinks=False) or not TWO_RE.match(d.name):
                            continue
                        date_str = valid_date_parts(y.name, m.name, d.name)
                        if not date_str:
                            continue
                        traces = Path(d.path) / "traces"
                        if not traces.is_dir():
                            continue
                        try:
                            shards = os.scandir(traces)
                        except OSError:
                            continue
                        with shards:
                            for shard in shards:
                                if not shard.is_dir(follow_symlinks=False):
                                    continue
                                try:
                                    files = os.scandir(shard.path)
                                except OSError:
                                    continue
                                with files:
                                    for f in files:
                                        if not f.is_file(follow_symlinks=False):
                                            continue
                                        match = TRACE_RE.match(f.name)
                                        if not match:
                                            continue
                                        if since_ns is not None:
                                            try:
                                                if f.stat(follow_symlinks=False).st_mtime_ns < since_ns:
                                                    continue
                                            except FileNotFoundError:
                                                continue
                                        yield Path(f.path), match.group(1).lower(), date_str


def index_path(root: Path, icao: str) -> Path:
    return root / INDEX_DIR / icao[-2:] / f"{icao}.json"


def read_index(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise RuntimeError(f"cannot read existing index {path}: {exc}") from exc
    dates = data.get("dates", []) if isinstance(data, dict) else []
    if not isinstance(dates, list) or not all(isinstance(x, str) for x in dates):
        raise RuntimeError(f"invalid index schema in {path}")
    return dates


def encoded_payload(dates: set[str] | list[str]) -> bytes:
    payload = json.dumps(
        {"dates": sorted(set(dates), reverse=True)},
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    import io
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=6, mtime=0) as gz:
        gz.write(payload)
    return out.getvalue()


def write_index(path: Path, dates: set[str] | list[str], dry_run: bool = False) -> bool:
    """Atomically write only when logical dates differ. Returns True if changed."""
    normalized = sorted(set(dates), reverse=True)
    try:
        existing = read_index(path)
    except RuntimeError:
        existing = None
    if existing == normalized:
        return False
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_bytes(encoded_payload(normalized))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return True


def read_marker(marker: Path) -> int | None:
    try:
        return int(marker.read_text(encoding="ascii").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def write_marker(marker: Path, scan_started_ns: int, dry_run: bool = False) -> None:
    if dry_run:
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_name(f".{marker.name}.tmp.{os.getpid()}")
    tmp.write_text(str(scan_started_ns) + "\n", encoding="ascii")
    os.chmod(tmp, 0o644)
    os.replace(tmp, marker)


def existing_index_files(root: Path):
    base = root / INDEX_DIR
    if not base.is_dir():
        return []
    return [p for p in base.glob("??/*.json") if re.fullmatch(r"[0-9a-f]{6}\.json", p.name)]


def cleanup_empty_shards(root: Path, dry_run: bool = False) -> None:
    base = root / INDEX_DIR
    if not base.is_dir():
        return
    for d in base.iterdir():
        if not d.is_dir():
            continue
        try:
            next(d.iterdir())
        except StopIteration:
            if not dry_run:
                d.rmdir()


def full_rebuild(root: Path, dry_run: bool = False):
    by_icao: dict[str, set[str]] = {}
    files_seen = 0
    for _path, icao, date_str in iter_trace_files(root):
        files_seen += 1
        by_icao.setdefault(icao, set()).add(date_str)

    updated = 0
    for icao, dates in by_icao.items():
        updated += int(write_index(index_path(root, icao), dates, dry_run=dry_run))

    expected = {index_path(root, icao) for icao in by_icao}
    removed = 0
    for path in existing_index_files(root):
        if path not in expected:
            removed += 1
            if not dry_run:
                path.unlink()
    cleanup_empty_shards(root, dry_run=dry_run)
    return files_seen, len(by_icao), updated, removed


def incremental(root: Path, since_ns: int, dry_run: bool = False):
    changed: dict[str, set[str]] = {}
    files_seen = 0
    for _path, icao, date_str in iter_trace_files(root, since_ns=since_ns):
        files_seen += 1
        changed.setdefault(icao, set()).add(date_str)

    updated = 0
    for icao, new_dates in changed.items():
        path = index_path(root, icao)
        try:
            dates = set(read_index(path))
        except RuntimeError as exc:
            print(f"warning: {exc}; rebuilding this ICAO from archive", file=sys.stderr)
            dates = set()
            for _p, candidate, date_str in iter_trace_files(root):
                if candidate == icao:
                    dates.add(date_str)
        dates.update(new_dates)
        updated += int(write_index(path, dates, dry_run=dry_run))
    return files_seen, len(changed), updated, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/var/globe_history", help="globe_history root")
    parser.add_argument("--full", action="store_true", help="full reconcile; removes stale indexed dates/aircraft")
    parser.add_argument("--dry-run", action="store_true", help="scan and report without writing")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    marker = root / INDEX_DIR / MARKER_NAME
    scan_started_ns = time.time_ns()
    previous = read_marker(marker)
    do_full = args.full or previous is None

    if do_full:
        files_seen, aircraft, updated, removed = full_rebuild(root, dry_run=args.dry_run)
        mode = "full"
    else:
        files_seen, aircraft, updated, removed = incremental(root, previous, dry_run=args.dry_run)
        mode = "incremental"

    write_marker(marker, scan_started_ns, dry_run=args.dry_run)
    print(
        f"mode={mode} trace_files={files_seen} aircraft_touched={aircraft} "
        f"indexes_updated={updated} indexes_removed={removed} root={root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
