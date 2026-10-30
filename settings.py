"""Local settings and session persistence.

Files live under XDG directories and are written atomically with mode 0600.
Only the model id, generation knobs, window geometry and chat text are stored;
API keys are never written here.
"""

from __future__ import annotations

import json
import os
import tempfile

APP_NAME = "python-tutor"

DEFAULT_SETTINGS = {
    "level": "Intermediate",
    "model": "",
    "temperature": 0.4,
    "max_tokens": 2000,
    "geometry": "",
}


def _app_dir(env_var: str, default: str) -> str:
    base = os.environ.get(env_var) or os.path.expanduser(default)
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_dir() -> str:
    return _app_dir("XDG_CONFIG_HOME", "~/.config")


def data_dir() -> str:
    return _app_dir("XDG_DATA_HOME", "~/.local/share")


def settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def session_path() -> str:
    return os.path.join(data_dir(), "session.json")


def _read(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, type(default)) else default
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: str, data) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def load_settings() -> dict:
    stored = _read(settings_path(), {})
    data = {**DEFAULT_SETTINGS, **stored}
    if data.get("level") not in ("Beginner", "Intermediate", "Advanced"):
        data["level"] = DEFAULT_SETTINGS["level"]
    if not isinstance(data.get("model"), str):
        data["model"] = ""
    try:
        data["temperature"] = float(data.get("temperature"))
    except (TypeError, ValueError):
        data["temperature"] = DEFAULT_SETTINGS["temperature"]
    try:
        data["max_tokens"] = int(data.get("max_tokens"))
    except (TypeError, ValueError):
        data["max_tokens"] = DEFAULT_SETTINGS["max_tokens"]
    if not isinstance(data.get("geometry"), str):
        data["geometry"] = ""
    return data


def save_settings(settings: dict) -> None:
    _write(settings_path(), settings)


def load_session() -> list[dict]:
    data = _read(session_path(), {})
    history = data.get("history") if isinstance(data, dict) else None
    if not isinstance(history, list):
        return []
    cleaned = []
    for message in history:
        if (
            isinstance(message, dict)
            and message.get("role") in ("user", "assistant")
            and isinstance(message.get("content"), str)
        ):
            cleaned.append({"role": message["role"], "content": message["content"]})
    return cleaned


def save_session(history: list[dict]) -> None:
    _write(session_path(), {"history": history})


def clear_session() -> None:
    try:
        os.unlink(session_path())
    except OSError:
        pass
