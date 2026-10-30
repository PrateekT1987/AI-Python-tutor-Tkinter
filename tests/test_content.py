"""Tests for the tolerant fenced-code parser and truncation detection."""

from __future__ import annotations

from content import Block, looks_truncated, parse_content


def test_plain_text_is_one_block():
    assert parse_content("hello **world**") == [Block("text", "hello **world**")]


def test_fenced_python_block_is_split_out():
    blocks = parse_content("before\n```python\nprint('hi')\n```\nafter")

    assert [block.kind for block in blocks] == ["text", "code", "text"]
    assert blocks[1].lang == "python"
    assert blocks[1].value == "print('hi')"
    assert blocks[0].value == "before\n"
    assert blocks[2].value == "after"


def test_info_string_is_reduced_to_language():
    blocks = parse_content('```python title="demo"\nx = 1\n```')

    assert len(blocks) == 1
    assert blocks[0].lang == "python"
    assert blocks[0].value == "x = 1"


def test_tilde_fence_is_supported():
    blocks = parse_content("~~~\ncode\n~~~")

    assert blocks == [Block("code", "code", "")]


def test_unclosed_fence_is_treated_as_code():
    blocks = parse_content("text\n```python\nprint('cut')")

    assert [block.kind for block in blocks] == ["text", "code"]
    assert blocks[1].value == "print('cut')"


def test_empty_text_produces_no_blocks():
    assert parse_content("") == []


def test_blank_text_around_code_is_dropped():
    blocks = parse_content("\n\n```\nx\n```\n\n")

    assert [block.kind for block in blocks] == ["code"]


def test_longer_fence_can_contain_shorter_one():
    blocks = parse_content("````\n```\nnested\n```\n````")

    assert len(blocks) == 1
    assert "```" in blocks[0].value


def test_looks_truncated_detects_open_fence():
    assert looks_truncated("```python\nx = 1") is True
    assert looks_truncated("~~~\nx") is True


def test_looks_truncated_respects_provider_flag():
    assert looks_truncated("complete answer", truncated=True) is True
    assert looks_truncated("complete answer") is False
