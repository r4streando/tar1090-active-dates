# Attribution and provenance

This project is a small downstream enhancement for stock
[`wiedehopf/tar1090`](https://github.com/wiedehopf/tar1090).

The Active Dates behavior was designed after auditing the public
`ADSBexchange/tar1090` implementation of per-aircraft activity/history dates in
2026. The browser-side logic was adapted to use a local static index generated
from `/var/globe_history`, without ADS-B Exchange cloud APIs, authentication,
telemetry, account integration, Most Watched, feeder leaderboard, Turnstile, or
other aggregator-specific infrastructure.

The original local implementation was deployed against:

- tar1090 `3.14.1819`
- upstream commit `2704011a6dbf09266daac896a0896159ee0646e1`
- local patch commit `ae36accc784ca59332df3144498b397d8e57112b`

On 2026-10-07 the integration anchors were rechecked against current upstream:

- tar1090 `3.14.1823`
- upstream commit `e784ee5ae82948f41efe3ef5c235ade0943ab8ff`

Both exact upstream revisions are accepted by `apply-active-dates.py`.

Because this project modifies/integrates GPL-licensed tar1090 code, it is
published under GPL v2 or later; see `LICENSE`.
