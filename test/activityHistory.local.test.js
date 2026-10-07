"use strict";

const { test } = require('node:test');
const assert = require('node:assert/strict');
const ah = require('../payload/activityHistory.js');

function reset(hist, recent) {
    ah.historicalDatesByIcao = {};
    ah.recentDatesByIcao = {};
    if (hist) ah.historicalDatesByIcao.abc123 = hist;
    if (recent) ah.recentDatesByIcao.abc123 = recent;
}

function traceFrom(baseIso, offsets) {
    const base = Math.floor(Date.parse(baseIso) / 1000);
    return { timestamp: base, trace: offsets.map((o) => [o, 18.0, -67.0]) };
}

test('extracts UTC dates across midnight', () => {
    const data = traceFrom('2026-09-05T00:01:00Z', [-120, 0, 120]);
    assert.deepEqual(ah.datesFromTrace(data), ['2026-09-04', '2026-09-05']);
});

test('normalizes ICAO keys', () => {
    reset();
    ah.mergeTraceDates(' A7C4EF ', ['2026-09-05']);
    assert.deepEqual(ah.recentDatesByIcao.a7c4ef, ['2026-09-05']);
});

test('previous and next skip inactive days', () => {
    reset(['2026-08-24', '2026-08-26'], ['2026-09-05']);
    assert.equal(ah.getNextDate('ABC123', '2026-08-24'), '2026-08-26');
    assert.equal(ah.getNextDate('ABC123', '2026-08-26'), '2026-09-05');
    assert.equal(ah.getPrevDate('ABC123', '2026-09-05'), '2026-08-26');
});

test('most recent date includes live edge', () => {
    reset(['2026-08-26'], ['2026-09-05']);
    assert.equal(ah.mostRecentActiveDate('abc123'), '2026-09-05');
});

test('when no activity is known, calendar remains unrestricted', () => {
    reset();
    assert.equal(ah.isNoActivityDay('abc123', '2020-01-01'), false);
});

test('when activity is known, inactive days are blocked', () => {
    reset(['2026-08-26']);
    assert.equal(ah.isNoActivityDay('abc123', '2026-08-25'), true);
    assert.equal(ah.isNoActivityDay('abc123', '2026-08-26'), false);
});

test('historical fetch uses local sharded globe_history path', async () => {
    reset();
    const oldFetch = globalThis.fetch;
    let requested = null;
    globalThis.fetch = async (url) => {
        requested = url;
        return { ok: true, json: async () => ({ dates: ['2026-08-24'] }) };
    };
    try {
        assert.deepEqual(await ah.fetchHistoricalDates('A8D2C1'), ['2026-08-24']);
        assert.equal(requested, 'globe_history/active-dates/c1/a8d2c1.json');
    } finally {
        globalThis.fetch = oldFetch;
    }
});
