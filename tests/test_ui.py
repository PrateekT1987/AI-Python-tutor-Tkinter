"""Tk integration tests. Skipped automatically when no display is available."""

from __future__ import annotations

import json

import pytest

tkinter = pytest.importorskip("tkinter")

import settings
import ui
import ui.app as app_module
from prompts import LEVELS
from ui.settings_dialog import SettingsDialog


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    try:
        window = tkinter.Tk()
    except tkinter.TclError as exc:  # pragma: no cover - headless CI without xvfb
        pytest.skip(f"no display: {exc}")
    window.withdraw()
    yield window
    try:
        window.destroy()
    except tkinter.TclError:
        pass


def test_app_boots_with_configured_model(root):
    app = ui.TutorApp(root)
    root.update()

    assert app.level in LEVELS
    assert app.model  # falls back to config.MODEL when settings are empty
    assert app.starters_frame.winfo_manager() == "grid"
    assert app.stop_btn["state"] == "disabled"


def test_parsed_answer_highlights_code_and_adds_runner(root):
    app = ui.TutorApp(root)
    app._insert_parsed(
        "Try this:\n```python\ndef add(a, b):\n    return a + b\n```\nDone.",
        "assistant",
    )
    root.update()

    text = app.text.get("1.0", "end-1c")
    assert "def add(a, b):" in text
    assert "Done." in text
    assert app.text.tag_ranges("kw")  # def / return highlighted
    assert app.text.window_names()  # embedded run/copy buttons


def test_saved_history_is_restored_on_launch(root):
    settings.save_session(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "```python\nprint(1)\n```"},
        ]
    )

    app = ui.TutorApp(root)
    root.update()

    assert len(app.history) == 2
    assert app.starters_frame.winfo_manager() == ""
    assert "restored session" in app.text.get("1.0", "end-1c")
    assert app.text.tag_ranges("code")


def test_settings_dialog_validates_and_applies(root):
    app = ui.TutorApp(root)
    saved = {}
    dialog = SettingsDialog(root, app, app.settings, saved.update)

    dialog.temp_var.set("9")
    dialog._save()
    assert "between 0 and 2" in dialog.error.cget("text")
    assert saved == {}

    dialog.model_var.set("vendor/model")
    dialog.temp_var.set("0.7")
    dialog.tokens_var.set("1234")
    dialog._save()

    assert saved == {"model": "vendor/model", "temperature": 0.7, "max_tokens": 1234}
    app._apply_settings(saved)
    assert app.model == "vendor/model"
    assert app.temperature == 0.7
    assert app.max_tokens == 1234


def test_export_transcript_writes_markdown(root, tmp_path, monkeypatch):
    app = ui.TutorApp(root)
    app.history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    target = tmp_path / "transcript.md"
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", lambda **_kw: str(target))

    app.export_transcript()

    content = target.read_text(encoding="utf-8")
    assert "# Python tutor session" in content
    assert "## You" in content
    assert "## Tutor" in content
    assert "hello" in content


def test_new_session_clears_history_and_transcript(root, monkeypatch):
    app = ui.TutorApp(root)
    settings.save_session([{"role": "user", "content": "hi"}])
    app.history = [{"role": "user", "content": "hi"}]
    app.has_sent = True
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a, **_k: True)

    app.new_session()
    root.update()

    assert app.history == []
    assert settings.load_session() == []
    assert app.text.get("1.0", "end-1c") == ""
    assert app.starters_frame.winfo_manager() == "grid"


def test_cancel_sets_event_and_disables_stop(root):
    app = ui.TutorApp(root)
    app.loading = True
    app.stop_btn.configure(state="normal")

    app.cancel()

    assert app.cancel_event.is_set()
    assert app.stop_btn["state"] == "disabled"


def test_close_persists_settings_and_session(root):
    app = ui.TutorApp(root)
    app.level = "Advanced"
    app.settings["geometry"] = "800x600+1+1"
    app.history = [{"role": "user", "content": "kept"}]

    app.on_close()

    with open(settings.settings_path(), encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["level"] == "Advanced"
    assert stored["geometry"] == "800x600+1+1"
    assert settings.load_session() == [{"role": "user", "content": "kept"}]


def test_close_ignores_withdrawn_1x1_geometry(root):
    app = ui.TutorApp(root)
    app.settings["geometry"] = "820x640+2+2"

    app.on_close()

    with open(settings.settings_path(), encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["geometry"] == "820x640+2+2"


def test_sandbox_window_opens_and_runs(root):
    app = ui.TutorApp(root)

    app._toggle_scratch()
    root.update()

    assert app.scratch is not None
    assert app.scratch.winfo_exists()
    app.scratch.close()
