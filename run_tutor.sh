#!/usr/bin/env bash
# Launcher for the Python tutor desktop app.
# Checks dependencies, validates configuration, then runs the GUI.
# It never installs or changes anything on your system.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo_check() { printf "  [%s] %s\n" "$1" "$2"; }
ok()   { echo_check "OK"       "$1"; }
miss() { echo_check "MISSING"  "$1"; }

# 1) Python itself
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "error: '$PY' not found. Install Python 3, e.g.  sudo apt install python3"
    exit 1
fi
echo "python == $("$PY" --version)"

# 2) tkinter
if "$PY" -c "import tkinter" >/dev/null 2>&1; then
    ok "tkinter"
else
    miss "tkinter"
    echo "  -> Your system Python lacks tkinter. Install it with:"
    echo "       sudo apt install python3-tk        # Ubuntu/Debian"
    echo "       sudo dnf install python3-tkinter   # Fedora"
    echo "     The launcher will not modify the system for you."
    exit 1
fi

# 3) requests
if "$PY" -c "import requests" >/dev/null 2>&1; then
    ok "requests ($($PY -c 'import requests; print(requests.__version__)'))"
else
    miss "requests"
    echo "  -> Install it in a virtualenv, or with:"
    echo "       $PY -m pip install --user requests"
    echo "     The launcher will not install packages for you."
    exit 1
fi

# 4) Configuration (fails fast when OPENROUTER_API_KEY or MODEL is missing)
echo "Configuration:"
"$PY" config.py || exit 1

echo "Starting tutor..."
exec "$PY" python_tutor_gui.py
