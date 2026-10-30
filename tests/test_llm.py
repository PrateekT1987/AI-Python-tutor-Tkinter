"""Tests for streaming, retries, cancellation and context trimming."""

from __future__ import annotations

import json
import threading

import pytest
import requests

import llm


class FakeResponse:
    def __init__(self, status_code=200, lines=(), headers=None, text=""):
        self.status_code = status_code
        self._lines = lines
        self.headers = headers or {}
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            if isinstance(line, BaseException):
                raise line
            yield line


def sse(*deltas, finish=None):
    lines = []
    for index, delta in enumerate(deltas):
        choice = {"delta": {"content": delta}}
        if finish is not None and index == len(deltas) - 1:
            choice["finish_reason"] = finish
        lines.append("data: " + json.dumps({"choices": [choice]}))
    lines.append("data: [DONE]")
    return lines


@pytest.fixture
def no_sleep(monkeypatch):
    delays = []
    monkeypatch.setattr(llm, "_sleep_or_cancel", lambda delay, cancel: delays.append(delay))
    return delays


def install_post(monkeypatch, *responses):
    calls = []

    def post(*_args, **_kwargs):
        calls.append(1)
        if not responses:
            raise AssertionError("unexpected extra request")
        result = responses[0] if len(responses) == 1 else responses[len(calls) - 1]
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(llm.requests, "post", post)
    return calls


def test_stream_chat_yields_deltas(monkeypatch):
    install_post(monkeypatch, FakeResponse(lines=sse("Hel", "lo", finish="stop")))
    flag = {"truncated": False}

    text = "".join(llm.stream_chat([{"role": "user", "content": "hi"}], flag=flag))

    assert text == "Hello"
    assert flag["truncated"] is False


def test_stream_chat_sets_flag_on_length_finish(monkeypatch):
    install_post(monkeypatch, FakeResponse(lines=sse("cut", finish="length")))
    flag = {"truncated": False}

    list(llm.stream_chat([{"role": "user", "content": "hi"}], flag=flag))

    assert flag["truncated"] is True


def test_stream_chat_ignores_malformed_lines(monkeypatch):
    lines = [
        "",
        "event: ping",
        "data: not-json",
        'data: {"choices": []}',
        *sse("ok"),
    ]
    install_post(monkeypatch, FakeResponse(lines=lines))

    assert "".join(llm.stream_chat([{"role": "user", "content": "hi"}])) == "ok"


def test_stream_chat_retries_rate_limit(monkeypatch, no_sleep):
    calls = install_post(
        monkeypatch,
        FakeResponse(429, headers={"Retry-After": "2"}, text="slow down"),
        FakeResponse(lines=sse("ok")),
    )

    text = "".join(llm.stream_chat([{"role": "user", "content": "hi"}]))

    assert text == "ok"
    assert len(calls) == 2
    assert no_sleep and no_sleep[0] >= 2


def test_stream_chat_gives_up_after_max_retries(monkeypatch, no_sleep):
    monkeypatch.setattr(llm, "MAX_RETRIES", 1)
    calls = install_post(monkeypatch, FakeResponse(429))

    with pytest.raises(llm.RateLimitError):
        list(llm.stream_chat([{"role": "user", "content": "hi"}]))

    assert len(calls) == 2


def test_stream_chat_retries_network_errors(monkeypatch, no_sleep):
    calls = install_post(
        monkeypatch,
        requests.ConnectionError("boom"),
        FakeResponse(lines=sse("ok")),
    )

    text = "".join(llm.stream_chat([{"role": "user", "content": "hi"}]))

    assert text == "ok"
    assert len(calls) == 2


def test_stream_chat_raises_network_error_after_exhaustion(monkeypatch, no_sleep):
    monkeypatch.setattr(llm, "MAX_RETRIES", 1)
    install_post(monkeypatch, requests.ConnectionError("boom"))

    with pytest.raises(llm.NetworkError):
        list(llm.stream_chat([{"role": "user", "content": "hi"}]))


def test_stream_chat_does_not_retry_auth_failures(monkeypatch):
    calls = install_post(monkeypatch, FakeResponse(401, text="bad key"))

    with pytest.raises(llm.AuthError):
        list(llm.stream_chat([{"role": "user", "content": "hi"}]))

    assert len(calls) == 1


def test_stream_chat_reports_provider_errors(monkeypatch):
    install_post(monkeypatch, FakeResponse(400, text="bad request\nline two"))

    with pytest.raises(llm.ProviderError, match="bad request line two"):
        list(llm.stream_chat([{"role": "user", "content": "hi"}]))


def test_stream_chat_never_retries_after_partial_output(monkeypatch, no_sleep):
    calls = install_post(
        monkeypatch,
        FakeResponse(
            lines=[
                "data: " + json.dumps({"choices": [{"delta": {"content": "part"}}]}),
                requests.ConnectionError("dropped"),
            ]
        ),
    )

    with pytest.raises(llm.NetworkError):
        list(llm.stream_chat([{"role": "user", "content": "hi"}]))

    assert len(calls) == 1


def test_stream_chat_cancels_before_start(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    calls = install_post(monkeypatch, FakeResponse(lines=sse("never")))

    with pytest.raises(llm.Cancelled):
        list(llm.stream_chat([{"role": "user", "content": "hi"}], cancel=cancel))

    assert calls == []


def test_stream_chat_cancels_mid_stream(monkeypatch):
    cancel = threading.Event()

    def lines():
        yield "data: " + json.dumps({"choices": [{"delta": {"content": "one"}}]})
        cancel.set()
        yield "data: " + json.dumps({"choices": [{"delta": {"content": "two"}}]})

    install_post(monkeypatch, FakeResponse(lines=lines()))

    seen = []
    with pytest.raises(llm.Cancelled):
        for token in llm.stream_chat([{"role": "user", "content": "hi"}], cancel=cancel):
            seen.append(token)

    assert seen == ["one"]


def test_fit_messages_keeps_everything_under_budget():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]

    assert llm.fit_messages(messages, max_chars=1000) == messages


def test_fit_messages_drops_oldest_turns():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "a" * 400},
        {"role": "assistant", "content": "b" * 400},
        {"role": "user", "content": "newest"},
    ]

    fitted = llm.fit_messages(messages, max_chars=500)

    assert fitted[0] == {"role": "system", "content": "SYS"}
    assert fitted[-1] == {"role": "user", "content": "newest"}
    assert all(message != messages[1] for message in fitted)


def test_fit_messages_keeps_newest_even_when_oversized():
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "q" * 900},
    ]

    fitted = llm.fit_messages(messages, max_chars=300)

    assert fitted[-1]["role"] == "user"
    assert len(fitted[-1]["content"]) <= 300


def test_fit_messages_caps_a_giant_system_prompt():
    messages = [
        {"role": "system", "content": "s" * 900},
        {"role": "user", "content": "question"},
    ]

    fitted = llm.fit_messages(messages, max_chars=400)

    assert len(fitted[0]["content"]) == 200
    assert fitted[-1] == {"role": "user", "content": "question"}


def test_parse_retry_after():
    assert llm._parse_retry_after("2.5") == 2.5
    assert llm._parse_retry_after("-1") == 0.0
    assert llm._parse_retry_after("nonsense") == 0.0
    assert llm._parse_retry_after(None) == 0.0


def test_describe_error_is_short_and_single_line():
    assert llm.describe_error(llm.AuthError("bad key")) == "bad key"
    assert "network error" in llm.describe_error(requests.ConnectionError("x"))
    assert len(llm.describe_error(ValueError("x" * 500))) == 200
    assert "\n" not in llm.describe_error(ValueError("a\nb"))
