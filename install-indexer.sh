#!/bin/bash
# Installs the static globe_history active-date indexer and its systemd timer.
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=/var/globe_history

if [[ $EUID -ne 0 ]]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi
if ! id readsb >/dev/null 2>&1; then
    echo "Expected local user 'readsb' was not found; refusing to install the timer." >&2
    exit 1
fi
if [[ ! -d "$ROOT" ]]; then
    echo "$ROOT does not exist; refusing to continue." >&2
    exit 1
fi

install -m 0755 "$HERE/build-active-dates.py" /usr/local/sbin/tar1090-active-dates-index
install -m 0644 "$HERE/systemd/tar1090-active-dates.service" /etc/systemd/system/tar1090-active-dates.service
install -m 0644 "$HERE/systemd/tar1090-active-dates.timer" /etc/systemd/system/tar1090-active-dates.timer

# Verify readsb can write the index directory without altering trace data.
install -d -o readsb -g "$(id -g readsb)" -m 0755 "$ROOT/active-dates"

systemctl daemon-reload

# Initial reconciliation. Later timer runs are incremental.
runuser -u readsb -- /usr/local/sbin/tar1090-active-dates-index --root "$ROOT" --full

systemctl enable --now tar1090-active-dates.timer

echo
echo "Installed. Timer status:"
systemctl --no-pager --full status tar1090-active-dates.timer || true
