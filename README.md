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

## Configuration

All runtime configuration lives in `src/assistant/config.py`, overridable via environment
variables: `SAGE_MODEL`, `SAGE_OLLAMA_URL`, `SAGE_SEARXNG_URL`, `SAGE_DB_PATH`.
