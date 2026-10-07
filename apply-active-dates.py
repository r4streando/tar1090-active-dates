#!/usr/bin/env python3
"""Apply the Active Dates frontend patch to a supported stock tar1090 revision.

The patch is intentionally fail-closed. It requires a clean git checkout at one
of the exact supported upstream commits and verifies every source anchor before
writing anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SUPPORTED_BASES = {
    "2704011a6dbf09266daac896a0896159ee0646e1": "3.14.1819",
    "e784ee5ae82948f41efe3ef5c235ade0943ab8ff": "3.14.1823",
}

DATEPICKER_OLD = r'''    jQuery("#histDatePicker").datepicker({
        maxDate: '+1d',
        dateFormat: "yy-mm-dd",
        onSelect: function(date){
            setTraceDate({string: date});
            shiftTrace();
            jQuery("#histDatePicker").blur();
        },
        autoSize: true,
        onClose: !onMobile ? null : function(dateText, inst){
            jQuery("#histDatePicker").attr("disabled", false);
        },
        beforeShow: !onMobile ? null : function(input, inst){
            jQuery("#histDatePicker").attr("disabled", true);
        },
    });'''

DATEPICKER_NEW = r'''    jQuery("#histDatePicker").datepicker({
        maxDate: '+1d',
        dateFormat: "yy-mm-dd",
        onSelect: function(date){
            setTraceDate({string: date});
            shiftTrace();
            jQuery("#histDatePicker").blur();
        },
        autoSize: true,
        onClose: !onMobile ? null : function(dateText, inst){
            jQuery("#histDatePicker").attr("disabled", false);
        },
        beforeShow: !onMobile ? null : function(input, inst){
            jQuery("#histDatePicker").attr("disabled", true);
        },
        beforeShowDay: function(date) {
            const icao = activeDatesIcao();
            if (!icao || !ActivityHistory.hasActivity(icao)) return [true, '', ''];
            // Use the datepicker's local-calendar formatter. Formatting this Date with
            // UTC getters can shift a cell by a day in time zones east/west of UTC.
            const dateStr = jQuery.datepicker.formatDate('yy-mm-dd', date);
            if (ActivityHistory.isNoActivityDay(icao, dateStr)) {
                return [false, '', 'No activity'];
            }
            const active = ActivityHistory.getActiveDatesSet(icao)[dateStr] ? 'hist-active-date' : '';
            return [true, active, active ? 'Activity' : ''];
        },
    });'''

TOGGLE_OPEN_OLD = r'''        showTraceWasIsolation = onlySelected;
        toggleIsolation("on", "noRefresh");
        shiftTrace();'''

TOGGLE_OPEN_NEW = r'''        showTraceWasIsolation = onlySelected;
        toggleIsolation("on", "noRefresh");

        const historyIcao = activeDatesIcao();
        if (historyIcao && !replay) {
            jQuery('#leg_sel').text('Loading history dates ...');
            Promise.all([
                ActivityHistory.fetchHistoricalDates(historyIcao),
                ActivityHistory.fetchTraceDates(historyIcao).then(function(dates) {
                    ActivityHistory.mergeTraceDates(historyIcao, dates);
                }),
            ]).then(function() {
                // History may have been closed or the selected aircraft changed.
                if (!showTrace || activeDatesIcao() !== historyIcao) return;
                jQuery("#histDatePicker").datepicker("refresh");
                shiftTrace();
            });
        } else {
            // Multi-select and replay retain stock day-by-day behavior.
            shiftTrace();
        }'''

SHIFT_DATE_OLD = r'''    jQuery('#leg_sel').text('Loading ...');
    if (!traceDate || offset == "today") {
        if (replay) {
            setTraceDate({ ts: replay.ts.getTime() });
        } else {
            setTraceDate({ ts: new Date().getTime() });
        }
    } else if (offset) {
        setTraceDate({ ts: traceDate.getTime() + offset * 86400 * 1000 });
    }'''

SHIFT_DATE_NEW = r'''    jQuery('#leg_sel').text('Loading ...');
    const historyIcao = activeDatesIcao();
    const useActivityNav = historyIcao && traceDate && offset !== "today" && offset &&
        !replay && ActivityHistory.hasActivity(historyIcao);

    if (useActivityNav) {
        const targetDate = offset > 0
            ? ActivityHistory.getNextDate(historyIcao, traceDateString)
            : ActivityHistory.getPrevDate(historyIcao, traceDateString);
        if (!targetDate) {
            updateHistoryNavButtons();
            return;
        }
        setTraceDate({ string: targetDate });
    } else if (!traceDate || offset == "today") {
        if (replay) {
            setTraceDate({ ts: replay.ts.getTime() });
        } else {
            // A fresh single-aircraft History open lands on the newest known
            // active UTC day. Existing/deep-linked traceDate values are preserved.
            const mostRecent = (offset != "today" && historyIcao)
                ? ActivityHistory.mostRecentActiveDate(historyIcao) : null;
            setTraceDate(mostRecent ? { string: mostRecent } : { ts: new Date().getTime() });
        }
    } else if (offset) {
        // Multi-select or unavailable active-date data keeps stock +/-1 day stepping.
        setTraceDate({ ts: traceDate.getTime() + offset * 86400 * 1000 });
    }'''

HELPERS = r'''

// Active-date navigation is intentionally single-aircraft only. Multi-select
// keeps upstream's normal calendar and +/-1 day stepping.
function activeDatesIcao() {
    if (SelPlanes && SelPlanes.length > 1) return null;
    return SelectedPlane ? SelectedPlane.icao : null;
}

function updateHistoryNavButtons() {
    const icao = activeDatesIcao();
    if (!icao || !traceDateString || !ActivityHistory.hasActivity(icao)) {
        jQuery('#trace_back_1d').prop('disabled', false);
        jQuery('#trace_jump_1d').prop('disabled', false);
        return;
    }
    const hasPrev = !!ActivityHistory.getPrevDate(icao, traceDateString);
    const hasNext = !!ActivityHistory.getNextDate(icao, traceDateString);
    jQuery('#trace_back_1d').prop('disabled', !hasPrev);
    jQuery('#trace_jump_1d').prop('disabled', !hasNext);
}
'''

INDEX_SCRIPT_OLD = '    <script src="planeObject.js"></script>\n    <script src="script.js"></script>'
INDEX_SCRIPT_NEW = '    <script src="planeObject.js"></script>\n    <script src="activityHistory.js"></script>\n    <script src="script.js"></script>'

STYLE_OLD = '''#histDatePicker{\n  background: var(--BGCOLOR1);\n}\n\n#replayBar {'''
STYLE_NEW = '''#histDatePicker{\n  background: var(--BGCOLOR1);\n}\n\n.hist-active-date a.ui-state-default {\n  font-weight: bold;\n}\n\n#replayBar {'''

CACHE_OLD = 'planeObject.js\nscript.js\n'
CACHE_NEW = 'planeObject.js\nactivityHistory.js\nscript.js\n'


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=check,
    )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one upstream anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', nargs='?', default='.', help='stock tar1090 git checkout')
    parser.add_argument('--check', action='store_true', help='validate without writing')
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    kit = Path(__file__).resolve().parent
    if not (repo / '.git').exists():
        raise SystemExit(f"not a git checkout: {repo}")

    dirty = run(['git', 'status', '--porcelain'], repo).stdout.strip()
    if dirty:
        raise SystemExit('refusing: target worktree is not clean:\n' + dirty)

    head = run(['git', 'rev-parse', 'HEAD'], repo).stdout.strip()
    expected_version = SUPPORTED_BASES.get(head)
    if expected_version is None:
        supported = '\n'.join(f"  {version}  {commit}" for commit, version in SUPPORTED_BASES.items())
        raise SystemExit(
            f"refusing: unsupported tar1090 HEAD {head}\nSupported exact bases:\n{supported}"
        )

    version = (repo / 'version').read_text(encoding='utf-8').strip()
    if version != expected_version:
        raise SystemExit(
            f"refusing: HEAD {head} should report version {expected_version}, found {version}"
        )

    script_path = repo / 'html' / 'script.js'
    index_path = repo / 'html' / 'index.html'
    style_path = repo / 'html' / 'style.css'
    cache_path = repo / 'cachebust.list'
    activity_path = repo / 'html' / 'activityHistory.js'

    if activity_path.exists():
        raise SystemExit(f"refusing: {activity_path} already exists")

    script = script_path.read_text(encoding='utf-8')
    index = index_path.read_text(encoding='utf-8-sig')
    style = style_path.read_text(encoding='utf-8')
    cache = cache_path.read_text(encoding='utf-8')

    script = replace_once(script, DATEPICKER_OLD, DATEPICKER_NEW, 'datepicker')
    script = replace_once(script, TOGGLE_OPEN_OLD, TOGGLE_OPEN_NEW, 'toggleShowTrace open sequence')

    shift_start = script.find('function shiftTrace(offset) {')
    if shift_start < 0:
        raise RuntimeError('shiftTrace: function not found')
    shift_end = script.find('\nfunction ', shift_start + 1)
    if shift_end < 0:
        raise RuntimeError('shiftTrace: could not locate next top-level function')
    shift = script[shift_start:shift_end]
    shift = replace_once(shift, SHIFT_DATE_OLD, SHIFT_DATE_NEW, 'shiftTrace date-selection block')
    shift = replace_once(
        shift,
        '    updateAddressBar();\n}',
        '    updateAddressBar();\n    updateHistoryNavButtons();\n}',
        'shiftTrace navigation-button update',
    )
    script = script[:shift_start] + shift + HELPERS + script[shift_end:]

    index = replace_once(index, INDEX_SCRIPT_OLD, INDEX_SCRIPT_NEW, 'index script include')
    style = replace_once(style, STYLE_OLD, STYLE_NEW, 'active-date CSS')
    cache = replace_once(cache, CACHE_OLD, CACHE_NEW, 'cachebust list')
    payload = (kit / 'payload' / 'activityHistory.js').read_text(encoding='utf-8')

    node = shutil.which('node')
    if node:
        with tempfile.TemporaryDirectory(prefix='tar1090-active-dates-') as td:
            td_path = Path(td)
            temp_activity = td_path / 'activityHistory.js'
            temp_script = td_path / 'script.js'
            temp_activity.write_text(payload, encoding='utf-8')
            temp_script.write_text(script, encoding='utf-8')
            for path in (temp_activity, temp_script):
                proc = subprocess.run(
                    [node, '--check', str(path)], text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                if proc.returncode:
                    raise SystemExit(
                        f"node --check failed for transformed {path.name}:\n{proc.stderr}"
                    )

        tests = kit / 'test' / 'activityHistory.local.test.js'
        proc = subprocess.run(
            [node, '--test', str(tests)], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if proc.returncode:
            raise SystemExit('ActivityHistory tests failed:\n' + proc.stdout)
    else:
        print('warning: node not found; JavaScript syntax/unit tests were skipped', file=sys.stderr)

    if args.check:
        print(f"Preflight OK: tar1090 {version} / {head}")
        print('All expected upstream anchors were found exactly once; no files were changed.')
        return 0

    script_path.write_text(script, encoding='utf-8')
    index_path.write_text(index, encoding='utf-8-sig')
    style_path.write_text(style, encoding='utf-8')
    cache_path.write_text(cache, encoding='utf-8')
    activity_path.write_text(payload, encoding='utf-8')

    print(f"Active Dates patch applied to tar1090 {version} / {head}")
    print('Changed files:')
    print(run(['git', 'status', '--short'], repo).stdout.rstrip())
    print('\nReview with: git diff --check && git diff --stat')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
