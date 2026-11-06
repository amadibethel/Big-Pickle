#!/bin/bash
# Double-click this file to start Counter and open it in your browser.

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo
  echo "Python 3 is required to run Counter."
  echo "Install it from https://www.python.org/downloads/ and try again."
  echo
  read -r -p "Press Enter to close…"
  exit 1
fi

python3 server.py
