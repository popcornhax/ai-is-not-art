#!/usr/bin/env bash
# deploy.sh — Full deployment of PixCut-App + ai-is-not-art to a Raspberry Pi
#
# Usage:
#   PI_HOST=mypi.local PI_USER=pi ./deploy.sh
#
# Expects PixCut-App to be a sibling directory: ../PixCut-App

set -euo pipefail

PI_HOST="${PI_HOST:?Set PI_HOST to the Raspberry Pi hostname or address}"
PI_USER="${PI_USER:?Set PI_USER to the Raspberry Pi SSH user}"
PI_PASS="${PI_PASS:-}"
# SECURE=true  → kiosk binds to 127.0.0.1, port 8000 blocked from LAN (conference default)
# SECURE=false → kiosk binds to 0.0.0.0,   port 8000 open on LAN (home/dev use)
SECURE="${SECURE:-true}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXCUT_DIR="${PIXCUT_DIR:-$(cd "${SCRIPT_DIR}/../PixCut-App" 2>/dev/null && pwd || echo "")}"

REMOTE_PIXCUT="/home/${PI_USER}/pixcut-app"
REMOTE_AINA="/home/${PI_USER}/ai-is-not-art"

if command -v sshpass &>/dev/null && [ -n "${PI_PASS}" ]; then
    export SSHPASS="${PI_PASS}"
    SSH="sshpass -e ssh -o StrictHostKeyChecking=accept-new"
    RSYNC_RSH="sshpass -e ssh -o StrictHostKeyChecking=accept-new"
else
    echo "Using SSH keys or interactive password authentication."
    SSH="ssh -o StrictHostKeyChecking=accept-new"
    RSYNC_RSH="ssh -o StrictHostKeyChecking=accept-new"
fi

echo "==> Deploying to ${PI_USER}@${PI_HOST}"
echo "    PixCut-App source: ${PIXCUT_DIR:-NOT FOUND}"
echo "    ai-is-not-art source: ${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# Step 1: Sync PixCut-App
# ---------------------------------------------------------------------------
if [ -z "${PIXCUT_DIR}" ] || [ ! -d "${PIXCUT_DIR}" ]; then
    echo ""
    echo "ERROR: PixCut-App directory not found at ${SCRIPT_DIR}/../PixCut-App"
    echo "       Set PIXCUT_DIR=/path/to/PixCut-App and re-run."
    exit 1
fi

echo ""
echo "--- [1/4] Syncing PixCut-App ---"
rsync -a --progress \
    -e "${RSYNC_RSH}" \
    --exclude='.venv/' \
    --exclude='run-logs/' \
    --exclude='output/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='research/' \
    --exclude='.git/' \
    "${PIXCUT_DIR}/" \
    "${PI_USER}@${PI_HOST}:${REMOTE_PIXCUT}/"

# ---------------------------------------------------------------------------
# Step 2: Sync ai-is-not-art
# ---------------------------------------------------------------------------
echo ""
echo "--- [2/4] Syncing ai-is-not-art ---"
rsync -a --progress \
    -e "${RSYNC_RSH}" \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='run-logs/' \
    "${SCRIPT_DIR}/" \
    "${PI_USER}@${PI_HOST}:${REMOTE_AINA}/"

# ---------------------------------------------------------------------------
# Step 3: Remote setup (both apps)
# ---------------------------------------------------------------------------
echo ""
echo "--- [3/4] Running remote setup ---"

$SSH "${PI_USER}@${PI_HOST}" env SECURE="${SECURE}" REMOTE_USER="${PI_USER}" REMOTE_PIXCUT="${REMOTE_PIXCUT}" REMOTE_AINA="${REMOTE_AINA}" bash <<'REMOTE'
set -euo pipefail

echo "  [a] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-dev libusb-1.0-0 python3-lgpio

echo "  [b] Adding ${REMOTE_USER} to plugdev group..."
sudo usermod -aG plugdev "${REMOTE_USER}" || true

echo "  [c] Installing udev rules..."
sudo cp "${REMOTE_PIXCUT}/99-pixcut.rules" /etc/udev/rules.d/99-pixcut.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "  [d] PixCut-App venv + dependencies..."
cd "${REMOTE_PIXCUT}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -r requirements-server.txt shapely

echo "  [e] PixCut kiosk systemd service..."
if [ "$SECURE" = "true" ]; then
    KIOSK_HOST="127.0.0.1"
    echo "      Secure mode: kiosk bound to 127.0.0.1 (localhost only)"
else
    KIOSK_HOST="0.0.0.0"
    echo "      LAN mode: kiosk bound to 0.0.0.0 (LAN accessible)"
fi
sed "s/--host [0-9.]\+/--host ${KIOSK_HOST}/" \
    "${REMOTE_PIXCUT}/pixcut-kiosk.service" \
    | sudo tee /etc/systemd/system/pixcut-kiosk.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable pixcut-kiosk
sudo systemctl restart pixcut-kiosk

echo "  [f] ai-is-not-art venv + dependencies..."
cd "${REMOTE_AINA}"
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r "${REMOTE_PIXCUT}/requirements.txt" shapely

echo "  [g] ai-is-not-art directories..."
mkdir -p run-logs

echo "  [h] Firewall (ufw)..."
sudo apt-get install -y ufw -qq
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow in on lo
if [ "$SECURE" = "true" ]; then
    echo "      Secure mode: port 8000 blocked from LAN"
else
    sudo ufw allow 8000
    echo "      LAN mode: port 8000 open"
fi
sudo ufw --force enable

echo "  [i] ai-is-not-art systemd service..."
sudo cp "${REMOTE_AINA}/ai-is-not-art.service" /etc/systemd/system/ai-is-not-art.service
sudo systemctl daemon-reload
sudo systemctl enable ai-is-not-art
sudo systemctl restart ai-is-not-art

sleep 2
echo ""
echo "  Kiosk service status:"
sudo systemctl status pixcut-kiosk --no-pager || true
echo ""
echo "  ai-is-not-art service status:"
sudo systemctl status ai-is-not-art --no-pager || true
REMOTE

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "--- [4/4] Verifying kiosk API ---"
sleep 3
if curl -sf "http://${PI_HOST}:8000/api/stickers" > /dev/null; then
    echo "    Kiosk API: OK  →  http://${PI_HOST}:8000"
else
    echo "    Kiosk API: not responding yet (may still be starting)"
fi

echo ""
echo "==> Deploy complete!"
echo ""
echo "    Kiosk UI:   http://${PI_HOST}:8000"
echo "    AINA logs:  ssh ${PI_USER}@${PI_HOST} 'journalctl -u ai-is-not-art -f'"
echo "    Kiosk logs: ssh ${PI_USER}@${PI_HOST} 'journalctl -u pixcut-kiosk -f'"
echo ""
echo "NEXT STEPS:"
echo "  1. Edit config.toml — set openai.api_key"
echo "  2. Set debug_mode = true for testing without printing"
echo "  3. Run ./deploy.sh again to push the updated config"
echo "  4. Wire the button and LED (see README for pinout)"
