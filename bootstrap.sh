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

info "Step 1/11: checking operating system"
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

info "Step 2/11: checking for ollama"
if command -v ollama >/dev/null 2>&1; then
    ok "ollama already installed"
else
    info "ollama not found; installing"
    curl -fsSL https://ollama.com/install.sh | sh
    ok "ollama installed"
fi

info "Step 3/11: ensuring model '$MODEL' is present"
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

info "Step 4/11: checking GPU"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    ok "nvidia-smi works; GPU inference available"
else
    warn "nvidia-smi not working; inference will run on CPU and be slower. Continuing."
fi

info "Step 5/11: setting up virtualenv"
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

info "Step 6/11: running database migrations"
python -m assistant.db.migrations
ok "database ready"

info "Step 7/11: starting SearxNG (optional)"
if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        if docker compose up -d; then
            ok "SearxNG started via docker compose"
        else
            warn "docker compose up failed (is the Docker daemon running?); skipping SearxNG. Web search will not work yet."
        fi
    else
        warn "'docker compose' plugin not available; skipping SearxNG. Web search will not work yet."
    fi
else
    warn "docker not found; skipping SearxNG. Web search will not work yet."
fi

info "Step 8/11: installing voice assets (PortAudio, Piper voice, wake-word models)"
if command -v apt-get >/dev/null 2>&1; then
    if dpkg -s libportaudio2 >/dev/null 2>&1; then
        ok "libportaudio2 already installed"
    else
        info "installing libportaudio2 (needed by sounddevice)"
        if sudo apt-get install -y libportaudio2; then
            ok "libportaudio2 installed"
        else
            warn "libportaudio2 install failed; microphone audio may not work until it is installed."
        fi
    fi
else
    warn "apt-get not found; ensure a PortAudio runtime is installed for microphone support."
fi

PIPER_VOICE="${SAGE_PIPER_VOICE_NAME:-en_US-amy-medium}"
PIPER_QUALITY="medium"
PIPER_LANG_DIR="en/en_US/amy/${PIPER_QUALITY}"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/${PIPER_LANG_DIR}"
mkdir -p models
for suffix in onnx onnx.json; do
    target="models/${PIPER_VOICE}.${suffix}"
    if [ -f "$target" ]; then
        ok "Piper voice asset already present: $target"
    else
        info "downloading $target"
        if curl -fsSL -o "$target" "${PIPER_BASE}/${PIPER_VOICE}.${suffix}"; then
            ok "downloaded $target"
        else
            rm -f "$target"
            warn "failed to download $target; voice output will not work until it is present."
        fi
    fi
done

info "ensuring openWakeWord models are downloaded"
if python - <<'PY'
import openwakeword.utils
openwakeword.utils.download_models()
print("openWakeWord models ready")
PY
then
    ok "openWakeWord models ready"
else
    warn "openWakeWord model download failed; wake-word detection will not work until it succeeds."
fi

info "Step 9/11: installing background reminder daemon (systemd --user)"
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    UNIT_DIR="$HOME/.config/systemd/user"
    UNIT_PATH="$UNIT_DIR/assistant-daemon.service"
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_PATH" <<EOF
[Unit]
Description=jarvis-assistant background reminder daemon
After=default.target

[Service]
ExecStart=$VENV_PYTHON -m assistant.daemon
Restart=on-failure
RestartSec=5
WorkingDirectory=$SCRIPT_DIR

[Install]
WantedBy=default.target
EOF
    ok "wrote $UNIT_PATH"
    systemctl --user daemon-reload || true
    if systemctl --user enable --now assistant-daemon; then
        ok "assistant-daemon enabled and started"
    else
        warn "could not enable assistant-daemon; reminders still fire while the TUI is open."
    fi

    if loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
        ok "linger already enabled for $USER; skipping sudo"
    else
        warn "Enabling linger needs sudo (the only sudo here besides the one-time apt package install)."
        info "Linger lets the reminder and voice services keep running across logouts and reboots"
        info "without an active login session. You will be prompted for your password once."
        sudo loginctl enable-linger "$USER"
        ok "linger enabled for $USER"
    fi

    info "Daemon status:"
    systemctl --user status assistant-daemon --no-pager || true
else
    warn "systemd --user not available; skipping background daemon install."
    warn "Reminders will still fire whenever the TUI is open."
fi

info "Step 10/11: installing always-listening voice service (systemd --user)"
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    UNIT_DIR="$HOME/.config/systemd/user"
    VOICE_UNIT_PATH="$UNIT_DIR/assistant-voice.service"
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
    mkdir -p "$UNIT_DIR"
    cat > "$VOICE_UNIT_PATH" <<EOF
[Unit]
Description=jarvis-assistant always-listening voice service
After=default.target

[Service]
ExecStart=$VENV_PYTHON -m assistant.voice
Restart=on-failure
RestartSec=5
WorkingDirectory=$SCRIPT_DIR

[Install]
WantedBy=default.target
EOF
    ok "wrote $VOICE_UNIT_PATH"
    systemctl --user daemon-reload || true
    if systemctl --user enable --now assistant-voice; then
        ok "assistant-voice enabled and started"
    else
        warn "could not enable assistant-voice; run it manually with: python -m assistant.voice"
    fi
    info "Voice service status:"
    systemctl --user status assistant-voice --no-pager || true
else
    warn "systemd --user not available; skipping voice service install."
    warn "Run the voice loop manually with: python -m assistant.voice"
fi

info "Step 11/11: done"
ok "Setup complete. Run the app with:"
printf '\n    source .venv/bin/activate && python -m assistant.main\n\n'
ok "Background services: systemctl --user status assistant-daemon assistant-voice"
