#!/usr/bin/env bash
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  echo "AutoMind AI demo: http://localhost:8080/frontend/index.html"
  python3 -m http.server 8080
else
  echo "Python 3 is required."
fi
