#!/usr/bin/env bash
#
# Sets up vdirsyncer + todoman on a laptop for GTD task management.
#
# What this does:
#   1. Installs vdirsyncer and todoman
#   2. Writes config files (prompts before overwriting)
#   3. Runs vdirsyncer discover + sync
#   4. Adds the 'cap' alias to ~/.zshrc
#   5. Optionally installs a systemd user timer for auto-sync
#
# Usage: ./setup-laptop.sh [RADICALE_URL] [USERNAME]
#   RADICALE_URL  - Radicale server URL (default: http://10.10.10.10:5232)
#   USERNAME      - Radicale username (default: gdobbe)

set -euo pipefail

RADICALE_URL="${1:-http://10.10.10.10:5232}"
USERNAME="${2:-gdobbe}"

VDIRSYNCER_CONFIG_DIR="${HOME}/.config/vdirsyncer"
VDIRSYNCER_CONFIG="${VDIRSYNCER_CONFIG_DIR}/config"
TODOMAN_CONFIG_DIR="${HOME}/.config/todoman"
TODOMAN_CONFIG="${TODOMAN_CONFIG_DIR}/config.py"
VDIRSYNCER_DATA="${HOME}/.local/share/vdirsyncer/gtd"

# --- Install ---

echo "=== Installing vdirsyncer and todoman ==="

if command -v pacman &>/dev/null; then
    sudo pacman -S --needed --noconfirm vdirsyncer todoman
elif command -v pipx &>/dev/null; then
    pipx install vdirsyncer
    pipx install todoman
else
    echo "No supported package manager found. Install vdirsyncer and todoman manually."
    echo "  pipx install vdirsyncer && pipx install todoman"
    exit 1
fi

# --- vdirsyncer config ---

echo ""
echo "=== Configuring vdirsyncer ==="

mkdir -p "${VDIRSYNCER_CONFIG_DIR}"
mkdir -p "${VDIRSYNCER_DATA}"

if [[ -f "${VDIRSYNCER_CONFIG}" ]]; then
    echo "vdirsyncer config already exists at ${VDIRSYNCER_CONFIG}"
    read -rp "Overwrite? [y/N] " overwrite
    [[ "${overwrite}" =~ ^[Yy]$ ]] || { echo "Skipping vdirsyncer config."; }
fi

if [[ ! -f "${VDIRSYNCER_CONFIG}" ]] || [[ "${overwrite:-}" =~ ^[Yy]$ ]]; then
    cat > "${VDIRSYNCER_CONFIG}" <<EOF
[general]
status_path = "~/.local/share/vdirsyncer/status/"

[pair gtd]
a = "gtd_local"
b = "gtd_remote"
collections = ["from b"]
conflict_resolution = "b wins"

[storage gtd_local]
type = "filesystem"
path = "${VDIRSYNCER_DATA}"
fileext = ".ics"

[storage gtd_remote]
type = "caldav"
url = "${RADICALE_URL}/${USERNAME}/"
username = "${USERNAME}"
password.fetch = ["command", "secret-tool", "lookup", "service", "radicale", "user", "${USERNAME}"]
EOF

    echo "Wrote ${VDIRSYNCER_CONFIG}"
    echo ""
    echo "NOTE: Store your Radicale password in the system keyring:"
    echo "  secret-tool store --label='Radicale' service radicale user ${USERNAME}"
    echo ""
    echo "Or replace the password.fetch line with:"
    echo '  password = "your-password-here"'
fi

# --- todoman config ---

echo ""
echo "=== Configuring todoman ==="

mkdir -p "${TODOMAN_CONFIG_DIR}"

if [[ ! -f "${TODOMAN_CONFIG}" ]]; then
    cat > "${TODOMAN_CONFIG}" <<EOF
path = "${VDIRSYNCER_DATA}/*"
date_format = "%Y-%m-%d"
time_format = "%H:%M"
default_list = "gtd-inbox"
default_priority = 0
EOF

    echo "Wrote ${TODOMAN_CONFIG}"
else
    echo "todoman config already exists at ${TODOMAN_CONFIG}, skipping."
fi

# --- Shell alias ---

echo ""
echo "=== Shell alias ==="

ALIAS_LINE='alias cap='\''todo new --list gtd-inbox'\'''

if grep -qF 'alias cap=' ~/.zshrc 2>/dev/null; then
    echo "'cap' alias already in ~/.zshrc, skipping."
else
    echo "" >> ~/.zshrc
    echo "# GTD quick capture" >> ~/.zshrc
    echo "${ALIAS_LINE}" >> ~/.zshrc
    echo "Added 'cap' alias to ~/.zshrc"
    echo "  Usage: cap \"Call dentist\""
fi

# --- Initial sync ---

echo ""
echo "=== Running vdirsyncer discover + sync ==="

read -rp "Run vdirsyncer discover now? (requires server to be running) [y/N] " do_sync
if [[ "${do_sync}" =~ ^[Yy]$ ]]; then
    vdirsyncer discover gtd
    vdirsyncer sync gtd
    echo ""
    echo "Sync complete. Try: todo list"
else
    echo "Skipping. Run manually when ready:"
    echo "  vdirsyncer discover gtd && vdirsyncer sync gtd"
fi

# --- Auto-sync timer (optional) ---

echo ""
echo "=== Auto-sync timer (optional) ==="
read -rp "Install systemd user timer for auto-sync every 5 minutes? [y/N] " do_timer

if [[ "${do_timer}" =~ ^[Yy]$ ]]; then
    TIMER_DIR="${HOME}/.config/systemd/user"
    mkdir -p "${TIMER_DIR}"

    cat > "${TIMER_DIR}/vdirsyncer-gtd.service" <<EOF
[Unit]
Description=Sync GTD calendars via vdirsyncer

[Service]
Type=oneshot
ExecStart=$(command -v vdirsyncer) sync gtd
EOF

    cat > "${TIMER_DIR}/vdirsyncer-gtd.timer" <<EOF
[Unit]
Description=Auto-sync GTD calendars every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable --now vdirsyncer-gtd.timer
    echo "Timer installed and started."
    echo "  Check status: systemctl --user status vdirsyncer-gtd.timer"
else
    echo "Skipping auto-sync timer."
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Quick reference:"
echo "  cap \"thing\"          - capture to inbox"
echo "  todo list             - see all tasks"
echo "  todo list gtd-inbox   - see inbox"
echo "  vdirsyncer sync gtd   - manual sync"
