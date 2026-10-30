"""Parse messages into text and fenced-code blocks with inline markdown support.

The parser is deliberately tolerant: fences may use backticks or tildes, may
carry an info string (``python title=demo``), and an unclosed fence at the end
of a streamed answer is treated as code so partial output still renders.

Also handles inline markdown (bold, italic, code) and tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|\s*[-:]+\s*\|")

# Inline markdown patterns
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class Block:
    kind: str          # "text", "code", or "table"
    value: str
    lang: str = ""


@dataclass(frozen=True)
class InlineSpan:
    """Represents an inline markdown element."""
    type: str  # "bold", "italic", "code", "text"
    text: str


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


def _is_table_row(line: str) -> bool:
    return bool(_TABLE_ROW.match(line.strip()))


def _is_table_sep(line: str) -> bool:
    return bool(_TABLE_SEP.match(line.strip()))


def parse_content(text: str) -> list[Block]:
    """Split `text` into text/code/table blocks, preserving their order."""
    blocks: list[Block] = []
    text_buffer: list[str] = []
    code_buffer: list[str] = []
    table_buffer: list[str] = []
    marker = ""
    lang = ""
    in_table = False

    def flush_text() -> None:
        if text_buffer:
            value = "".join(text_buffer)
            if value.strip():
                blocks.append(Block("text", value))
            text_buffer.clear()

    def flush_code() -> None:
        blocks.append(Block("code", "".join(code_buffer).rstrip("\n"), lang))
        code_buffer.clear()

    def flush_table() -> None:
        if table_buffer:
            blocks.append(Block("table", "".join(table_buffer).rstrip("\n"), ""))
            table_buffer.clear()

    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        
        # Check for table separator
        if _is_table_sep(line):
            if not in_table:
                flush_text()
                in_table = True
            table_buffer.append(line)
            continue
            
        # Check for table row
        if _is_table_row(line):
            if not in_table:
                flush_text()
                in_table = True
            table_buffer.append(line)
            continue
            
        # Not a table line
        if in_table:
            flush_table()
            in_table = False

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
        flush_code()
    if in_table:
        flush_table()
    flush_text()
    return blocks


def parse_inline(text: str) -> list[InlineSpan]:
    """Parse inline markdown (bold, italic, code) into spans."""
    spans: list[InlineSpan] = []
    pos = 0
    
    # Combined pattern for all inline elements
    pattern = re.compile(r"\*\*(.+?)\*\*|(?<!\*)\*([^*]+)\*(?!\*)|`([^`\n]+)`")
    
    last_end = 0
    for match in re.finditer(r"\*\*(.+?)\*\*|(?<!\*)\*([^*]+)\*(?!\*)|`([^`\n]+)`", text):
        start, end = match.span()
        if start > last_end:
            spans.append(InlineSpan("text", text[last_end:start]))
        
        if match.group(1) is not None:  # bold
            spans.append(InlineSpan("bold", match.group(1)))
        elif match.group(2) is not None:  # italic
            spans.append(InlineSpan("italic", match.group(2)))
        elif match.group(3) is not None:  # inline code
            spans.append(InlineSpan("code", match.group(3)))
        
        last_end = match.end()
    
    if last_end < len(text):
        spans.append(InlineSpan("text", text[last_end:]))
    
    return spans


def parse_table(text: str) -> tuple[list[list[str]], list[int]]:
    """Parse a markdown table into rows and column widths.
    
    Returns (rows, col_widths) where rows is list of cell lists.
    """
    lines = text.strip().split("\n")
    rows = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _is_table_sep(line):
            continue
        match = _TABLE_ROW.match(line)
        if match:
            cells = [cell.strip() for cell in match.group(1).split("|")]
            rows.append(cells)
    
    if not rows:
        return [], []
    
    # Calculate column widths
    num_cols = len(rows[0])
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))
    
    return rows, col_widths


def format_table(rows: list[list[str]], col_widths: list[int]) -> str:
    """Format a table as aligned text with borders."""
    if not rows:
        return ""
    
    lines = []
    for i, row in enumerate(rows):
        cells = []
        for j, cell in enumerate(row):
            width = col_widths[j]
            cells.append(cell.ljust(width))
        lines.append(" │ ".join(cells))
        
        # Add separator after header
        if i == 0:
            sep = "─┼─".join("─" * w for w in col_widths)
            lines.append(sep)
    
    return "\n".join(lines)


def _lang_from_info(info: str) -> str:
    info = info.strip()
    if not info:
        return ""
    return info.split()[0].strip(".,:").lower()


_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|\s*[-:]+\s*\|")


def _is_close(line: str, marker: str) -> bool:
    stripped = line.strip()
    return (
        len(stripped) >= len(marker)
        and set(stripped) == {marker[0]}
    )


def parse_content(text: str) -> list[Block]:
    """Split `text` into text/code/table blocks, preserving their order."""
    blocks: list[Block] = []
    text_buffer: list[str] = []
    code_buffer: list[str] = []
    table_buffer: list[str] = []
    marker = ""
    lang = ""
    in_table = False

    def flush_text() -> None:
        if text_buffer:
            value = "".join(text_buffer)
            if value.strip():
                blocks.append(Block("text", value))
            text_buffer.clear()

    def flush_code() -> None:
        blocks.append(Block("code", "".join(code_buffer).rstrip("\n"), lang))
        code_buffer.clear()

    def flush_table() -> None:
        if table_buffer:
            blocks.append(Block("table", "".join(table_buffer).rstrip("\n"), ""))
            table_buffer.clear()

    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        
        # Check for table separator
        if _is_table_sep(line):
            if not in_table:
                flush_text()
                in_table = True
            table_buffer.append(line)
            continue
            
        # Check for table row
        if _TABLE_ROW.match(line.strip()):
            if not in_table:
                flush_text()
                in_table = True
            table_buffer.append(line)
            continue
            
        # Not a table line
        if in_table:
            flush_table()
            in_table = False

        if not marker:
            match = re.match(r"^(`{3,}|~{3,})(.*)$", bare)
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
        flush_code()
    if in_table:
        flush_table()
    flush_text()
    return blocks


def looks_truncated(text: str, truncated: bool = False) -> bool:
    """True when the provider hit the token cap or a fence was left open."""
    if truncated:
        return True
    return text.count("```") % 2 == 1 or text.count("~~~") % 2 == 1