"""Parse messages into text and fenced-code blocks.

The parser is deliberately tolerant: fences may use backticks or tildes, may
carry an info string (``python title=demo``), and an unclosed fence at the end
of a streamed answer is treated as code so partial output still renders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class Block:
    kind: str          # "text" or "code"
    value: str
    lang: str = ""


def _lang_from_info(info: str) -> str:
    info = info.strip()
    if not info:
        return ""
    # "python title=demo" -> "python"; ignore bare punctuation.
    return info.split()[0].strip(".,:").lower()


def _is_close(line: str, marker: str) -> bool:
    stripped = line.strip()
    return (
        len(stripped) >= len(marker)
        and set(stripped) == {marker[0]}
    )


def parse_content(text: str) -> list[Block]:
    """Split `text` into text/code blocks, preserving their order."""
    blocks: list[Block] = []
    text_buffer: list[str] = []
    code_buffer: list[str] = []
    marker = ""
    lang = ""

    def flush_text() -> None:
        if text_buffer:
            value = "".join(text_buffer)
            if value.strip():
                blocks.append(Block("text", value))
            text_buffer.clear()

    def flush_code() -> None:
        blocks.append(Block("code", "".join(code_buffer).rstrip("\n"), lang))
        code_buffer.clear()

    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if not marker:
            match = _FENCE_OPEN.match(bare)
            if match:
                flush_text()
                marker = match.group(1)
                lang = _lang_from_info(match.group(2))
            else:
                text_buffer.append(line)
        elif _is_close(bare, marker):
            flush_code()
            marker = ""
            lang = ""
        else:
            code_buffer.append(line)

    if marker:
        # Unclosed fence in a truncated/streamed answer: keep it as code.
        flush_code()
    flush_text()
    return blocks


def looks_truncated(text: str, truncated: bool = False) -> bool:
    """True when the provider hit the token cap or a fence was left open."""
    if truncated:
        return True
    return text.count("```") % 2 == 1 or text.count("~~~") % 2 == 1
