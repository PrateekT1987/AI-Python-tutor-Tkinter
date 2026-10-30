#!/usr/bin/env python3
"""Python, interactively — a desktop Python tutor backed by OpenRouter.

Thin entry point. The implementation is split across:
    config.py     .env loading, OpenRouter settings, validation
    prompts.py    system prompt, levels and starter questions
    content.py    text/code-block parsing
    llm.py        streaming client: retries, cancellation, context trimming
    sandbox.py    isolated snippet execution
    settings.py   local settings + saved session
    ui/           theme, syntax highlighting, windows

Run with:  python3 python_tutor_gui.py
"""

from ui import main

if __name__ == "__main__":
    main()
