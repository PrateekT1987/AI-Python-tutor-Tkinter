"""Colors, font fallbacks and HiDPI setup for the desktop app."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont

BG = "#12181F"
PANEL = "#161E27"
PANEL_EDGE = "#232D39"
TEXT = "#E7E5DC"
MUTED = "#7C8896"
BLUE = "#4F8FC0"
AMBER = "#E3A542"
CODE_BG = "#0D1218"
ERROR = "#C4715A"
CODE_FG = "#D6E4EF"
OK_GREEN = "#7FB069"

# Syntax-highlight colors that sit on top of the code block background.
SYNTAX = {
    "kw": "#C792EA",
    "str": "#C3E88D",
    "com": "#66788A",
    "num": "#F78C6C",
    "builtin": "#82AAFF",
}

MONO_CANDIDATES = (
    "JetBrains Mono",
    "SF Mono",
    "Cascadia Mono",
    "Consolas",
    "DejaVu Sans Mono",
    "Menlo",
    "Liberation Mono",
    "Courier New",
    "Courier",
)

BODY_CANDIDATES = (
    "Iowan Old Style",
    "Charter",
    "Georgia",
    "Palatino Linotype",
    "DejaVu Serif",
    "Liberation Serif",
    "Times New Roman",
    "Times",
)


def _family(root: tk.Misc, candidates: tuple[str, ...], fallback: str) -> str:
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        available = set()
    for family in candidates:
        if family in available:
            return family
    return fallback


def mono_font(root: tk.Misc, size: int = 11) -> tuple[str, int]:
    return (_family(root, MONO_CANDIDATES, "Courier"), size)


def body_font(root: tk.Misc, size: int = 12) -> tuple[str, int]:
    return (_family(root, BODY_CANDIDATES, "Times"), size)


def small_font(root: tk.Misc, size: int = 10) -> tuple[str, int]:
    try:
        family = tkfont.nametofont("TkDefaultFont").actual("family")
    except tk.TclError:
        family = "TkDefaultFont"
    return (family, size)


def enable_hidpi(root: tk.Tk) -> None:
    """Best-effort DPI awareness and Tk scaling for Windows and Linux."""
    if sys.platform == "win32":  # pragma: no cover - Windows
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - cosmetic only
            pass
    try:
        scaling = root.winfo_fpixels("1i") / 72.0
        if scaling > 0:
            root.tk.call("tk", "scaling", scaling)
    except tk.TclError:
        pass
