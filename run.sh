#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -d "venv" ]; then
  source venv/bin/activate
fi
python -m mediavault 2>/dev/null || python __main__.py
