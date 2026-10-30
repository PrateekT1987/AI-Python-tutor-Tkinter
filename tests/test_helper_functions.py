"""Tests for the course-compatibility helpers in helper_functions.py."""

from __future__ import annotations

import builtins

import pytest
import requests

import helper_functions as helpers


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def skip_validation(monkeypatch):
    monkeypatch.setattr(helpers, "validate_config", lambda: None)


def install_post(monkeypatch, result):
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(helpers.requests, "post", post)
    return calls


def test_get_completion_returns_message(monkeypatch):
    calls = install_post(
        monkeypatch,
        FakeResponse(payload={"choices": [{"message": {"content": "hello"}}]}),
    )

    assert helpers.get_completion("hi", model="vendor/model") == "hello"
    assert calls[0]["json"]["model"] == "vendor/model"
    assert calls[0]["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert calls[0]["url"].endswith("/chat/completions")


def test_get_completion_from_messages_passes_history(monkeypatch):
    calls = install_post(
        monkeypatch,
        FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
    )
    messages = [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
    ]

    assert helpers.get_completion_from_messages(messages) == "ok"
    assert calls[0]["json"]["messages"] == messages


def test_aliases_delegate(monkeypatch):
    install_post(
        monkeypatch,
        FakeResponse(payload={"choices": [{"message": {"content": "alias"}}]}),
    )

    assert helpers.get_llm_response("hi") == "alias"
    assert helpers.get_response_from_llm([{"role": "user", "content": "hi"}]) == "alias"


def test_rate_limit_becomes_tutor_error(monkeypatch):
    install_post(monkeypatch, FakeResponse(429, text="slow down"))

    with pytest.raises(helpers.TutorError, match="429"):
        helpers.get_completion("hi")


def test_auth_failure_becomes_tutor_error(monkeypatch):
    install_post(monkeypatch, FakeResponse(401, text="nope"))

    with pytest.raises(helpers.TutorError, match="OPENROUTER_API_KEY"):
        helpers.get_completion("hi")


def test_server_error_includes_detail(monkeypatch):
    install_post(monkeypatch, FakeResponse(500, text="upstream exploded\nboom"))

    with pytest.raises(helpers.TutorError, match="upstream exploded boom"):
        helpers.get_completion("hi")


def test_network_failure_becomes_tutor_error(monkeypatch):
    install_post(monkeypatch, requests.ConnectionError("no route"))

    with pytest.raises(helpers.TutorError, match="Could not reach OpenRouter"):
        helpers.get_completion("hi")


def test_unexpected_shape_becomes_tutor_error(monkeypatch):
    install_post(monkeypatch, FakeResponse(payload={"unexpected": True}))

    with pytest.raises(helpers.TutorError, match="Unexpected response shape"):
        helpers.get_completion("hi")


def test_display_table_falls_back_without_pandas(monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pandas":
            raise ImportError("no pandas")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    helpers.display_table([{"a": 1}, {"a": 2}])

    printed = capsys.readouterr().out
    assert "{'a': 1}" in printed
    assert "{'a': 2}" in printed
