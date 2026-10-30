"""Free-form sandbox window."""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

from sandbox import (
    RUN_MAX_OUTPUT,
    SCRATCH_TIMEOUT,
    execute_python,
    sandbox_summary,
)
from .theme import (
    BG,
    BLUE,
    CODE_BG,
    CODE_FG,
    ERROR,
    MUTED,
    OK_GREEN,
    PANEL,
    PANEL_EDGE,
    TEXT,
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Scratchpad(tk.Toplevel):
    """Free-form code playground: type anything, run it, see the output."""

    FILE = os.path.join(PROJECT_DIR, "scratchpad.py")

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.q = queue.Queue()
        self._cleared = False
        self.title("Sandbox \u2014 free-form scratchpad")
        self.configure(bg=BG)
        self.geometry("660x600")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=2)
        self.rowconfigure(3, weight=1)

        head = tk.Frame(self, bg=PANEL, padx=12, pady=8)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="Sandbox", bg=PANEL, fg=TEXT,
                 font=self.app.body).pack(side="left")
        tk.Label(head, text=f"free-form scratchpad \u2014 {sandbox_summary()}",
                 bg=PANEL, fg=MUTED, font=self.app.small).pack(side="left", padx=(8, 0))
        self.status_lbl = tk.Label(head, text="ready", bg=PANEL, fg=MUTED,
                                   font=self.app.small)
        self.status_lbl.pack(side="right")

        editor_frame = tk.Frame(self, bg=CODE_BG)
        editor_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(8, 4))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)
        self.editor = scrolledtext.ScrolledText(
            editor_frame, wrap="none", undo=True,
            bg=CODE_BG, fg=TEXT, insertbackground=TEXT,
            selectbackground=BLUE, selectforeground=BG,
            relief="flat", borderwidth=0, font=self.app.mono, padx=10, pady=8)
        self.editor.grid(column=0, row=0, sticky="nsew")
        self.editor.tag_configure("placeholder", foreground=MUTED,
                                  font=self.app.small)

        actions = tk.Frame(self, bg=BG)
        actions.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
        self.run_btn = tk.Button(
            actions, text="Run (Ctrl+Enter)", command=self.run,
            font=self.app.mono, bg=BLUE, fg=BG, borderwidth=0,
            activebackground="#6ba7d4", activeforeground=BG,
            padx=12, pady=4, cursor="hand2")
        self.run_btn.pack(side="left")
        self.clear_btn = tk.Button(
            actions, text="Clear", command=self.clear,
            font=self.app.mono, bg=PANEL, fg=MUTED, borderwidth=0,
            activebackground=PANEL_EDGE, activeforeground=TEXT,
            padx=12, pady=4, cursor="hand2")
        self.clear_btn.pack(side="left", padx=(8, 0))
        self.save_btn = tk.Button(
            actions, text="Save", command=self.save,
            font=self.app.mono, bg=PANEL, fg=MUTED, borderwidth=0,
            activebackground=PANEL_EDGE, activeforeground=TEXT,
            padx=12, pady=4, cursor="hand2")
        self.save_btn.pack(side="left", padx=(8, 0))
        self.reload_btn = tk.Button(
            actions, text="Reload", command=self.reload,
            font=self.app.mono, bg=PANEL, fg=MUTED, borderwidth=0,
            activebackground=PANEL_EDGE, activeforeground=TEXT,
            padx=12, pady=4, cursor="hand2")
        self.reload_btn.pack(side="left", padx=(8, 0))
        self.close_btn = tk.Button(
            actions, text="Close", command=self.close,
            font=self.app.mono, bg=PANEL, fg=MUTED, borderwidth=0,
            activebackground=PANEL_EDGE, activeforeground=TEXT,
            padx=12, pady=4, cursor="hand2")
        self.close_btn.pack(side="left", padx=(8, 0))

        out_frame = tk.Frame(self, bg=BG)
        out_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        out_frame.columnconfigure(0, weight=1)
        out_frame.rowconfigure(0, weight=1)
        self.output = scrolledtext.ScrolledText(
            out_frame, wrap="char", bg=BG, fg=CODE_FG, font=self.app.mono,
            relief="flat", borderwidth=0, padx=10, pady=8)
        self.output.grid(column=0, row=0, sticky="nsew")
        self.output.configure(state="disabled")
        self.output.tag_configure("stdout", foreground=CODE_FG)
        self.output.tag_configure("stderr", foreground=ERROR)
        self.output.tag_configure("ok", foreground=OK_GREEN)
        self.output.tag_configure("err", foreground=ERROR)

        self.editor.bind("<Control-Return>", lambda e: self.run())
        self._load()
        self.after(50, self._poll)

    def _load(self):
        try:
            with open(self.FILE, "r", encoding="utf-8") as handle:
                content = handle.read()
        except FileNotFoundError:
            return
        if content.strip():
            self.editor.insert("1.0", content)

    def save(self):
        text = self.editor.get("1.0", "end-1c")
        # Never destroy a saved script because the editor happens to be empty.
        # Only an explicit Clear() writes an empty file.
        if not text.strip() and not self._cleared:
            if os.path.exists(self.FILE) and os.path.getsize(self.FILE) > 0:
                self.set_status("kept existing scratchpad (editor is empty)", MUTED)
                return
        self._cleared = False
        try:
            with open(self.FILE, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass
        self.set_status("saved to scratchpad.py")

    def reload(self):
        """Replace the editor with the on-disk scratchpad file."""
        self.editor.delete("1.0", "end")
        try:
            with open(self.FILE, "r", encoding="utf-8") as handle:
                content = handle.read()
        except FileNotFoundError:
            return
        if content.strip():
            self.editor.insert("1.0", content)
        self.set_status("reloaded from disk")

    def close(self):
        # Never auto-write on close: closing must not overwrite the on-disk
        # scratchpad with whatever happens to be in the editor. Use Save.
        self.destroy()

    def clear(self):
        self.editor.delete("1.0", "end")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._cleared = True
        self.save()  # explicit wipe of the on-disk file too
        self._cleared = False
        self.set_status("cleared")

    def set_status(self, msg, color=MUTED):
        self.status_lbl.configure(text=msg, fg=color)

    def run(self):
        code = self.editor.get("1.0", "end-1c").strip()
        if not code:
            self.set_status("type some code first", ERROR)
            return
        self.run_btn.configure(state="disabled")
        self.set_status("running\u2026", BLUE)

        def worker():
            started = time.time()
            result = execute_python(code, SCRATCH_TIMEOUT)
            elapsed = time.time() - started
            self.q.put((*result, elapsed))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            ok, stdout, stderr, elapsed = self.q.get_nowait()
        except queue.Empty:
            pass
        except ValueError:
            pass
        else:
            self.run_btn.configure(state="normal")
            self.set_status(f"exit {'ok' if ok else 'error'} in {elapsed:.2f}s",
                            OK_GREEN if ok else ERROR)
            self._append_output(ok, stdout, stderr)
        if self.winfo_exists():
            self.after(50, self._poll)

    def _append_output(self, ok, stdout, stderr):
        if len(stdout) > RUN_MAX_OUTPUT:
            stdout = stdout[:RUN_MAX_OUTPUT] + "\n\u2026 (output truncated)"
        if len(stderr) > RUN_MAX_OUTPUT:
            stderr = stderr[:RUN_MAX_OUTPUT] + "\n\u2026 (output truncated)"
        self.output.configure(state="normal")
        divider = ("\u2501 exit " + ("ok" if ok else "error")
                   + " " + "\u2501" * 21 + "\n")
        self.output.insert("end", divider, ("ok" if ok else "err",))
        if stdout.strip():
            self.output.insert(
                "end", stdout + ("\n" if not stdout.endswith("\n") else ""), ("stdout",))
        if stderr.strip():
            self.output.insert(
                "end", stderr + ("\n" if not stderr.endswith("\n") else ""), ("stderr",))
        if not stdout.strip() and not stderr.strip():
            self.output.insert("end", "(no output)\n", ("stdout",))
        self.output.see("end")
        self.output.configure(state="disabled")
