#!/bin/bash
# Met a jour yt-dlp (cause n°1 des 403 quand YouTube change son site).
cd "$(dirname "$0")"
if [ -x "$HOME/.venvs/youtube-audio-dl/bin/python" ]; then
  exec "$HOME/.venvs/youtube-audio-dl/bin/python" -m pip install -U yt-dlp
else
  exec python3 -m pip install -U yt-dlp
fi
