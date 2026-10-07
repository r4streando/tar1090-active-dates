# tar1090-active-dates

Small downstream enhancement for stock
[`wiedehopf/tar1090`](https://github.com/wiedehopf/tar1090) that makes History
navigate only dates on which the selected aircraft actually has trace data.

For a single selected aircraft:

- History opens on the most recent known active UTC date.
- The calendar highlights active dates and disables known empty dates.
- Previous/Next skip directly between observed dates.
- The live `trace_full` is merged in so today's activity works before
  `globe_history` archive rollover.
- Missing active-date index data falls back to normal tar1090 behavior.
- Multi-select, replay, and existing History deep links keep upstream behavior.

No trace files are modified.

## Supported tar1090 bases

The frontend patcher is deliberately fail-closed:

| tar1090 | upstream commit |
| --- | --- |
| `3.14.1819` | `2704011a6dbf09266daac896a0896159ee0646e1` |
| `3.14.1823` | `e784ee5ae82948f41efe3ef5c235ade0943ab8ff` |

`3.14.1823` was current upstream when support was revalidated on 2026-10-07.
Do not force the patch onto a later commit: forward-port it and add that exact
revision to the supported list instead.

## Requirements

- stock tar1090 with `/var/globe_history` enabled;
- Git and Python 3;
- systemd;
- local `readsb` user with write access to `/var/globe_history`;
- Node.js is optional but strongly recommended for the patcher's JavaScript
  syntax and unit-test preflight;
- tar1090's normal `/globe_history/` web alias.

The supplied static gzip indexes work directly with stock tar1090 **lighttpd**
configuration. If you use nginx, add equivalent handling inside the tar1090
`/globe_history/` location, for example:

```nginx
location ~ active-dates/ {
    gzip off;
    add_header Content-Encoding "gzip";
    add_header Content-Type "application/json";
}
```

`verify-install.sh` fetches a real index through HTTP and will fail if decoding
is wrong.

## Deploy on a current installation

The commands below intentionally create a separate tar1090 source checkout so
future upstream installs do not leave an untracked hand-edited web tree.

```bash
sudo git clone https://github.com/r4streando/tar1090-active-dates.git \
  /opt/tar1090-active-dates

mkdir -p "$HOME/src"
git clone https://github.com/wiedehopf/tar1090.git \
  "$HOME/src/tar1090-active-dates-upstream"

cd "$HOME/src/tar1090-active-dates-upstream"
git checkout e784ee5ae82948f41efe3ef5c235ade0943ab8ff

python3 /opt/tar1090-active-dates/apply-active-dates.py --check .
python3 /opt/tar1090-active-dates/apply-active-dates.py .

git diff --check
git diff --stat
```

Expected `git status --short` output:

```text
 M cachebust.list
 M html/index.html
 M html/script.js
 M html/style.css
?? html/activityHistory.js
```

Install/build the per-aircraft date index:

```bash
sudo /opt/tar1090-active-dates/install-indexer.sh
```

Then install the patched tar1090 checkout using tar1090's local/test install
path:

```bash
cd "$HOME/src/tar1090-active-dates-upstream"
sudo ./install.sh test
```

Verify everything through the actual web server:

```bash
/opt/tar1090-active-dates/verify-install.sh
```

If your tar1090 instance is not named `tar1090`, pass the instance name:

```bash
/opt/tar1090-active-dates/verify-install.sh myinstance
```

Finally hard-refresh the browser.

## Indexer

Historical activity is inferred only from paths like:

```text
/var/globe_history/2026/10/07/traces/c1/trace_full_a8d2c1.json
```

The generated index is sharded the same way:

```text
/var/globe_history/active-dates/c1/a8d2c1.json
```

Its logical JSON is:

```json
{"dates":["2026-10-07","2026-10-05","2026-09-29"]}
```

The `.json` file contains gzip bytes because tar1090's lighttpd
`/globe_history/` path advertises `Content-Encoding: gzip`.

The first installation performs a full reconciliation. The timer then runs
incrementally every six hours, with randomized delay.

Check it with:

```bash
systemctl list-timers tar1090-active-dates.timer
systemctl status tar1090-active-dates.timer
journalctl -u tar1090-active-dates.service --no-pager
```

Force a complete reconciliation after manually pruning/deleting archive data:

```bash
sudo -u readsb /usr/local/sbin/tar1090-active-dates-index \
  --root /var/globe_history --full
```

## Updating tar1090

Do not simply pull a newer upstream commit into the patched checkout. The
patcher deliberately accepts only reviewed upstream revisions.

When upstream advances:

1. inspect changes to `html/script.js`, `html/index.html`, `html/style.css`, and
   `cachebust.list`;
2. verify the Active Dates anchors still apply correctly;
3. run the JavaScript tests and syntax checks;
4. add the new exact version/commit to `SUPPORTED_BASES`;
5. build a fresh clean upstream checkout and reapply the patch.

The static indexer generally does not need to be reinstalled for a frontend-only
upstream tar1090 update.

## Uninstall the indexer

```bash
sudo /opt/tar1090-active-dates/uninstall-indexer.sh
```

That removes the timer, indexer executable, and generated `active-dates`
indexes. It does **not** delete historical trace files.

Reinstall stock tar1090 separately to remove the frontend patch.

## Development checks

```bash
node --test test/activityHistory.local.test.js
node --check payload/activityHistory.js
python3 -m py_compile apply-active-dates.py build-active-dates.py
bash -n install-indexer.sh uninstall-indexer.sh verify-install.sh
```

See [`DESIGN.md`](DESIGN.md) and [`ATTRIBUTION.md`](ATTRIBUTION.md) for design
and provenance details.

## License

GPL v2 or later. See [`LICENSE`](LICENSE).
