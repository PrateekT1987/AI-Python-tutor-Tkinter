"""Small settings dialog for model and generation parameters."""

from __future__ import annotations

import tkinter as tk

from config import MAX_TOKENS, MODEL, OPENROUTER_BASE_URL
from settings import DEFAULT_SETTINGS
from .theme import (
    BG,
    BLUE,
    CODE_BG,
    ERROR,
    MUTED,
    PANEL,
    PANEL_EDGE,
    TEXT,
)


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, app, settings: dict, on_save):
        super().__init__(master)
        self.app = app
        self.on_save = on_save
        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.model_var = tk.StringVar(value=settings.get("model") or MODEL)
        self.temp_var = tk.StringVar(value=str(settings.get("temperature", 0.4)))
        self.tokens_var = tk.StringVar(
            value=str(settings.get("max_tokens", MAX_TOKENS))
        )

        body = tk.Frame(self, bg=BG, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        tk.Label(body, text="Model", bg=BG, fg=TEXT, font=app.body,
                 anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        tk.Entry(body, textvariable=self.model_var, width=44,
                 bg=CODE_BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=app.mono).grid(
            row=0, column=1, sticky="ew", padx=(10, 0), pady=4, ipady=4)

        tk.Label(body, text="Temperature", bg=BG, fg=TEXT, font=app.body,
                 anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(body, textvariable=self.temp_var, width=10,
                 bg=CODE_BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=app.mono).grid(
            row=1, column=1, sticky="w", padx=(10, 0), pady=4, ipady=4)

        tk.Label(body, text="Max tokens", bg=BG, fg=TEXT, font=app.body,
                 anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        tk.Entry(body, textvariable=self.tokens_var, width=10,
                 bg=CODE_BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=app.mono).grid(
            row=2, column=1, sticky="w", padx=(10, 0), pady=4, ipady=4)

        tk.Label(body, text="Endpoint", bg=BG, fg=MUTED, font=app.small,
                 anchor="w").grid(row=3, column=0, sticky="w", pady=(10, 2))
        tk.Label(body, text=OPENROUTER_BASE_URL, bg=BG, fg=MUTED,
                 font=app.small, anchor="w").grid(
            row=3, column=1, sticky="w", padx=(10, 0), pady=(10, 2))

        tk.Label(
            body,
            text="Changes apply to the next message. Temperature 0-2; "
                 "max tokens 64-32000.",
            bg=BG, fg=MUTED, font=app.small, wraplength=430, justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.error = tk.Label(body, text="", bg=BG, fg=ERROR, font=app.small,
                              anchor="w", wraplength=430, justify="left")
        self.error.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = tk.Frame(body, bg=BG)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        tk.Button(buttons, text="Restore defaults", command=self._restore,
                  font=app.small, bg=PANEL, fg=MUTED, borderwidth=0,
                  activebackground=PANEL_EDGE, activeforeground=TEXT,
                  padx=10, pady=4, cursor="hand2").pack(side="left")
        tk.Button(buttons, text="Save", command=self._save,
                  font=app.mono, bg=BLUE, fg=BG, borderwidth=0,
                  activebackground="#6ba7d4", activeforeground=BG,
                  padx=14, pady=4, cursor="hand2").pack(side="right")
        tk.Button(buttons, text="Cancel", command=self.destroy,
                  font=app.mono, bg=PANEL, fg=MUTED, borderwidth=0,
                  activebackground=PANEL_EDGE, activeforeground=TEXT,
                  padx=12, pady=4, cursor="hand2").pack(side="right", padx=(0, 8))

    def _restore(self):
        self.model_var.set(MODEL)
        self.temp_var.set(str(DEFAULT_SETTINGS["temperature"]))
        self.tokens_var.set(str(MAX_TOKENS))
        self.error.configure(text="")

    def _save(self):
        model = self.model_var.get().strip()
        if not model:
            self.error.configure(text="Model id cannot be empty.")
            return
        try:
            temperature = float(self.temp_var.get())
        except ValueError:
            self.error.configure(text="Temperature must be a number.")
            return
        if not 0 <= temperature <= 2:
            self.error.configure(text="Temperature must be between 0 and 2.")
            return
        try:
            max_tokens = int(self.tokens_var.get())
        except ValueError:
            self.error.configure(text="Max tokens must be a whole number.")
            return
        if not 64 <= max_tokens <= 32000:
            self.error.configure(text="Max tokens must be between 64 and 32000.")
            return

        self.on_save({
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        self.destroy()
