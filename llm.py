"""OpenRouter streaming client.

Adds the reliability behavior the GUI needs: typed errors, retry with
exponential backoff for 429/5xx/network failures (only before any token has
been shown), cooperative cancellation, and context-window trimming.
"""

from __future__ import annotations

import json
import random
import time
from typing import Iterator

import requests

from config import CHAT_COMPLETIONS_URL, ENV, MAX_TOKENS, MODEL, provider_headers


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(ENV.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(str(ENV.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


MAX_RETRIES = max(0, _int_env("LLM_MAX_RETRIES", 3))
RETRY_BASE_SECONDS = max(0.0, _float_env("LLM_RETRY_BASE_SECONDS", 0.8))
REQUEST_TIMEOUT = max(1.0, _float_env("LLM_TIMEOUT_SECONDS", 60.0))
MAX_CONTEXT_CHARS = max(1000, _int_env("MAX_CONTEXT_CHARS", 24000))


class TutorError(RuntimeError):
    """Base class for errors that can be shown to the learner."""


class AuthError(TutorError):
    pass


class RateLimitError(TutorError):
    pass


class NetworkError(TutorError):
    pass


class ProviderError(TutorError):
    pass


class Cancelled(TutorError):
    pass


class _Retryable(Exception):
    def __init__(self, message: str, *, retry_after: float = 0.0, kind: str = "server"):
        super().__init__(message)
        self.retry_after = retry_after
        self.kind = kind


def describe_error(exc: BaseException) -> str:
    """One short, actionable line for the status area."""
    if isinstance(exc, TutorError):
        return str(exc)[:200]
    if isinstance(exc, requests.RequestException):
        return f"network error: {exc}"[:200]
    return (str(exc).strip().replace("\n", " ") or exc.__class__.__name__)[:200]


def _parse_retry_after(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        return 0.0


def _sleep_or_cancel(delay: float, cancel) -> None:
    deadline = time.monotonic() + delay
    while True:
        if cancel is not None and cancel.is_set():
            raise Cancelled("stopped")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


def _iter_sse(resp, flag, cancel) -> Iterator[str]:
    for raw in resp.iter_lines(decode_unicode=True):
        if cancel is not None and cancel.is_set():
            raise Cancelled("stopped")
        if not raw:
            continue
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        try:
            choice = chunk["choices"][0]
        except (KeyError, IndexError, TypeError):
            continue
        if flag is not None and choice.get("finish_reason") == "length":
            flag["truncated"] = True
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if content:
            yield content


def stream_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    flag: dict | None = None,
    cancel=None,
) -> Iterator[str]:
    """Yield text deltas for a streamed chat completion.

    Retries 429/5xx/network failures with jittered exponential backoff, but
    never after the first token has been yielded (that would duplicate text).
    Set ``cancel`` (a ``threading.Event``) to stop cooperatively.
    """
    payload = {
        "model": model or MODEL,
        "stream": True,
        "messages": messages,
        "max_tokens": max_tokens if max_tokens is not None else MAX_TOKENS,
    }
    if temperature is not None:
        payload["temperature"] = float(temperature)

    attempt = 0
    while True:
        if cancel is not None and cancel.is_set():
            raise Cancelled("stopped")

        yielded = False
        try:
            with requests.post(
                CHAT_COMPLETIONS_URL,
                json=payload,
                headers=provider_headers(),
                stream=True,
                timeout=(10, REQUEST_TIMEOUT),
            ) as resp:
                status = resp.status_code
                if status in (401, 403):
                    raise AuthError("authentication failed - check OPENROUTER_API_KEY")
                if status == 429:
                    raise _Retryable(
                        "rate limited",
                        retry_after=_parse_retry_after(resp.headers.get("Retry-After")),
                        kind="rate",
                    )
                if status >= 500:
                    raise _Retryable(f"OpenRouter returned HTTP {status}")
                if status >= 400:
                    detail = resp.text.strip().replace("\n", " ")[:160]
                    raise ProviderError(f"OpenRouter returned HTTP {status}: {detail}")

                for piece in _iter_sse(resp, flag, cancel):
                    yielded = True
                    yield piece
            return

        except Cancelled:
            raise
        except TutorError:
            raise
        except _Retryable as exc:
            if yielded or attempt >= MAX_RETRIES:
                if exc.kind == "rate":
                    raise RateLimitError(
                        "rate limited by OpenRouter - wait a moment and retry"
                    ) from exc
                raise ProviderError(
                    "OpenRouter is having trouble - try again shortly"
                ) from exc
            delay = min(RETRY_BASE_SECONDS * (2 ** attempt), 10.0)
            delay = max(delay, exc.retry_after) + random.uniform(0, 0.3)
            _sleep_or_cancel(delay, cancel)
            attempt += 1

        except requests.RequestException as exc:
            if yielded or attempt >= MAX_RETRIES:
                raise NetworkError(f"network error: {exc}") from exc
            delay = min(RETRY_BASE_SECONDS * (2 ** attempt), 10.0)
            _sleep_or_cancel(delay + random.uniform(0, 0.3), cancel)
            attempt += 1


def fit_messages(messages: list[dict], max_chars: int | None = None) -> list[dict]:
    """Trim the oldest turns so the request fits a char-based context budget.

    The system prompt is always kept. The newest turn is kept even when it alone
    exceeds the budget, truncated to fit.
    """
    limit = max_chars if max_chars is not None else MAX_CONTEXT_CHARS
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    def size(items: list[dict]) -> int:
        return sum(len(str(m.get("content", ""))) for m in items)

    # Never let the system prompt consume the whole budget: reserve at least
    # half of it for the conversation.
    if size(system) > limit // 2:
        system = [dict(system[0])]
        system[0]["content"] = str(system[0].get("content", ""))[: limit // 2]

    if size(system) + size(rest) <= limit:
        return list(system) + list(rest)

    total = size(system)
    kept: list[dict] = []
    for message in reversed(rest):
        content = str(message.get("content", ""))
        if kept and total + len(content) > limit:
            break
        if not kept and total + len(content) > limit:
            allowed = max(0, limit - total)
            message = {**message, "content": content[:allowed]}
            content = message["content"]
        kept.append(message)
        total += len(content)

    kept.reverse()
    return list(system) + kept
