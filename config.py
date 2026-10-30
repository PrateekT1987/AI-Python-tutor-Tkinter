"""Configuration for the Python tutor (OpenRouter only).

Single source of truth for .env loading, provider settings and validation.
The desktop app (`python_tutor_gui.py`) and the course helpers
(`helper_functions.py`) both import from here.

Required .env values:
    OPENROUTER_API_KEY   -- https://openrouter.ai/keys
    MODEL                -- an OpenRouter model id (e.g. "nvidia/...:free")

Optional .env values:
    OPENROUTER_BASE_URL  -- defaults to https://openrouter.ai/api/v1
    MAX_TOKENS           -- completion cap, defaults to 2000
    OPENROUTER_HTTP_REFERER / OPENROUTER_APP_TITLE
                         -- attribution headers shown on OpenRouter
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def default_env_file() -> str:
    """Resolve the .env to load.

    Priority: ``PYTHON_TUTOR_ENV``, then ``./.env`` (so an installed copy picks
    up the project you launched it from), then ``.env`` next to this module.
    """
    override = os.environ.get("PYTHON_TUTOR_ENV")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    local = os.path.abspath(".env")
    if os.path.isfile(local):
        return local
    return os.path.join(PROJECT_DIR, ".env")


ENV_FILE = default_env_file()

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MAX_TOKENS = 2000
DEFAULT_REFERER = "https://github.com/prateekt87/python-tutor"
DEFAULT_TITLE = "Python Tutor"

# Keys read from the shell, overriding .env when present.
_ENV_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_HTTP_REFERER",
    "OPENROUTER_APP_TITLE",
    "MODEL",
    "MAX_TOKENS",
    "TUTOR_MEMORY_MB",
    "TUTOR_ALLOW_NETWORK",
    "LLM_MAX_RETRIES",
    "LLM_RETRY_BASE_SECONDS",
    "LLM_TIMEOUT_SECONDS",
    "MAX_CONTEXT_CHARS",
)


def load_env(path: str = ENV_FILE) -> dict[str, str]:
    """Read KEY=VALUE lines from `path`; ignore blanks, comments and malformed lines."""
    env: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if not key:
                    continue
                env[key] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


ENV: dict[str, str] = load_env()
for _key in _ENV_KEYS:
    if os.environ.get(_key):
        ENV[_key] = os.environ[_key]


def _get(key: str, default: str = "") -> str:
    return (ENV.get(key) or default).strip()


OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = _get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
MODEL = _get("MODEL")
HTTP_REFERER = _get("OPENROUTER_HTTP_REFERER", DEFAULT_REFERER)
APP_TITLE = _get("OPENROUTER_APP_TITLE", DEFAULT_TITLE)

try:
    MAX_TOKENS = int(_get("MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
except ValueError:
    MAX_TOKENS = DEFAULT_MAX_TOKENS

CHAT_COMPLETIONS_URL = f"{OPENROUTER_BASE_URL}/chat/completions"


def provider_headers() -> dict[str, str]:
    """Headers for an OpenRouter request, including attribution."""
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": HTTP_REFERER,
        "X-Title": APP_TITLE,
    }


def env_permission_warning() -> str | None:
    """Return a warning when .env is readable by group/others, else None."""
    if not os.path.exists(ENV_FILE):
        return None
    mode = os.stat(ENV_FILE).st_mode & 0o777
    if mode & 0o077:
        return (
            f"{ENV_FILE} is accessible by other users (mode {mode:o}). "
            "Run: chmod 600 .env"
        )
    return None


def validate_config() -> None:
    """Fail fast with an actionable message when required settings are missing."""
    warning = env_permission_warning()
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    missing = []
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if not MODEL:
        missing.append("MODEL")
    if missing:
        raise SystemExit(
            "Missing required environment setting(s): "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill them in, or export them in your shell."
        )


if __name__ == "__main__":
    validate_config()
    print(f"base_url : {OPENROUTER_BASE_URL}")
    print(f"model    : {MODEL}")
    print(f"max_tokens: {MAX_TOKENS}")
    print(f"api key  : {'set' if OPENROUTER_API_KEY else 'MISSING'}")
