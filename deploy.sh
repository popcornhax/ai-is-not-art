#!/usr/bin/env bash
# deploy.sh — Deploy ai-is-not-art to stickerbox.local
#
# Usage:
#   ./deploy.sh
#   PI_HOST=mypi.local ./deploy.sh

set -euo pipefail

PI_HOST="${PI_HOST:-stickerbox.local}"
PI_USER="${PI_USER:-sticker}"
PI_PASS="${PI_PASS:-}"
REMOTE_DIR="/home/${PI_USER}/ai-is-not-art"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v sshpass &>/dev/null; then
    SSH="sshpass -p ${PI_PASS} ssh -o StrictHostKeyChecking=accept-new"
    RSYNC_RSH="sshpass -p ${PI_PASS} ssh -o StrictHostKeyChecking=accept-new"
else
    echo "Note: sshpass not found — you will be prompted for the password."
    SSH="ssh -o StrictHostKeyChecking=accept-new"
    RSYNC_RSH="ssh -o StrictHostKeyChecking=accept-new"
fi

echo "==> Deploying ai-is-not-art to ${PI_USER}@${PI_HOST}:${REMOTE_DIR}"

# ---------------------------------------------------------------------------
# Step 1: Sync project files
# ---------------------------------------------------------------------------
echo ""
echo "--- Syncing files ---"
rsync -av --progress \
    -e "${RSYNC_RSH}" \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='run-logs/' \
    "${SCRIPT_DIR}/" \
    "${PI_USER}@${PI_HOST}:${REMOTE_DIR}/"

# ---------------------------------------------------------------------------
# Step 2: Remote setup
# ---------------------------------------------------------------------------
echo ""
echo "--- Running remote setup ---"

$SSH "${PI_USER}@${PI_HOST}" bash <<'REMOTE'
set -euo pipefail
REMOTE_DIR="/home/sticker/ai-is-not-art"
cd "${REMOTE_DIR}"

echo "  [1/4] Creating Python venv and installing dependencies..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

echo "  [2/4] Creating directories..."
mkdir -p run-logs

echo "  [3/4] Installing systemd service..."
sudo cp "${REMOTE_DIR}/ai-is-not-art.service" /etc/systemd/system/ai-is-not-art.service
sudo systemctl daemon-reload
sudo systemctl enable ai-is-not-art

echo "  [4/4] Starting service..."
sudo systemctl restart ai-is-not-art

sleep 2
echo ""
echo "  Service status:"
sudo systemctl status ai-is-not-art --no-pager || true
REMOTE

echo ""
echo "==> Deploy complete!"
echo ""
echo "    Logs: ssh ${PI_USER}@${PI_HOST} 'journalctl -u ai-is-not-art -f'"
echo ""
echo "IMPORTANT: Edit config.toml and set your OpenAI API key before the"
echo "           first button press, then re-run deploy.sh to push the update."
