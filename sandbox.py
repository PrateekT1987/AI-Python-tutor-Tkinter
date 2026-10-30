"""Run untrusted snippets with best-effort OS isolation.

Layers, strongest first:
  1. bubblewrap (`bwrap`) -- read-only root, writable temp dir, no network,
     cleared environment, no capabilities, private /tmp, PID/IPC/UTS namespaces.
  2. `unshare -Urn` -- private network namespace when user namespaces work.
  3. rlimits only -- the snippet can still reach the network.

All layers apply CPU, address-space, file-size, open-file and core limits so a
runaway snippet cannot wedge the machine. The GUI tells the user which layer is
active before every model-generated snippet is run.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass

try:
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]

try:
    from config import ENV as _ENV
except ImportError:  # pragma: no cover - standalone use
    _ENV = {}

RUN_TIMEOUT = 10          # seconds before a snippet is killed
SCRATCH_TIMEOUT = 120     # longer budget for the Sandbox (network/API scripts)
RUN_MAX_OUTPUT = 20000    # characters of stdout/stderr shown

try:
    MEMORY_LIMIT_MB = int(_ENV.get("TUTOR_MEMORY_MB") or "512")
except (ValueError, TypeError):
    MEMORY_LIMIT_MB = 512
MEMORY_LIMIT_BYTES = MEMORY_LIMIT_MB * 1024 * 1024
FILE_SIZE_LIMIT_BYTES = 10 * 1024 * 1024
OPEN_FILE_LIMIT = 128

ALLOW_NETWORK = str(_ENV.get("TUTOR_ALLOW_NETWORK", "")).strip().lower() in {
    "1", "true", "yes", "on",
}

DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"


@dataclass(frozen=True)
class SandboxInfo:
    mechanism: str        # "bwrap", "unshare" or "rlimits"
    network_isolated: bool


_INFO: SandboxInfo | None = None


def _probe(argv: list[str]) -> bool:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _bwrap_probe() -> list[str]:
    argv = [
        "bwrap", "--die-with-parent", "--unshare-all", "--clearenv",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp",
    ]
    if ALLOW_NETWORK:
        argv.append("--share-net")
    return argv + ["--", "true"]


def _detect() -> SandboxInfo:
    if shutil.which("bwrap") and _probe(_bwrap_probe()):
        return SandboxInfo("bwrap", not ALLOW_NETWORK)
    unshare_flag = "-Ur" if ALLOW_NETWORK else "-Urn"
    if shutil.which("unshare") and _probe(["unshare", unshare_flag, "--", "true"]):
        return SandboxInfo("unshare", not ALLOW_NETWORK)
    return SandboxInfo("rlimits", False)


def sandbox_info() -> SandboxInfo:
    """Return (and cache) the strongest isolation available on this machine."""
    global _INFO
    if _INFO is None:
        _INFO = _detect()
    return _INFO


def sandbox_summary() -> str:
    info = sandbox_info()
    if info.network_isolated:
        return f"{info.mechanism}, network disabled"
    if info.mechanism != "rlimits":
        return f"{info.mechanism}, network enabled (opt-in)"
    return "rlimits only, network enabled"


def run_button_label() -> str:
    info = sandbox_info()
    if info.network_isolated:
        return "\u25b6 run this code (sandboxed)"
    if info.mechanism != "rlimits":
        return "\u25b6 run this code (network on)"
    return "\u25b6 run this code (no net isolation)"


def _limit_bootstrap(timeout: int) -> str:
    cpu = int(timeout) + 1
    return (
        "import os, resource, sys\n"
        "def _set(name, value):\n"
        "    limit = getattr(resource, name, None)\n"
        "    if limit is None:\n"
        "        return\n"
        "    try:\n"
        "        resource.setrlimit(limit, (value, value))\n"
        "    except (ValueError, OSError):\n"
        "        pass\n"
        f"_set('RLIMIT_CPU', {cpu})\n"
        f"_set('RLIMIT_AS', {MEMORY_LIMIT_BYTES})\n"
        f"_set('RLIMIT_FSIZE', {FILE_SIZE_LIMIT_BYTES})\n"
        f"_set('RLIMIT_NOFILE', {OPEN_FILE_LIMIT})\n"
        "_set('RLIMIT_CORE', 0)\n"
        "os.execv(sys.executable, [sys.executable, '-I', '-u', sys.argv[1]])\n"
    )


def _inner_command(snippet_path: str, timeout: int) -> list[str]:
    if resource is not None:
        return [sys.executable, "-I", "-c", _limit_bootstrap(timeout), snippet_path]
    return [sys.executable, "-I", "-u", snippet_path]


def _interpreter_binds() -> list[str]:
    """Re-expose the interpreter when it lives under the masked ``/tmp``.

    bwrap mounts a fresh tmpfs on ``/tmp``, which would hide a virtualenv
    created there. Binding back just the interpreter's prefix read-only keeps
    such setups runnable without exposing the rest of the host ``/tmp``.
    """
    candidates: list[str] = []
    for path in (sys.prefix, os.path.dirname(sys.executable)):
        for candidate in (os.path.abspath(path), os.path.realpath(path)):
            if candidate == "/tmp" or candidate.startswith("/tmp/"):
                if candidate not in candidates:
                    candidates.append(candidate)

    args: list[str] = []
    for candidate in candidates:
        if os.path.isdir(candidate):
            args += ["--ro-bind", candidate, candidate]
    return args


def _bwrap_command(workdir: str, inner: list[str]) -> list[str]:
    argv = [
        "bwrap",
        "--die-with-parent",
        "--unshare-all",
        "--clearenv",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
    ]
    argv += _interpreter_binds()
    if ALLOW_NETWORK:
        argv.append("--share-net")
    argv += [
        "--bind", workdir, workdir,
        "--chdir", workdir,
        "--setenv", "PATH", os.environ.get("PATH", DEFAULT_PATH),
        "--setenv", "HOME", workdir,
        "--setenv", "TMPDIR", "/tmp",
        "--cap-drop", "ALL",
        "--",
    ]
    return argv + inner


def _minimal_env(workdir: str) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", DEFAULT_PATH),
        "HOME": workdir,
        "TMPDIR": tempfile.gettempdir(),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows
            proc.kill()
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def execute_python(code: str, timeout: int = RUN_TIMEOUT) -> tuple[bool, str, str]:
    """Run a snippet in an isolated temp dir.

    Returns (ok, stdout, stderr). Never raises for user-code errors; only
    returns a message for timeouts. stdin is closed so input() gets EOF.
    """
    with tempfile.TemporaryDirectory(prefix="pytutor_") as workdir:
        snippet_path = os.path.join(workdir, "snippet.py")
        with open(snippet_path, "w", encoding="utf-8") as handle:
            handle.write(code)

        inner = _inner_command(snippet_path, timeout)
        mechanism = sandbox_info().mechanism
        if mechanism == "bwrap":
            cmd = _bwrap_command(workdir, inner)
        elif mechanism == "unshare":
            cmd = ["unshare", "-Ur" if ALLOW_NETWORK else "-Urn", "--"] + inner
        else:
            cmd = inner

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=_minimal_env(workdir),
                start_new_session=(os.name == "posix"),
            )
        except OSError as exc:
            return False, "", f"Could not start the sandbox: {exc}"

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(proc)
            stdout, stderr = proc.communicate()
            return False, stdout or "", (stderr or "") + f"\nTimed out after {timeout}s."

        return proc.returncode == 0, stdout, stderr
