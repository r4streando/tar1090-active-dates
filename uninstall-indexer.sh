#!/bin/bash
# Removes only the Active Dates indexer/timer and generated indexes; trace history is untouched.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run this with sudo." >&2
    exit 1
fi

systemctl disable --now tar1090-active-dates.timer 2>/dev/null || true
rm -f /etc/systemd/system/tar1090-active-dates.timer
rm -f /etc/systemd/system/tar1090-active-dates.service
rm -f /usr/local/sbin/tar1090-active-dates-index
systemctl daemon-reload
rm -rf /var/globe_history/active-dates

echo "Removed Active Dates indexer and generated indexes. /var/globe_history trace files were not touched."
