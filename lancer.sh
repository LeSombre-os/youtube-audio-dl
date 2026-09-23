#!/bin/bash
cd "$(dirname "$0")"
if [ -x "$HOME/.venvs/youtube-audio-dl/bin/python" ]; then
  exec "$HOME/.venvs/youtube-audio-dl/bin/python" app.py
else
  exec python3 app.py
fi
