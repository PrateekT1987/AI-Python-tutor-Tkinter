"""Lightweight regex-based Python syntax highlighting for Tk Text widgets."""

from __future__ import annotations

import re

KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
    "match", "case", "type",
}

BUILTINS = {
    "abs", "all", "any", "ascii", "bin", "bool", "breakpoint", "bytearray",
    "bytes", "callable", "chr", "classmethod", "compile", "complex", "delattr",
    "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter", "float",
    "format", "frozenset", "getattr", "globals", "hasattr", "hash", "help",
    "hex", "id", "input", "int", "isinstance", "issubclass", "iter", "len",
    "list", "locals", "map", "max", "memoryview", "min", "next", "object",
    "oct", "open", "ord", "pow", "print", "property", "range", "repr",
    "reversed", "round", "set", "setattr", "slice", "sorted", "staticmethod",
    "str", "sum", "super", "tuple", "type", "vars", "zip", "__import__",
}

_PATTERN = re.compile(
    r"""
    (?P<comment>\#[^\n]*)
  | (?P<string>
        \"\"\"[\s\S]*?\"\"\"
      | '''[\s\S]*?'''
      | "(?:\\.|[^"\\])*"
      | '(?:\\.|[^'\\])*'
    )
  | (?P<number>
        \b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)\b
    )
  | (?P<keyword>\b(?:%s)\b)
  | (?P<builtin>\b(?:%s)\b)
    """
    % ("|".join(sorted(KEYWORDS, key=len, reverse=True)),
       "|".join(sorted(BUILTINS, key=len, reverse=True))),
    re.VERBOSE,
)

_TAG_FOR_GROUP = {
    "comment": "com",
    "string": "str",
    "number": "num",
    "keyword": "kw",
    "builtin": "builtin",
}


def highlight_python(widget, code: str, start_index: str) -> None:
    """Apply syntax tags to `code`, which begins at `start_index`."""
    for match in _PATTERN.finditer(code):
        tag = _TAG_FOR_GROUP.get(match.lastgroup or "")
        if not tag:
            continue
        widget.tag_add(
            tag,
            f"{start_index}+{match.start()}c",
            f"{start_index}+{match.end()}c",
        )
