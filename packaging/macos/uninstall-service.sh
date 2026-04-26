#!/bin/bash
# Warden macOS service uninstaller.
# Safe to run via MDM or manually. Idempotent — will not fail if already removed.

set -euo pipefail

SERVICE_LABEL="com.github.luisfontes19.warden"
BINARY_PATH="/usr/local/bin/warden"
PLIST_PATH="/Library/LaunchDaemons/${SERVICE_LABEL}.plist"
LOG_DIR="/var/log/warden"
APP_SUPPORT_PATH="Library/Application Support/warden"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo)." >&2
    exit 1
fi

if launchctl list | grep -q "$SERVICE_LABEL" 2>/dev/null; then
    echo "Stopping and unloading service ..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
else
    echo "Service not currently loaded — skipping unload."
fi

[[ -f "$PLIST_PATH" ]] && rm -f "$PLIST_PATH" && echo "Removed ${PLIST_PATH}."
[[ -f "$BINARY_PATH" ]] && rm -f "$BINARY_PATH" && echo "Removed ${BINARY_PATH}."
[[ -f "$APP_SUPPORT_PATH" ]] && rm -f "$APP_SUPPORT_PATH" && echo "Removed ${APP_SUPPORT_PATH}."

echo "Warden service uninstalled."
echo "Note: logs at ${LOG_DIR} were preserved. Remove manually if needed."