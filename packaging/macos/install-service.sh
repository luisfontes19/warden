#!/bin/bash
# Warden macOS service installer.
#
# This script is hosted in the repo. The MDM policy only needs to fetch and run it.
# Paste the following into your MDM console (Jamf, Kandji, Mosyle, Intune, etc.)
# as a Script policy scoped to your target devices:
#
#   #!/bin/bash
#   INSTALLER_URL="https://raw.githubusercontent.com/luisfontes19/warden/main/packaging/macos/install-service.sh"
#   BINARY_URL="https://github.com/luisfontes19/warden/releases/latest/download/warden-macos"
#   curl -fsSL "$INSTALLER_URL" -o /tmp/warden-install.sh
#   BINARY_URL="$BINARY_URL" bash /tmp/warden-install.sh
#
# To pin a specific version, replace "latest" with a tag, e.g. "download/v1.2.0/warden-macos".
# To verify integrity, also pass: BINARY_SHA256="<sha256>" bash /tmp/warden-install.sh
#
# Manual usage:
#   sudo BINARY_URL="https://..." ./install-service.sh
#   sudo BINARY_URL="https://..." BINARY_SHA256="abc123..." ./install-service.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Parameters — prefer env vars, fall back to Jamf-style positional params
# ---------------------------------------------------------------------------
BINARY_URL="${BINARY_URL:-${4:-}}"
BINARY_SHA256="${BINARY_SHA256:-${5:-}}"

SERVICE_LABEL="com.github.luisfontes19.warden"
INSTALL_DIR="/usr/local/bin"
BINARY_NAME="warden"
BINARY_PATH="${INSTALL_DIR}/${BINARY_NAME}"
PLIST_PATH="/Library/LaunchDaemons/${SERVICE_LABEL}.plist"
LOG_DIR="/var/log/warden"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ -z "$BINARY_URL" ]]; then
    echo "ERROR: BINARY_URL is required." >&2
    echo "  Set it as an environment variable or Jamf script parameter \$4." >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo)." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Download binary
# ---------------------------------------------------------------------------
echo "Downloading warden from ${BINARY_URL} ..."
TMP_BINARY="$(mktemp)"
curl --fail --silent --show-error --location "$BINARY_URL" --output "$TMP_BINARY"

if [[ -n "$BINARY_SHA256" ]]; then
    echo "Verifying checksum ..."
    ACTUAL_SHA256="$(shasum -a 256 "$TMP_BINARY" | awk '{print $1}')"
    if [[ "$ACTUAL_SHA256" != "$BINARY_SHA256" ]]; then
        echo "ERROR: Checksum mismatch." >&2
        echo "  Expected: ${BINARY_SHA256}" >&2
        echo "  Got:      ${ACTUAL_SHA256}" >&2
        rm -f "$TMP_BINARY"
        exit 1
    fi
    echo "Checksum verified."
fi

# ---------------------------------------------------------------------------
# Install binary
# ---------------------------------------------------------------------------
echo "Installing binary to ${BINARY_PATH} ..."
mkdir -p "$INSTALL_DIR"
mv "$TMP_BINARY" "$BINARY_PATH"
chmod 755 "$BINARY_PATH"
chown root:wheel "$BINARY_PATH"

# ---------------------------------------------------------------------------
# Create log directory
# ---------------------------------------------------------------------------
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"

# ---------------------------------------------------------------------------
# Write LaunchDaemon plist
# ---------------------------------------------------------------------------
echo "Writing LaunchDaemon plist to ${PLIST_PATH} ..."
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${BINARY_PATH}</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/warden.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/warden.error.log</string>
</dict>
</plist>
EOF

chmod 644 "$PLIST_PATH"
chown root:wheel "$PLIST_PATH"

# ---------------------------------------------------------------------------
# Load service (unload first to handle upgrades gracefully)
# ---------------------------------------------------------------------------
if launchctl list | grep -q "$SERVICE_LABEL" 2>/dev/null; then
    echo "Unloading existing service ..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

echo "Loading service ..."
launchctl load "$PLIST_PATH"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
sleep 2
if launchctl list | grep -q "$SERVICE_LABEL"; then
    echo "Warden service installed and running successfully."
else
    echo "WARNING: Service was loaded but does not appear in launchctl list." >&2
    echo "  Check logs at ${LOG_DIR}/warden.error.log" >&2
    exit 1
fi