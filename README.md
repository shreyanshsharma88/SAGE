# SAGE

A fully local terminal AI assistant. Milestone 1–2: a Textual TUI task manager backed by
SQLite, with typed stubs for a local LLM agent loop (Ollama) and local web search (SearxNG)
landing in later sessions. No cloud calls anywhere.

## Setup

```
git clone <repo> && cd sage && ./bootstrap.sh
```

That single command installs Ollama, pulls the configured model, creates the virtualenv,
installs dependencies, runs migrations, and starts SearxNG if Docker is present. It is
idempotent — safe to re-run.

## Run

```
source .venv/bin/activate
python -m assistant.main
```

## Keybindings

- `c` — complete the selected task
- `d` — delete the selected task (asks for confirmation first)
- `enter` in the input bar — add a task to the active category

## Hardware target

Ubuntu 26.04, AMD Ryzen 5 5600H, NVIDIA GTX 1650 Mobile (4GB VRAM). The 4GB VRAM ceiling
means the LLM must be a 3–4B model resident fully on-GPU; the default is `phi4-mini`. The
model name is configurable in `src/assistant/config.py` (or the `SAGE_MODEL` env var).

## Configuration

All runtime configuration lives in `src/assistant/config.py`, overridable via environment
variables: `SAGE_MODEL`, `SAGE_OLLAMA_URL`, `SAGE_SEARXNG_URL`, `SAGE_DB_PATH`.
