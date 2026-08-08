#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

info()  { printf '\033[1;34m[sage]\033[0m %s\n' "$1"; }
warn()  { printf '\033[1;33m[sage][warn]\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m[sage]\033[0m %s\n' "$1"; }

resolve_model() {
    if [ -n "${SAGE_MODEL:-}" ]; then
        printf '%s' "$SAGE_MODEL"
        return
    fi
    local from_config
    from_config="$(grep -E '^DEFAULT_MODEL' src/assistant/config.py 2>/dev/null | sed -E 's/.*"([^"]+)".*/\1/' || true)"
    if [ -n "$from_config" ]; then
        printf '%s' "$from_config"
    else
        printf 'phi4-mini'
    fi
}

MODEL="$(resolve_model)"
info "Configured model: $MODEL"

info "Step 1/8: checking operating system"
if [ -r /etc/os-release ]; then
    . /etc/os-release
    if printf '%s' "${ID:-}${ID_LIKE:-}" | grep -qi ubuntu; then
        ok "Ubuntu detected (${PRETTY_NAME:-unknown})"
    else
        warn "Non-Ubuntu OS detected (${PRETTY_NAME:-unknown}); continuing anyway"
    fi
else
    warn "Cannot read /etc/os-release; assuming a non-Ubuntu system and continuing"
fi

info "Step 2/8: checking for ollama"
if command -v ollama >/dev/null 2>&1; then
    ok "ollama already installed"
else
    info "ollama not found; installing"
    curl -fsSL https://ollama.com/install.sh | sh
    ok "ollama installed"
fi

info "Step 3/8: ensuring model '$MODEL' is present"
if command -v ollama >/dev/null 2>&1; then
    if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then
        ok "model '$MODEL' already pulled"
    else
        info "pulling model '$MODEL' (this can take a while)"
        ollama pull "$MODEL"
        ok "model '$MODEL' pulled"
    fi
else
    warn "ollama unavailable; skipping model pull"
fi

info "Step 4/8: checking GPU"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    ok "nvidia-smi works; GPU inference available"
else
    warn "nvidia-smi not working; inference will run on CPU and be slower. Continuing."
fi

info "Step 5/8: setting up virtualenv"
if [ -d .venv ]; then
    ok "existing .venv found; leaving it in place"
else
    python3 -m venv .venv
    ok "created .venv"
fi
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt
pip install -e .
ok "dependencies installed"

info "Step 6/8: running database migrations"
python -m assistant.db.migrations
ok "database ready"

info "Step 7/8: starting SearxNG (optional)"
if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        docker compose up -d
        ok "SearxNG started via docker compose"
    else
        warn "'docker compose' plugin not available; skipping SearxNG. Web search will not work yet."
    fi
else
    warn "docker not found; skipping SearxNG. Web search will not work yet."
fi

info "Step 8/8: done"
ok "Setup complete. Run the app with:"
printf '\n    source .venv/bin/activate && python -m assistant.main\n\n'
