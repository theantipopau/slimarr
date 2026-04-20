#!/usr/bin/env bash
# install.sh — Slimarr installer for Linux / macOS
# Usage:
#   bash install.sh                  # install deps + build frontend
#   bash install.sh --skip-frontend  # skip npm install/build
#   bash install.sh --service        # also install systemd service (Linux only)
#   bash install.sh --uninstall      # remove systemd service

set -euo pipefail

SKIP_FRONTEND=0
INSTALL_SERVICE=0
UNINSTALL=0
SERVICE_NAME="slimarr"
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/venv"

for arg in "$@"; do
  case $arg in
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --service)       INSTALL_SERVICE=1 ;;
    --uninstall)     UNINSTALL=1 ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

# ── Uninstall ─────────────────────────────────────────────────────────────────
if [[ $UNINSTALL -eq 1 ]]; then
  if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    sudo systemctl stop "$SERVICE_NAME"
  fi
  if [[ -f /etc/systemd/system/$SERVICE_NAME.service ]]; then
    sudo systemctl disable "$SERVICE_NAME"
    sudo rm /etc/systemd/system/$SERVICE_NAME.service
    sudo systemctl daemon-reload
    echo -e "${GREEN}Service removed.${NC}"
  else
    echo "Service not found."
  fi
  exit 0
fi

echo ""
echo -e "${GREEN}  ┌─────────────────────────────┐${NC}"
echo -e "${GREEN}  │   Slimarr Installer v1.0    │${NC}"
echo -e "${GREEN}  └─────────────────────────────┘${NC}"
echo ""

# ── 1. Python venv ────────────────────────────────────────────────────────────
echo -e "${CYAN}[1/5] Setting up Python virtual environment...${NC}"
PYTHON_BIN=""
for py in python3.12 python3.13 python3.11 python3; do
  if command -v "$py" &>/dev/null; then
    PYTHON_BIN=$(command -v "$py")
    break
  fi
done
if [[ -z $PYTHON_BIN ]]; then
  echo -e "${RED}Python 3.11+ not found. Install it first (e.g. apt install python3.12).${NC}"
  exit 1
fi
echo -e "  Using: $PYTHON_BIN ($($PYTHON_BIN --version))"
if [[ ! -d $VENV ]]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi
echo -e "${GREEN}  Virtual environment ready.${NC}"

# ── 2. pip install ────────────────────────────────────────────────────────────
echo -e "${CYAN}[2/5] Installing Python dependencies...${NC}"
"$VENV/bin/python" -m pip install --upgrade pip -q
"$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt" -q
echo -e "${GREEN}  Python dependencies installed.${NC}"

# ── 3 & 4. Frontend ──────────────────────────────────────────────────────────
if [[ $SKIP_FRONTEND -eq 0 ]]; then
  if ! command -v npm &>/dev/null; then
    echo -e "${RED}npm not found. Install Node.js 18+ (https://nodejs.org) or use --skip-frontend.${NC}"
    exit 1
  fi
  echo -e "${CYAN}[3/5] Installing frontend dependencies...${NC}"
  (cd "$ROOT/frontend" && npm install --silent)
  echo -e "${CYAN}[4/5] Building frontend...${NC}"
  (cd "$ROOT/frontend" && npm run build)
  echo -e "${GREEN}  Frontend built.${NC}"
else
  echo -e "${YELLOW}[3/5] Skipping frontend install.${NC}"
  echo -e "${YELLOW}[4/5] Skipping frontend build.${NC}"
fi

# ── 5. Data directories + default config ─────────────────────────────────────
echo -e "${CYAN}[5/5] Preparing data directories...${NC}"
mkdir -p "$ROOT/data" "$ROOT/data/logs" "$ROOT/data/MediaCover" "$ROOT/data/recycling"

if [[ ! -f $ROOT/config.yaml ]]; then
  cat > "$ROOT/config.yaml" <<'YAML'
server:
  host: "0.0.0.0"
  port: 9494
  log_level: "info"

plex:
  url: "http://localhost:32400"
  token: ""
  library_sections: []

sabnzbd:
  url: "http://localhost:8080"
  api_key: ""
  category: "slimarr"

prowlarr:
  enabled: false
  url: "http://localhost:9696"
  api_key: ""

radarr:
  enabled: false
  url: "http://localhost:7878"
  api_key: ""

tmdb:
  api_key: ""

comparison:
  min_savings_percent: 10.0
  allow_resolution_downgrade: false
  downgrade_min_savings_percent: 40.0
  preferred_codecs: ["av1", "h265"]
  max_candidate_age_days: 3650
  minimum_file_size_mb: 500

files:
  recycling_bin: "./data/recycling"
  recycling_bin_cleanup_days: 30

schedule:
  start_time: "01:00"
  end_time: "07:00"
  max_downloads_per_night: 10
  throttle_seconds: 30
YAML
  echo -e "${YELLOW}  Created default config.yaml — edit it before starting!${NC}"
fi
echo -e "${GREEN}  Data directories ready.${NC}"

# ── systemd service ───────────────────────────────────────────────────────────
if [[ $INSTALL_SERVICE -eq 1 ]]; then
  if [[ $(uname) != "Linux" ]]; then
    echo -e "${YELLOW}--service is Linux-only (systemd). Skipping on $(uname).${NC}"
  else
    CURRENT_USER=$(id -un)
    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
    echo -e "${CYAN}Installing systemd service as user '$CURRENT_USER'...${NC}"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Slimarr — Smart Plex movie replacement manager
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$ROOT
ExecStart=$VENV/bin/python $ROOT/run.py --headless
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl start "$SERVICE_NAME"
    echo -e "${GREEN}  Service '$SERVICE_NAME' installed and started.${NC}"
    echo -e "  Manage with: sudo systemctl {start|stop|restart|status} $SERVICE_NAME"
  fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  ✓ Installation complete!${NC}"
echo ""
echo "  Next steps:"
echo "    1. Edit config.yaml with your Plex token, SABnzbd API key, etc."
echo "    2. Start Slimarr:"
echo "         $VENV/bin/python run.py --headless          # foreground"
echo "         bash install.sh --service                   # systemd (auto-start)"
echo "    3. Open http://localhost:9494 and register your account."
echo ""
