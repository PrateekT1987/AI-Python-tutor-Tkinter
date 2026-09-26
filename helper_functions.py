"""Local helper functions for the LLM course, wired to OpenCode Zen (big-pickle).

Drop-in replacement for the notebook's helper_functions.py. Uses the same
OpenAI-compatible client and key resolution as chatbot.py, so it works with
the venv's exported OPENCODE_API_KEY or the VITE_OPENCODE_API_KEY in .env.

Not a pip package: keep this file next to your scripts and
`from helper_functions import get_completion` will just work.
"""
import os
import time

import pandas as pd
from openai import OpenAI
from openai import RateLimitError

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())  # read local .env file, if present
except ImportError:
    pass  # key may already be in the shell environment

API_KEY = os.getenv("OPENCODE_API_KEY") or os.getenv("VITE_OPENCODE_API_KEY")
if not API_KEY:
    raise SystemExit("OPENCODE_API_KEY not found: activate openai-env or set it in .env")

DEFAULT_MODEL = "big-pickle"

client = OpenAI(
    api_key=API_KEY,
    base_url="https://opencode.ai/zen/v1",
    default_headers={
        "x-opencode-client": "cli",
        "x-opencode-session": f"ses_{int(time.time() * 1000)}",
        "User-Agent": "opencode/1.15.5",
    },
)


def _create(messages, model=DEFAULT_MODEL, temperature=0):
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )


def get_completion(prompt, model=DEFAULT_MODEL, temperature=0):
    """Classic single-prompt helper; returns the model's reply as a string."""
    messages = [{"role": "user", "content": prompt}]
    return get_completion_from_messages(messages, model=model, temperature=temperature)


def get_completion_from_messages(messages, model=DEFAULT_MODEL, temperature=0):
    """Chat-style helper; takes a list of message dicts, returns the reply str."""
    try:
        response = _create(messages, model=model, temperature=temperature)
    except RateLimitError:
        raise SystemExit(
            "OpenCode free tier is rate-limited (429). Wait a few minutes and retry, "
            "or use the tutor's Gemini/other providers instead."
        )
    return response.choices[0].message.content


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
    """Render a list of dicts (or rows) as a table.

    In Jupyter this shows the rich pandas-styled table; as a plain script it
    prints an aligned plain-text table. Same contract as the course helper.
    """
    try:
        import IPython.display  # available in notebooks
    except ImportError:
        IPython = None
    df = pd.DataFrame(data)
    if IPython is not None:
        IPython.display.display(df)
    else:
        print(df.to_string(index=False))


if __name__ == "__main__":
    print_llm_response("Say hello in one short sentence.")