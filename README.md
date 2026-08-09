# SAGE

A fully local terminal AI assistant: a Textual TUI task manager backed by SQLite, a streaming
Ollama agent loop with tool-calling, local web search via self-hosted SearxNG, recurring
tasks, a knowledge Notes tab, desktop reminders fired by a background `systemd --user`
daemon, and an always-listening local voice interface (wake word in, streamed speech out).
No cloud calls anywhere.

## Setup

```
git clone <repo> && cd sage && ./bootstrap.sh
```

That single command installs Ollama, pulls the configured model, creates the virtualenv,
installs dependencies, runs migrations, starts SearxNG if Docker is present, downloads the
voice models (Piper voice + openWakeWord), and installs both the reminder daemon and the
always-listening voice service as `systemd --user` units. It is idempotent — safe to re-run.

`sudo` is used in exactly two one-time, guarded places: `loginctl enable-linger` (so the
services survive logouts/reboots, skipped if already enabled) and `apt-get install
libportaudio2` (the PortAudio runtime for the microphone, skipped if already installed).
bootstrap.sh states the linger step explicitly
before prompting, and skips it silently if linger is already enabled.

## Update / deploy

To pull a new version and apply it in place:

```
git pull && ./bootstrap.sh
```

Re-running bootstrap.sh updates the venv, database, and systemd unit in place — it never
wipes an existing virtualenv or database, never duplicates the unit, and won't re-prompt for
sudo if linger is already enabled.

## Reminders and the background daemon

Reminders are fired by `check_and_fire_reminders()` in `src/assistant/reminders.py`. Two
processes call it:

- The TUI, on a 60-second interval, while it is open.
- The standalone daemon (`python -m assistant.daemon`), always, via the
  `assistant-daemon` `systemd --user` service — no terminal needed.

Both mark `tasks.reminded_at` on fire, so a reminder is delivered exactly once regardless of
which process gets there first. Check the daemon with:

```
systemctl --user status assistant-daemon
```

## Voice

The voice interface is the primary way to use SAGE on the target machine. It runs headless as
a `systemd --user` service (`assistant-voice`), so after setup you never need a terminal:

- Say the wake word (`hey jarvis`) — a short beep confirms, then it listens, transcribes with
  `faster-whisper` (CPU/int8), thinks with the agent loop, and speaks the reply through
  `piper-tts`, sentence by sentence as they generate.
- Say the wake word again mid-response to interrupt: it cancels the in-flight Ollama stream
  (closing the connection so the GPU stops), stops speaking within about a sentence, and starts
  listening for the new command. A single shared microphone stream feeds both the wake-word
  detector and the recorder — the mic is never opened and closed per turn.
- Deletes are confirmed by voice ("Delete the task X? Say yes or no.").

Run it manually for tuning (Enter also works as an interrupt when a terminal is attached):

```
python -m assistant.voice
```

Check the service:

```
systemctl --user status assistant-voice
```

**Known limitation — no acoustic echo cancellation.** The wake-word detector stays active
during playback with no AEC, so at higher speaker volume the assistant can occasionally
false-trigger on its own voice. An external or headset mic avoids this entirely. Fixing it with
real AEC is deferred unless in-room testing shows it is a practical problem.

## Run the TUI

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
variables: `SAGE_MODEL`, `SAGE_OLLAMA_URL`, `SAGE_SEARXNG_URL`, `SAGE_DB_PATH`,
`SAGE_WHISPER_MODEL` (default `base.en`), and `SAGE_PIPER_VOICE` (path to the Piper `.onnx`).
