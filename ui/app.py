"""Main desktop window for the Python tutor."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from config import MODEL, validate_config
from content import looks_truncated, parse_content
from llm import (
    Cancelled,
    describe_error,
    fit_messages,
    stream_chat,
)
from prompts import CONTINUE_PROMPT, LEVELS, STARTERS, build_system_prompt
from sandbox import (
    MEMORY_LIMIT_MB,
    RUN_MAX_OUTPUT,
    RUN_TIMEOUT,
    execute_python,
    run_button_label,
    sandbox_info,
)
from settings import (
    clear_session,
    load_session,
    load_settings,
    save_session,
    save_settings,
)

from .highlight import highlight_python
from .scratchpad import Scratchpad
from .settings_dialog import SettingsDialog
from .theme import (
    AMBER,
    BG,
    BLUE,
    CODE_BG,
    CODE_FG,
    ERROR,
    MUTED,
    OK_GREEN,
    PANEL,
    PANEL_EDGE,
    SYNTAX,
    TEXT,
    body_font,
    enable_hidpi,
    mono_font,
    small_font,
)


class TutorApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.history = load_session()
        self.level = self.settings.get("level") or "Intermediate"
        self.model = self.settings.get("model") or MODEL
        self.temperature = self.settings.get("temperature", 0.4)
        self.max_tokens = self.settings.get("max_tokens", 2000)

        self.loading = False
        self.block_start = None
        self.has_sent = bool(self.history)
        self.scratch = None
        self.q = queue.Queue()
        self.cancel_event = threading.Event()

        self.mono = mono_font(root, 11)
        self.body = body_font(root, 12)
        self.small = small_font(root, 10)

        self._style(root)
        self._build_menu()
        self._build_widgets()
        self._config_tags()
        self.update_level_buttons()

        if self.history:
            self.hide_starters()
            self._render_history()
        else:
            self.show_starters()

        self.root.after(50, self._poll_queue)

    # ── chrome ─────────────────────────────────────────────────────────
    def _style(self, root):
        root.title("Python, interactively")
        root.configure(bg=BG)
        geometry = self.settings.get("geometry")
        try:
            root.geometry(geometry or "860x700")
        except tk.TclError:
            root.geometry("860x700")
        root.minsize(640, 480)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New session", command=self.new_session)
        file_menu.add_command(label="Export transcript\u2026", command=self.export_transcript)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Settings\u2026", command=self.open_settings)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        self.root.config(menu=menubar)

    def _build_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = tk.Frame(self.root, bg=PANEL, pady=10, padx=16)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="Python, interactively", bg=PANEL, fg=TEXT,
                 font=self.body, anchor="w").pack(side="left")
        tk.Label(header, text="Python 3.x console \u2014 a tutor sits behind the prompt",
                 bg=PANEL, fg=MUTED, font=self.small, anchor="w").pack(side="left", padx=(10, 0))

        self.level_buttons = {}
        bar = tk.Frame(header, bg=PANEL)
        bar.pack(side="right")
        self.scratch_btn = tk.Button(
            bar, text="Sandbox", command=self._toggle_scratch,
            font=self.small, borderwidth=0, bd=0, pady=2, padx=10,
            bg=PANEL, fg=MUTED, activebackground=PANEL_EDGE,
            activeforeground=TEXT, cursor="hand2")
        self.scratch_btn.pack(side="right", padx=(8, 0))
        for level in LEVELS:
            btn = tk.Button(bar, text=level, command=lambda value=level: self.set_level(value),
                            font=self.small, borderwidth=0, bd=0, pady=2, padx=8,
                            activebackground=PANEL_EDGE, activeforeground=TEXT,
                            cursor="hand2")
            btn.pack(side="left", padx=1)
            self.level_buttons[level] = btn

        self.starters_frame = tk.Frame(self.root, bg=BG, padx=22, pady=14)
        self.starters_frame.grid(row=1, column=0, sticky="ew")
        tk.Label(self.starters_frame, text=(
            "Ask anything \u2014 a concept, an error message, or code you want reviewed. "
            "Pick a level above to set how much is explained. A few ways to start:"),
            bg=BG, fg=MUTED, font=self.small, wraplength=700, justify="left").pack(anchor="w")
        self.starter_buttons = []
        self._build_starter_buttons()

        self.text = scrolledtext.ScrolledText(
            self.root, wrap="char", bg=BG, fg=TEXT, font=self.body,
            insertbackground=TEXT, selectbackground=BLUE, selectforeground=BG,
            relief="flat", borderwidth=0, padx=22, pady=14, undo=False)
        self.text.grid(row=2, column=0, sticky="nsew")
        self.text.configure(state="disabled")

        bottom = tk.Frame(self.root, bg=PANEL, padx=14, pady=12)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        tk.Label(bottom, text=">>>", fg=AMBER, bg=PANEL,
                 font=self.mono).grid(row=0, column=0, padx=(0, 8))
        self.input_var = tk.StringVar()
        entry = tk.Entry(bottom, textvariable=self.input_var, bg=CODE_BG, fg=TEXT,
                         insertbackground=TEXT, relief="flat", font=self.mono,
                         borderwidth=0)
        entry.grid(row=0, column=1, sticky="ew", ipady=6, ipadx=8)
        entry.bind("<Return>", lambda _event: self.send())
        self.run_btn = tk.Button(bottom, text="Run", command=self.send,
                                 font=self.mono, bg=BLUE, fg=BG, borderwidth=0,
                                 activebackground="#6ba7d4", activeforeground=BG,
                                 padx=14, pady=6, cursor="hand2")
        self.run_btn.grid(row=0, column=2, padx=(10, 0))
        self.stop_btn = tk.Button(bottom, text="Stop", command=self.cancel,
                                  font=self.mono, bg=PANEL_EDGE, fg=MUTED,
                                  borderwidth=0, activebackground=ERROR,
                                  activeforeground=BG, padx=12, pady=6,
                                  cursor="hand2", state="disabled")
        self.stop_btn.grid(row=0, column=3, padx=(8, 0))

        self.status = tk.Label(self.root, bg=BG, fg=MUTED, font=self.small, anchor="se")
        self.status.grid(row=4, column=0, sticky="ew", padx=22, pady=(4, 6))
        self.set_status("ready")

    def _config_tags(self):
        text = self.text
        text.tag_configure("user_prompt", foreground=AMBER, font=self.mono)
        text.tag_configure("ai_prompt", foreground=BLUE, font=self.mono)
        text.tag_configure("user_text", foreground=TEXT)
        text.tag_configure("ai_text", foreground="#D9D6CB")
        text.tag_configure("code", foreground=CODE_FG, background=CODE_BG,
                           font=self.mono, lmargin1=12, lmargin2=12, rmargin=12,
                           spacing1=4, spacing3=4)
        text.tag_configure("error", foreground=ERROR)
        text.tag_configure("thinking", foreground=MUTED, font=self.small, lmargin1=26)
        for name, color in SYNTAX.items():
            text.tag_configure(name, foreground=color)

    def _build_starter_buttons(self):
        for button in self.starter_buttons:
            button.destroy()
        self.starter_buttons = []
        for starter in STARTERS[self.level]:
            button = tk.Button(
                self.starters_frame,
                text=starter,
                command=lambda value=starter: self.send(value),
                bg=PANEL, fg="#D9D6CB", activebackground=PANEL_EDGE,
                activeforeground=TEXT, relief="flat", borderwidth=0,
                font=self.body, anchor="w", justify="left", pady=6, padx=10,
                cursor="hand2")
            button.pack(fill="x", pady=3)
            self.starter_buttons.append(button)

    def update_level_buttons(self):
        for level, button in self.level_buttons.items():
            if level == self.level:
                button.configure(bg=BLUE, fg=BG)
            else:
                button.configure(bg=PANEL, fg=MUTED)

    def set_level(self, level):
        if self.loading:
            return
        self.level = level
        self.settings["level"] = level
        save_settings(self.settings)
        self.update_level_buttons()
        if not self.has_sent:
            self._build_starter_buttons()

    def show_starters(self):
        self.starters_frame.grid()

    def hide_starters(self):
        self.starters_frame.grid_remove()

    # ── scratchpad ─────────────────────────────────────────────────────
    def _toggle_scratch(self):
        if self.scratch is not None and self.scratch.winfo_exists():
            if self.scratch.winfo_viewable():
                self.scratch.withdraw()
                self.scratch_btn.configure(bg=PANEL, fg=MUTED)
            else:
                self.scratch.deiconify()
                self.scratch.lift()
                self.scratch.reload()
                self.scratch_btn.configure(bg=BLUE, fg=BG)
        else:
            self.scratch = Scratchpad(self.root, app=self)
            self.scratch.protocol("WM_DELETE_WINDOW", self._close_scratch)
            self.scratch_btn.configure(bg=BLUE, fg=BG)

    def _close_scratch(self):
        if self.scratch is not None and self.scratch.winfo_exists():
            self.scratch.close()
        self.scratch = None
        self.scratch_btn.configure(bg=PANEL, fg=MUTED)

    # ── status + insertion ─────────────────────────────────────────────
    def set_status(self, msg, color=MUTED):
        self.status.configure(text=msg, fg=color)

    def _insert(self, text, tags=()):
        self.text.configure(state="normal")
        self.text.insert("end", text, tags)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _insert_code(self, code, allow_run):
        self.text.configure(state="normal")
        self.text.insert("end", "\n", ("code",))
        self.text.insert("end", code + "\n", ("code",))
        ranges = self.text.tag_ranges("code")
        if ranges:
            # The "code" tag also covers the leading newline, and Tk merges
            # adjacent ranges, so advance one character to the first code char.
            start = self.text.index(f"{ranges[-2]} + 1c")
            highlight_python(self.text, code, start)
        self.text.see("end")
        self.text.configure(state="disabled")
        if allow_run:
            self._insert_runner(code)

    def _insert_parsed(self, content, role):
        """Insert a message respecting fenced code blocks."""
        is_user = role == "user"
        self._insert(">>> " if is_user else "... ",
                     ("user_prompt" if is_user else "ai_prompt",))
        for block in parse_content(content):
            if not block.value.strip():
                continue
            if block.kind == "code":
                self._insert_code(block.value.strip("\n"), allow_run=not is_user)
            else:
                self._insert(block.value.strip() + "\n",
                             ("user_text" if is_user else "ai_text",))
        self._insert("\n")

    def _insert_runner(self, code):
        """Embed run/copy buttons and an output area under a code block."""
        frame = tk.Frame(self.text, bg=CODE_BG)
        out = tk.Label(
            frame, text="", bg=CODE_BG, fg=CODE_FG,
            font=(self.mono[0], 9), justify="left", anchor="w",
            wraplength=560,
        )
        run = tk.Button(
            frame, text=run_button_label(),
            bg=CODE_BG, fg=BLUE, activebackground=CODE_BG,
            activeforeground="#6ba7d4", relief="flat", borderwidth=0,
            highlightthickness=0, font=(self.mono[0], 9),
            cursor="hand2", padx=2, pady=0,
        )
        copy = tk.Button(
            frame, text="copy",
            bg=CODE_BG, fg=MUTED, activebackground=CODE_BG,
            activeforeground=TEXT, relief="flat", borderwidth=0,
            highlightthickness=0, font=(self.mono[0], 9),
            cursor="hand2", padx=2, pady=0,
        )
        run.configure(command=lambda: self.run_snippet(code, out, run))
        copy.configure(command=lambda: self.copy_code(code))
        run.pack(anchor="w")
        copy.pack(anchor="w")
        out.pack(anchor="w")
        self.text.window_create("end", window=frame, padx=10, pady=2)

    def copy_code(self, code):
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.set_status("code copied to clipboard", OK_GREEN)

    # ── snippet runner ─────────────────────────────────────────────────
    def run_snippet(self, code, out, button):
        info = sandbox_info()
        if info.network_isolated:
            isolation = "network disabled"
        elif info.mechanism != "rlimits":
            isolation = "network enabled (opt-in)"
        else:
            isolation = "NETWORK ENABLED (no isolation available)"
        if not messagebox.askyesno(
            "Run this model-generated snippet?",
            "This code was generated by the tutor and will run locally.\n\n"
            f"Sandbox: {info.mechanism} - {isolation}\n"
            f"Limits: {MEMORY_LIMIT_MB} MB memory, {RUN_TIMEOUT}s CPU, "
            "10 MB file writes, read-only filesystem outside a temp dir.\n\n"
            "Only run code you trust. Continue?",
            parent=self.root,
        ):
            return
        button.configure(state="disabled")
        out.configure(text="running\u2026", fg=MUTED)
        self.set_status("running snippet\u2026")

        def worker():
            result = execute_python(code)
            self.q.put(("run_out", out, button, *result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, out, button, result):
        ok, stdout, stderr = result
        if len(stdout) > RUN_MAX_OUTPUT:
            stdout = stdout[:RUN_MAX_OUTPUT] + "\n\u2026 (output truncated)"
        if len(stderr) > RUN_MAX_OUTPUT:
            stderr = stderr[:RUN_MAX_OUTPUT] + "\n\u2026 (output truncated)"
        chunks = [chunk for chunk in (stdout.rstrip(), stderr.rstrip()) if chunk]
        if not chunks:
            chunks.append("(ran with no output)")
        out.configure(text="\n".join(chunks), fg=(CODE_FG if ok else ERROR))
        button.configure(state="normal")
        self.set_status("ready")

    # ── chat ───────────────────────────────────────────────────────────
    def append_user_message(self, text):
        self._insert_parsed(text, "user")

    def send(self, text=None):
        if self.loading:
            return
        text = (text if text is not None else self.input_var.get()).strip()
        if not text:
            return

        self.cancel_event.clear()
        self.history.append({"role": "user", "content": text})
        self.has_sent = True
        self.hide_starters()
        self.append_user_message(text)
        self.input_var.set("")
        self.loading = True
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.set_status("thinking\u2026")

        self.text.configure(state="normal")
        self.block_start = self.text.index("end-1c")
        self.text.configure(state="disabled")

        messages = [{"role": "system", "content": build_system_prompt(self.level)}]
        messages.extend(self.history)
        messages = fit_messages(messages)
        threading.Thread(target=self._worker, args=(messages,), daemon=True).start()

    def _worker(self, messages):
        text = ""
        flag = {"truncated": False}

        try:
            for token in stream_chat(
                messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                flag=flag,
                cancel=self.cancel_event,
            ):
                text += token
                self.q.put(("token", token))
        except Cancelled:
            self.q.put(("cancelled", text))
            return
        except Exception as exc:  # noqa: BLE001 - report to UI
            if len(text.strip()) >= 40:
                self.q.put(("done", text, True))
                return
            self.q.put(("error", describe_error(exc)))
            return

        if not text.strip():
            self.q.put(("error", "model returned an empty response"))
            return

        rounds = 0
        while looks_truncated(text, flag["truncated"]) and rounds < 2:
            if self.cancel_event.is_set():
                self.q.put(("cancelled", text))
                return
            rounds += 1
            cont_messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": CONTINUE_PROMPT},
            ]
            cont_messages = fit_messages(cont_messages)
            flag = {"truncated": False}
            try:
                for token in stream_chat(
                    cont_messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    flag=flag,
                    cancel=self.cancel_event,
                ):
                    text += token
                    self.q.put(("token", token))
            except Cancelled:
                self.q.put(("cancelled", text))
                return
            except Exception:  # noqa: BLE001 - give up continuing
                flag["truncated"] = True
                break

        self.q.put(("done", text, looks_truncated(text, flag["truncated"])))

    def cancel(self):
        if not self.loading:
            return
        self.cancel_event.set()
        self.stop_btn.configure(state="disabled")
        self.set_status("stopping\u2026")

    def _poll_queue(self):
        try:
            while True:
                kind, *payload = self.q.get_nowait()
                if kind == "token":
                    self._insert(payload[0], ("ai_text",))
                elif kind == "done":
                    self._finish_assistant(payload[0], error=None, truncated=payload[1])
                elif kind == "cancelled":
                    self._finish_assistant(payload[0], error=None, cancelled=True)
                elif kind == "error":
                    self._finish_assistant(None, error=payload[0])
                elif kind == "run_out":
                    out, button, ok, stdout, stderr = payload
                    self._show_result(out, button, (ok, stdout, stderr))
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _finish_assistant(self, text, error, truncated=False, cancelled=False):
        if self.block_start is not None:
            self.text.configure(state="normal")
            self.text.delete(self.block_start, "end-1c")
            self.text.configure(state="disabled")
        self.block_start = None

        if error:
            self._insert(f"!!! tutor request failed ({error}).\n", ("error",))
            self.set_status("error", ERROR)
        else:
            if text:
                self._insert_parsed(text, "assistant")
            if cancelled:
                self._insert("\n[stopped by user]\n", ("error",))
                self.set_status("stopped")
            elif truncated:
                self._insert(
                    "\n[answer cut off at the output limit - say 'continue' "
                    "to get the rest]\n",
                    ("error",),
                )
                self.set_status("answer truncated")
            else:
                self.set_status("ready")
            if text:
                self.history.append({"role": "assistant", "content": text})

        self.loading = False
        self.cancel_event.clear()
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        save_session(self.history)

    # ── history, export, settings, shutdown ────────────────────────────
    def _render_history(self):
        self._insert("[restored session]\n\n", ("thinking",))
        for message in self.history:
            role = message.get("role")
            if role in ("user", "assistant"):
                self._insert_parsed(message.get("content", ""), role)

    def export_transcript(self):
        if not self.history:
            messagebox.showinfo("Export transcript",
                                "There is nothing to export yet.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export transcript",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        lines = [
            "# Python tutor session",
            "",
            f"- Level: {self.level}",
            f"- Model: {self.model}",
            "",
        ]
        for message in self.history:
            role = "You" if message.get("role") == "user" else "Tutor"
            lines.append(f"## {role}\n\n{message.get('content', '')}\n")
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self.root)
            return
        self.set_status(f"exported to {os.path.basename(path)}", OK_GREEN)

    def new_session(self):
        if self.loading:
            messagebox.showinfo("Busy", "Stop the current answer first.",
                                parent=self.root)
            return
        if not messagebox.askyesno("New session",
                                   "Clear the transcript and saved history?",
                                   parent=self.root):
            return
        self.history.clear()
        clear_session()
        self.has_sent = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.show_starters()
        self.set_status("new session")

    def open_settings(self):
        SettingsDialog(self.root, self, self.settings, self._apply_settings)

    def _apply_settings(self, values):
        self.settings.update(values)
        self.model = self.settings.get("model") or MODEL
        self.temperature = self.settings["temperature"]
        self.max_tokens = self.settings["max_tokens"]
        save_settings(self.settings)
        self.set_status(f"settings saved \u2014 model {self.model}", OK_GREEN)

    def on_close(self):
        self.cancel_event.set()
        try:
            self.settings["level"] = self.level
            geometry = self.root.winfo_geometry()
            if not geometry.startswith("1x1"):
                self.settings["geometry"] = geometry
            save_settings(self.settings)
            save_session(self.history)
        finally:
            self.root.destroy()


def main():
    validate_config()
    root = tk.Tk()
    enable_hidpi(root)
    TutorApp(root)
    root.mainloop()
