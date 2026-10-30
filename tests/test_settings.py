"""Tests for local settings/session persistence (XDG, mode 0600)."""

from __future__ import annotations

import json
import os
import stat

import pytest

import settings


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


def test_defaults_when_nothing_saved():
    loaded = settings.load_settings()

    assert loaded["level"] == "Intermediate"
    assert loaded["model"] == ""
    assert loaded["temperature"] == 0.4
    assert loaded["max_tokens"] == 2000
    assert loaded["geometry"] == ""


def test_settings_round_trip_is_private():
    data = settings.load_settings()
    data.update(level="Advanced", model="vendor/model", temperature=0.9,
                max_tokens=1234, geometry="900x700+10+10")
    settings.save_settings(data)

    path = settings.settings_path()
    assert os.path.exists(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert settings.load_settings() == data


def test_invalid_values_fall_back_to_defaults():
    os.makedirs(os.path.dirname(settings.settings_path()), exist_ok=True)
    with open(settings.settings_path(), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "level": "Wizard",
                "model": 42,
                "temperature": "hot",
                "max_tokens": "many",
                "geometry": ["bad"],
            },
            handle,
        )

    loaded = settings.load_settings()

    assert loaded == settings.DEFAULT_SETTINGS


def test_unreadable_json_falls_back_to_defaults():
    os.makedirs(os.path.dirname(settings.settings_path()), exist_ok=True)
    with open(settings.settings_path(), "w", encoding="utf-8") as handle:
        handle.write("{not json")

    assert settings.load_settings() == settings.DEFAULT_SETTINGS


def test_wrong_toplevel_type_falls_back_to_defaults():
    os.makedirs(os.path.dirname(settings.settings_path()), exist_ok=True)
    with open(settings.settings_path(), "w", encoding="utf-8") as handle:
        json.dump(["not", "a", "dict"], handle)

    assert settings.load_settings() == settings.DEFAULT_SETTINGS


def test_session_round_trip_filters_bad_entries():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "system", "content": "drop me"},
        {"role": "user", "content": 7},
        "not a dict",
    ]
    settings.save_session(history)

    assert settings.load_session() == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_missing_session_is_empty():
    assert settings.load_session() == []


def test_clear_session_is_idempotent():
    settings.save_session([{"role": "user", "content": "hi"}])

    settings.clear_session()
    settings.clear_session()

    assert settings.load_session() == []


def test_save_leaves_no_temp_files():
    settings.save_settings(settings.load_settings())

    leftovers = [
        name
        for name in os.listdir(os.path.dirname(settings.settings_path()))
        if name.startswith(".tmp-")
    ]
    assert leftovers == []
