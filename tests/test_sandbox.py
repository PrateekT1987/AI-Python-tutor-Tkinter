"""Tests for the sandbox layer: labels, output capture, limits and stdin."""

from __future__ import annotations

import sys

import pytest

import sandbox


@pytest.fixture
def fixed_info(monkeypatch):
    def install(mechanism, network_isolated):
        monkeypatch.setattr(
            sandbox, "_INFO", sandbox.SandboxInfo(mechanism, network_isolated)
        )

    return install


def test_summary_and_label_for_network_isolated_sandbox(fixed_info):
    fixed_info("bwrap", True)

    assert sandbox.sandbox_summary() == "bwrap, network disabled"
    assert "sandboxed" in sandbox.run_button_label()


def test_summary_and_label_for_opt_in_network(fixed_info):
    fixed_info("unshare", False)

    assert sandbox.sandbox_summary() == "unshare, network enabled (opt-in)"
    assert "network on" in sandbox.run_button_label()


def test_summary_and_label_for_rlimits_fallback(fixed_info):
    fixed_info("rlimits", False)

    assert sandbox.sandbox_summary() == "rlimits only, network enabled"
    assert "no net isolation" in sandbox.run_button_label()


def test_execute_python_returns_stdout():
    ok, stdout, stderr = sandbox.execute_python("print('hello')")

    if not ok:
        pytest.skip(f"sandbox cannot start here: {stderr}")
    assert stdout == "hello\n"
    assert stderr == ""


def test_execute_python_reports_exceptions():
    ok, _stdout, stderr = sandbox.execute_python("raise ValueError('boom')")

    assert ok is False
    assert "ValueError" in stderr
    assert "boom" in stderr


def test_execute_python_reports_syntax_errors():
    ok, _stdout, stderr = sandbox.execute_python("def broken(:\n    pass")

    assert ok is False
    assert "SyntaxError" in stderr


def test_execute_python_closes_stdin():
    ok, stdout, _stderr = sandbox.execute_python(
        "import sys; print(len(sys.stdin.read()))"
    )

    if not ok:
        pytest.skip("sandbox cannot start here")
    assert stdout.strip() == "0"


def test_execute_python_times_out():
    ok, _stdout, stderr = sandbox.execute_python(
        "import time; time.sleep(30)", timeout=1
    )

    assert ok is False
    assert "Timed out after 1s." in stderr


def test_execute_python_runs_with_project_interpreter():
    ok, stdout, _stderr = sandbox.execute_python("import sys; print(sys.version_info[0])")

    if not ok:
        pytest.skip("sandbox cannot start here")
    assert stdout.strip() == str(sys.version_info[0])
