"""Tests for prompts and starter questions."""

from __future__ import annotations

import prompts


def test_levels_and_starters_stay_in_sync():
    assert prompts.LEVELS == ["Beginner", "Intermediate", "Advanced"]
    assert set(prompts.STARTERS) == set(prompts.LEVELS)
    for starters in prompts.STARTERS.values():
        assert starters
        assert all(isinstance(item, str) and item.strip() for item in starters)


def test_system_prompt_includes_level_guidance():
    beginner = prompts.build_system_prompt("Beginner")
    advanced = prompts.build_system_prompt("Advanced")

    assert "Python tutor" in beginner
    assert "code block" in beginner
    assert "new to Python" in beginner
    assert "internals" in advanced
    assert beginner != advanced


def test_unknown_level_falls_back_to_intermediate():
    assert prompts.build_system_prompt("Wizard") == prompts.build_system_prompt(
        "Intermediate"
    )


def test_continue_prompt_is_not_empty():
    assert prompts.CONTINUE_PROMPT.strip()
