"""Tests for .env parsing, request headers and fail-fast validation."""

from __future__ import annotations

import os
import stat

import pytest

import config


def test_load_env_parses_values_and_skips_noise(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "KEY=value\n"
        'QUOTED="two words"\n'
        "SINGLE='x y'\n"
        "SPACED =  padded  \n"
        "EMPTY=\n"
        "NO_EQUALS\n"
        "=orphan\n",
        encoding="utf-8",
    )

    env = config.load_env(str(env_file))

    assert env["KEY"] == "value"
    assert env["QUOTED"] == "two words"
    assert env["SINGLE"] == "x y"
    assert env["SPACED"] == "padded"
    assert env["EMPTY"] == ""
    assert "NO_EQUALS" not in env
    assert "" not in env


def test_load_env_missing_file_is_empty(tmp_path):
    assert config.load_env(str(tmp_path / "does-not-exist")) == {}


def test_provider_headers_include_attribution(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(config, "HTTP_REFERER", "https://example.com")
    monkeypatch.setattr(config, "APP_TITLE", "Tutor Test")

    headers = config.provider_headers()

    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["Content-Type"] == "application/json"
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-Title"] == "Tutor Test"


def test_env_permission_warning_for_world_readable_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")
    os.chmod(env_file, 0o644)
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))

    warning = config.env_permission_warning()

    assert warning is not None
    assert "chmod 600" in warning


def test_env_permission_warning_quiet_for_private_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")
    os.chmod(env_file, stat.S_IRUSR | stat.S_IWUSR)
    monkeypatch.setattr(config, "ENV_FILE", str(env_file))

    assert config.env_permission_warning() is None


def test_env_permission_warning_quiet_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", str(tmp_path / "absent"))
    assert config.env_permission_warning() is None


def test_validate_config_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(config, "MODEL", "some/model")
    monkeypatch.setattr(config, "env_permission_warning", lambda: None)

    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
        config.validate_config()


def test_validate_config_rejects_missing_model(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(config, "MODEL", "")
    monkeypatch.setattr(config, "env_permission_warning", lambda: None)

    with pytest.raises(SystemExit, match="MODEL"):
        config.validate_config()


def test_validate_config_passes_with_required_values(monkeypatch, capsys):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(config, "MODEL", "some/model")
    monkeypatch.setattr(config, "env_permission_warning", lambda: "fix permissions")

    config.validate_config()

    assert "fix permissions" in capsys.readouterr().err


def test_default_env_file_prefers_override(tmp_path, monkeypatch):
    target = tmp_path / "custom.env"
    monkeypatch.setenv("PYTHON_TUTOR_ENV", str(target))

    assert config.default_env_file() == str(target)


def test_default_env_file_prefers_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHON_TUTOR_ENV", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")

    assert config.default_env_file() == str(tmp_path / ".env")


def test_default_env_file_falls_back_to_module_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHON_TUTOR_ENV", raising=False)
    monkeypatch.chdir(tmp_path)

    assert config.default_env_file() == os.path.join(config.PROJECT_DIR, ".env")
