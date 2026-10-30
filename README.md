# AI_ChatBot — Python Tutor Console

An interactive, REPL-style Python tutoring chat. Ask anything about Python — it
responds with explanations, runnable code examples, and a follow-up question to keep
the lesson moving.

The project talks to **OpenRouter only**. One API key, one model id from `.env`,
no provider fallback chain.

- **Desktop app** — pure-Python Tkinter GUI (`python_tutor_gui.py`), recommended.
- **Browser app** — React + Vite console, served in production by `server.py`.

## Features (desktop app)

- Beginner / Intermediate / Advanced difficulty levels with tailored prompts
- Streaming responses from the model configured in `.env`
- **Stop** button and cooperative cancellation mid-answer
- Automatic retries with exponential backoff for 429/5xx/network errors
- Settings dialog for model, temperature and max tokens
- Chat history, difficulty and window geometry restored on launch; transcript export
- **Run any code block** the tutor writes: a "run this code" button executes it in a
  sandbox (bubblewrap when available: read-only filesystem, no network, CPU/memory
  limits), with stdin closed and output truncated
- **Sandbox** toggle in the header: a free-form scratchpad to write and run your own code,
  auto-saved to `scratchpad.py`
- **Auto-continue**: if an answer is cut off at the model's output limit, the app
  automatically asks the model to finish it (up to 2 extra rounds) instead of leaving a
  truncated answer

## Configuration

All settings live in `.env` (git-ignored). Copy the template:

```bash
cp .env.example .env
```

| Variable | Required | Description |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | yes | Key from <https://openrouter.ai/keys> |
| `MODEL` | yes | OpenRouter model id, e.g. `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `OPENROUTER_BASE_URL` | no | Defaults to `https://openrouter.ai/api/v1` |
| `MAX_TOKENS` | no | Completion cap, defaults to `2000` |
| `OPENROUTER_HTTP_REFERER` | no | Attribution header shown on OpenRouter |
| `OPENROUTER_APP_TITLE` | no | Attribution header shown on OpenRouter |
| `TUTOR_MEMORY_MB` | no | Sandbox memory cap, defaults to `512` |
| `TUTOR_ALLOW_NETWORK` | no | Set to `1` to let snippets reach the network |
| `LLM_MAX_RETRIES` | no | Retry attempts for 429/5xx/network errors, defaults to `3` |
| `LLM_RETRY_BASE_SECONDS` | no | Backoff base in seconds, defaults to `0.8` |
| `LLM_TIMEOUT_SECONDS` | no | Streaming read timeout, defaults to `60` |
| `MAX_CONTEXT_CHARS` | no | Char budget before old turns are trimmed, defaults to `24000` |
| `PYTHON_TUTOR_ENV` | no | Path to a different `.env`; defaults to `./.env` |

The app fails fast with a clear message if `OPENROUTER_API_KEY` or `MODEL` is missing.
Environment variables override values from `.env`. The file is looked up in the
current working directory first, then next to the source, so an installed copy
still finds the `.env` of the project you launch it from.

### Saved state

The desktop app restores your level, model, temperature, window geometry and chat
on launch. Files are written atomically with mode `0600`:

- Settings — `$XDG_CONFIG_HOME/python-tutor/settings.json` (or `~/.config/...`)
- Session — `$XDG_DATA_HOME/python-tutor/session.json` (or `~/.local/share/...`)

Use **File → New session** to clear them, and **File → Export transcript…** to save
the conversation as Markdown. API keys are never written to these files.

## Getting started — desktop app

Requirements: Python 3.10+, tkinter, `requests`.

```bash
sudo apt install python3-tk     # Ubuntu/Debian (others: python3-tk equivalent)
python3 -m pip install -r requirements.txt
./run_tutor.sh                  # checks deps and launches the GUI
```

Or install it as a command (adds a `python-tutor` launcher):

```bash
python3 -m pip install -e .     # or: pip install . once published
python-tutor
```

Or run the entry point directly:

```bash
python3 python_tutor_gui.py
```

Check your configuration without starting the UI:

```bash
python3 config.py
```

## Getting started — browser app

Development (Vite proxies `/api/openrouter` with the server-side key):

```bash
npm install
npm run dev
```

Production (build the bundle, then serve it with the Python proxy):

```bash
npm run build
python3 server.py               # http://127.0.0.1:8000
```

`server.py` serves `dist/` and proxies `/api/openrouter/*` to OpenRouter, so the
API key never reaches the browser. Set `HOST` and `PORT` to change the bind
address. Put it behind a TLS-terminating reverse proxy for a real deployment.
Installed as a package, the same server is available as `python-tutor-server`.

## Development

```bash
python3 -m pip install -e '.[dev]'   # or: pip install -r requirements-dev.txt
python3 -m pytest                    # 93 tests, no network or API key needed
```

The suite covers configuration, the fence parser, streaming/retries/cancellation,
context trimming, settings persistence, the sandbox, the HTTP server and the Tk
UI (the UI tests skip automatically when no display is available).

CI (`.github/workflows/ci.yml`) runs the tests on Python 3.10, 3.12 and 3.13
under Xvfb, byte-compiles the modules, checks `run_tutor.sh`, and lints/builds
the browser console.

## Project layout

```
python_tutor_gui.py   thin entry point
config.py             .env loading, OpenRouter settings, validation
prompts.py            system prompt, levels, starters
content.py            text / fenced-code parsing
llm.py                streaming client: retries, cancellation, context trimming
sandbox.py            isolated snippet execution
settings.py           settings + saved session (XDG, mode 0600)
ui/                   theme, highlighting, main window, sandbox, settings dialog
server.py             browser-app production server
tests/                pytest suite (no network or API key required)
pyproject.toml        packaging: deps, entry points, pytest config
requirements*.txt     runtime and development dependency lists
.github/workflows/    CI
```

## Scripts

```bash
./run_tutor.sh    # desktop app launcher
python3 server.py # browser app production server
python3 -m pytest # test suite
npm run dev       # browser dev server
npm run build     # production build
npm run lint      # oxlint
```

## Security note

`run this code` and the Sandbox execute snippets through `sandbox.py`, which
applies the strongest isolation available:

1. **bubblewrap** (`bwrap`) — read-only filesystem outside a temp dir, private
   `/tmp`, no network, cleared environment, no capabilities, PID/IPC/UTS
   namespaces.
2. **`unshare -Urn`** — private network namespace when user namespaces work.
3. **rlimits only** — if neither is available, the snippet *can* reach the
   network; the UI says so before running.

Every layer caps CPU time, address space (512 MB by default, `TUTOR_MEMORY_MB`),
file writes (10 MB), open files, and core dumps. Every model-generated snippet
is confirmed before it runs, because model output is treated as untrusted.

The Sandbox is network-isolated by default. Set `TUTOR_ALLOW_NETWORK=1` only
when a lesson needs to call an API; the UI then labels the runner
`network enabled (opt-in)`.
