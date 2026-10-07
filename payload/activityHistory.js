"use strict";

// Local per-aircraft history availability for stock tar1090.
// Historical dates come from static gzip JSON files generated from /var/globe_history.
// Recent dates come from readsb's live trace_full file so today's activity is available
// before the long-term globe_history archive catches up.
var ActivityHistory = {
    historicalDatesByIcao: {},
    recentDatesByIcao: {},

    normalizeIcao: function(icao) {
        return String(icao || '').trim().toLowerCase();
    },

    toDateStr: function(date) {
        if (typeof date === 'string') return date;
        return date.getUTCFullYear() + '-' +
            String(date.getUTCMonth() + 1).padStart(2, '0') + '-' +
            String(date.getUTCDate()).padStart(2, '0');
    },

    hasActivity: function(icao) {
        icao = this.normalizeIcao(icao);
        var historical = this.historicalDatesByIcao[icao];
        var recent = this.recentDatesByIcao[icao];
        return !!((historical && historical.length) || (recent && recent.length));
    },

    // null = unavailable/failed and may be retried; [] = fetched successfully but empty.
    fetchHistoricalDates: async function(icao) {
        icao = this.normalizeIcao(icao);
        if (!icao) return null;
        if (Array.isArray(this.historicalDatesByIcao[icao])) {
            return this.historicalDatesByIcao[icao];
        }
        try {
            var suffix = icao.slice(-2);
            var response = await fetch('globe_history/active-dates/' + suffix + '/' + icao + '.json');
            if (!response.ok) return null;
            var data = await response.json();
            var dates = Array.isArray(data.dates) ? data.dates.slice() : [];
            dates.sort().reverse();
            return (this.historicalDatesByIcao[icao] = dates);
        } catch (e) {
            return null;
        }
    },

    fetchTraceDates: async function(icao) {
        icao = this.normalizeIcao(icao);
        if (!icao) return null;
        try {
            var response = await fetch('data/traces/' + icao.slice(-2) + '/trace_full_' + icao + '.json');
            if (!response.ok) return null;
            var data = await response.json();
            return this.datesFromTrace(data);
        } catch (e) {
            return null;
        }
    },

    datesFromTrace: function(traceData) {
        var trace = traceData && traceData.trace;
        if (!trace || !trace.length) return [];
        var base = Number(traceData.timestamp) || 0;
        var seen = {};
        var out = [];
        for (var i = 0; i < trace.length; i++) {
            var p = trace[i];
            if (!p || !Number.isFinite(p[0])) continue;
            var date = new Date((base + p[0]) * 1000);
            if (!Number.isFinite(date.getTime())) continue;
            var ds = this.toDateStr(date);
            if (!seen[ds]) {
                seen[ds] = true;
                out.push(ds);
            }
        }
        return out;
    },

    mergeTraceDates: function(icao, dates) {
        icao = this.normalizeIcao(icao);
        if (!icao || !dates || !dates.length) return;
        var existing = this.recentDatesByIcao[icao] || [];
        var set = {};
        for (var i = 0; i < existing.length; i++) set[existing[i]] = true;
        for (var j = 0; j < dates.length; j++) set[dates[j]] = true;
        this.recentDatesByIcao[icao] = Object.keys(set).sort().reverse();
    },

    getActiveDatesSet: function(icao) {
        icao = this.normalizeIcao(icao);
        var set = {};
        var hist = this.historicalDatesByIcao[icao];
        if (hist) for (var i = 0; i < hist.length; i++) set[hist[i]] = true;
        var recent = this.recentDatesByIcao[icao];
        if (recent) for (var j = 0; j < recent.length; j++) set[recent[j]] = true;
        return set;
    },

    sortedActiveDates: function(icao) {
        return Object.keys(this.getActiveDatesSet(icao)).sort();
    },

    getNextDate: function(icao, currentDate) {
        var dates = this.sortedActiveDates(icao);
        var current = this.toDateStr(currentDate);
        for (var i = 0; i < dates.length; i++) {
            if (dates[i] > current) return dates[i];
        }
        return null;
    },

    getPrevDate: function(icao, currentDate) {
        var dates = this.sortedActiveDates(icao);
        var current = this.toDateStr(currentDate);
        for (var i = dates.length - 1; i >= 0; i--) {
            if (dates[i] < current) return dates[i];
        }
        return null;
    },

    mostRecentActiveDate: function(icao) {
        var dates = this.sortedActiveDates(icao);
        return dates.length ? dates[dates.length - 1] : null;
    },

    isNoActivityDay: function(icao, dateStr) {
        return this.hasActivity(icao) && !this.getActiveDatesSet(icao)[dateStr];
    }
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = ActivityHistory;
}
