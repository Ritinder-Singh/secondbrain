#!/usr/bin/env bash
# Engram setup script for Raspberry Pi 5 (ARM64, Raspberry Pi OS Bookworm)
# Usage: bash scripts/setup_pi.sh
set -euo pipefail

ENGRAM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGRAM_USER="$(whoami)"
PG_VERSION="15"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}▶ $*${NC}"; }
success() { echo -e "${GREEN}✓ $*${NC}"; }
die()     { echo -e "${RED}✗ $*${NC}"; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────

[[ "$(uname -m)" == "aarch64" ]] || die "This script is for ARM64 (Raspberry Pi). Got: $(uname -m)"
[[ "$EUID" -ne 0 ]] || die "Do not run as root. Run as your normal Pi user."

echo -e "\n${BOLD}Engram — Raspberry Pi Setup${NC}"
echo "Installing to: $ENGRAM_DIR"
echo "Running as:    $ENGRAM_USER"
echo ""

# ── System packages ───────────────────────────────────────────────────────────

info "Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    git curl wget build-essential \
    python3 python3-pip python3-venv \
    postgresql-${PG_VERSION} postgresql-server-dev-${PG_VERSION} \
    libpq-dev ffmpeg \
    portaudio19-dev libsndfile1 \
    pkg-config
success "System packages installed"

# ── pgvector ──────────────────────────────────────────────────────────────────

info "Installing pgvector..."
if ! sudo -u postgres psql -c "SELECT 1 FROM pg_available_extensions WHERE name='vector'" 2>/dev/null | grep -q 1; then
    TMP=$(mktemp -d)
    git clone --quiet --depth 1 https://github.com/pgvector/pgvector.git "$TMP/pgvector"
    cd "$TMP/pgvector"
    make -s
    sudo make -s install
    cd "$ENGRAM_DIR"
    rm -rf "$TMP"
    success "pgvector built and installed"
else
    success "pgvector already installed"
fi

# ── PostgreSQL: create DB + user ──────────────────────────────────────────────

info "Setting up PostgreSQL..."
sudo systemctl enable postgresql --quiet
sudo systemctl start postgresql

# Read DB config from .env if it exists, otherwise use defaults
DB_NAME="engram"; DB_USER="engram"; DB_PASS="engram"
if [[ -f "$ENGRAM_DIR/.env" ]]; then
    DB_NAME=$(grep ^POSTGRES_DB "$ENGRAM_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "engram")
    DB_USER=$(grep ^POSTGRES_USER "$ENGRAM_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "engram")
    DB_PASS=$(grep ^POSTGRES_PASSWORD "$ENGRAM_DIR/.env" 2>/dev/null | cut -d= -f2 || echo "engram")
fi

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
sudo -u postgres psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null
success "PostgreSQL ready (db: $DB_NAME, user: $DB_USER)"

# ── Ollama ────────────────────────────────────────────────────────────────────

info "Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl enable ollama --quiet
    sudo systemctl start ollama
    sleep 3  # wait for daemon to be ready
    success "Ollama installed"
else
    success "Ollama already installed"
    sudo systemctl start ollama 2>/dev/null || true
fi

info "Pulling models (this will take a while on first run)..."
ollama pull llama3.2:3b
ollama pull nomic-embed-text
success "Models ready"

# ── uv (Python package manager) ───────────────────────────────────────────────

info "Installing uv..."
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    success "uv installed"
else
    success "uv already installed"
fi

# ── Python dependencies ───────────────────────────────────────────────────────

info "Installing Python dependencies..."
cd "$ENGRAM_DIR"
uv sync --quiet
success "Python dependencies installed"

# ── .env file ─────────────────────────────────────────────────────────────────

if [[ ! -f "$ENGRAM_DIR/.env" ]]; then
    info "Creating .env from template..."
    cat > "$ENGRAM_DIR/.env" << 'EOF'
# ── LLM (Ollama — strictly local) ────────────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_EMBED_MODEL=nomic-embed-text

# ── Transcription (Groq Whisper for YouTube only) ─────────────────────────────
GROQ_API_KEY=
GROQ_WHISPER_MODEL=whisper-large-v3-turbo

# ── PostgreSQL + pgvector ─────────────────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=engram
POSTGRES_USER=engram
POSTGRES_PASSWORD=engram

# ── Obsidian Vault ────────────────────────────────────────────────────────────
VAULT_PATH=~/Documents/Engram-Vault

# ── Whisper (local — voice notes) ────────────────────────────────────────────
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE=512
CHUNK_OVERLAP=64
CHUNK_STRATEGY=recursive
EMBED_DIMS=768

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN=
GITHUB_USERNAME=
VAULT_REPO_URL=
VAULT_GITHUB_TOKEN=

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=

# ── Web Search (self-hosted SearXNG only) ────────────────────────────────────
SEARXNG_URL=

# ── Notifications (self-hosted ntfy) ─────────────────────────────────────────
NTFY_URL=
NTFY_TOPIC=

# ── Self-hosted connectors ────────────────────────────────────────────────────
NEXTCLOUD_URL=
NEXTCLOUD_USERNAME=
NEXTCLOUD_PASSWORD=
NEXTCLOUD_FOLDER=/
BOOKSTACK_URL=
BOOKSTACK_TOKEN_ID=
BOOKSTACK_TOKEN_SECRET=
EOF
    echo ""
    echo -e "${CYAN}  .env created. Fill in at minimum:${NC}"
    echo "    TELEGRAM_BOT_TOKEN"
    echo "    TELEGRAM_ALLOWED_USER_ID"
    echo ""
else
    info ".env already exists — updating OLLAMA_MODEL to llama3.2:3b for Pi..."
    sed -i 's/^OLLAMA_MODEL=.*/OLLAMA_MODEL=llama3.2:3b/' "$ENGRAM_DIR/.env"
    success ".env updated"
fi

# ── DB schema ─────────────────────────────────────────────────────────────────

info "Running DB schema setup..."
cd "$ENGRAM_DIR"
uv run python scripts/setup_db.py
uv run python -m interfaces.cli init
success "DB schema and vault ready"

# ── Systemd services ──────────────────────────────────────────────────────────

info "Creating systemd service: engram-telegram..."
sudo tee /etc/systemd/system/engram-telegram.service > /dev/null << EOF
[Unit]
Description=Engram Telegram Bot
After=network.target postgresql.service ollama.service
Wants=ollama.service

[Service]
Type=simple
User=${ENGRAM_USER}
WorkingDirectory=${ENGRAM_DIR}
ExecStart=$(which uv) run python -m interfaces.cli telegram
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

info "Creating systemd service: engram-web (disabled by default)..."
sudo tee /etc/systemd/system/engram-web.service > /dev/null << EOF
[Unit]
Description=Engram Web UI
After=network.target postgresql.service ollama.service
Wants=ollama.service

[Service]
Type=simple
User=${ENGRAM_USER}
WorkingDirectory=${ENGRAM_DIR}
ExecStart=$(which uv) run python -m interfaces.cli serve --port 8000
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable engram-telegram
success "engram-telegram enabled (starts on boot)"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}Setup complete!${NC}"
echo ""
echo "  Edit your config:       nano ${ENGRAM_DIR}/.env"
echo ""
echo "  Start the bot now:      sudo systemctl start engram-telegram"
echo "  Check bot logs:         journalctl -u engram-telegram -f"
echo ""
echo "  Enable web UI:          sudo systemctl enable --now engram-web"
echo "  Check web logs:         journalctl -u engram-web -f"
echo ""
echo -e "${CYAN}  Don't forget to fill in TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID in .env${NC}"
echo ""
