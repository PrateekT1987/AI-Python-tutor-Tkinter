"""Course helpers wired to OpenRouter.

These are the notebook helpers used by the LLM course, kept as a light
compatibility layer over the same provider and model as the desktop tutor.
Configuration comes from `.env` via `config.py` (OPENROUTER_API_KEY,
OPENROUTER_BASE_URL, MODEL).

Not a pip package: keep this file next to your scripts and
`from helper_functions import get_completion` will just work.
"""

from __future__ import annotations

import requests

from config import (
    CHAT_COMPLETIONS_URL,
    MAX_TOKENS,
    MODEL,
    OPENROUTER_API_KEY,
    provider_headers,
    validate_config,
)

DEFAULT_MODEL = MODEL
DEFAULT_MAX_TOKENS = MAX_TOKENS


class TutorError(RuntimeError):
    """Raised when the tutor backend cannot produce a completion."""


def _create(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    validate_config()
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        response = requests.post(
            CHAT_COMPLETIONS_URL,
            json=payload,
            headers=provider_headers(),
            timeout=60,
        )
    except requests.RequestException as exc:
        raise TutorError(f"Could not reach OpenRouter: {exc}") from exc

    if response.status_code == 429:
        raise TutorError("OpenRouter rate limit reached (429). Wait a moment and retry.")
    if response.status_code in (401, 403):
        raise TutorError(
            "OpenRouter rejected the credentials (401/403). Check OPENROUTER_API_KEY."
        )
    if not response.ok:
        detail = response.text.strip().replace("\n", " ")[:200]
        raise TutorError(f"OpenRouter returned {response.status_code}: {detail}")

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TutorError("Unexpected response shape from OpenRouter.") from exc


def get_completion(prompt, model=DEFAULT_MODEL, temperature=0):
    """Classic single-prompt helper; returns the model's reply as a string."""
    messages = [{"role": "user", "content": prompt}]
    return get_completion_from_messages(messages, model=model, temperature=temperature)


def get_completion_from_messages(messages, model=DEFAULT_MODEL, temperature=0):
    """Chat-style helper; takes a list of message dicts, returns the reply str."""
    return _create(messages, model=model, temperature=temperature)


def get_llm_response(prompt, temperature=0):
    """Newer-course alias for get_completion (single prompt)."""
    return get_completion(prompt, temperature=temperature)


def print_llm_response(prompt):
    """Get the reply and print it (used by the early course exercises)."""
    print(get_completion(prompt))


def get_response_from_llm(messages, temperature=0):
    """Returns just the string for a messages list, without printing."""
    return get_completion_from_messages(messages, temperature=temperature)


def display_table(data):
    """Render a list of dicts as a table (pandas/IPython when available)."""
    try:
        import pandas as pd
    except ImportError:
        for row in data:
            print(row)
        return

    df = pd.DataFrame(data)
    try:
        from IPython.display import display

        display(df)
    except ImportError:
        print(df.to_string(index=False))


if __name__ == "__main__":
    print_llm_response("Say hello in one short sentence.")
