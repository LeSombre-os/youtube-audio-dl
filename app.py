"""app.py - Mini serveur web local pour youtube-audio-dl. Stdlib uniquement."""
import http.server
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).parent
DOWNLOADS = BASE_DIR / "downloads"
PROMPT_FILE = BASE_DIR / "PROMPT.md"

sys.path.insert(0, str(BASE_DIR))
from download_music import download_track, load_tracks, load_tracks_from_text, sanitize_filename

PORT = 8000


def find_free_port(start=8000):
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", p))
                return p
            except OSError:
                continue
    return start


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write((BASE_DIR / "index.html").read_bytes())
        elif path == "/api/prompt":
            text = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else ""
            self._json({"prompt": text})
        elif path == "/api/open-folder":
            self._open_folder()
        elif path == "/api/zip":
            self._serve_zip()
        elif path == "/api/health":
            self._json({"ok": True, "downloads": str(DOWNLOADS)})
        elif path.startswith("/downloads/"):
            self._serve_file(path[len("/downloads/"):])
        else:
            self.send_error(404)

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/downloads/"):
            self._serve_file_head(parsed.path[len("/downloads/"):])
        else:
            self.send_error(501)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if parsed.path == "/api/preview":
            self._handle_preview(body)
        elif parsed.path == "/api/start":
            self._handle_start(body)
        elif parsed.path == "/api/upload":
            self._handle_upload(body)
        else:
            self.send_error(404)

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_preview(self, body):
        try:
            data = json.loads(body) if body else {}
            text = data.get("text", "")
            tracks = load_tracks_from_text(text)
            self._json({"tracks": [{"artiste": a, "titre": t} for a, t in tracks]})
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def _handle_upload(self, body):
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            self._json({"error": "multipart attendu"}, 400)
            return
        boundary = ctype.split("boundary=")[-1].encode() if "boundary=" in ctype else None
        if not boundary:
            self._json({"error": "boundary manquant"}, 400)
            return
        try:
            parts = body.split(b"--" + boundary)
            file_data = None
            filename = "upload.xlsx"
            for part in parts:
                if b"filename=" in part:
                    header, content = part.split(b"\r\n\r\n", 1)
                    content = content.rsplit(b"\r\n", 1)[0]
                    for line in header.decode(errors="ignore").split("\r\n"):
                        if "filename=" in line:
                            filename = line.split('filename="')[1].split('"')[0] if 'filename="' in line else filename
                    file_data = content
                    break
            if not file_data:
                self._json({"error": "fichier non trouve"}, 400)
                return
            tmp = Path(tempfile.gettempdir()) / sanitize_filename(filename)
            tmp.write_bytes(file_data)
            tracks = load_tracks(tmp)
            self._json({"tracks": [{"artiste": a, "titre": t} for a, t in tracks], "filename": filename})
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def _handle_start(self, body):
        try:
            data = json.loads(body) if body else {}
            text = data.get("text", "")
            quality = str(data.get("quality", "192"))
            tracks = []
            # Priorite: si upload deja preview, on repasse text; sinon text direct
            if text:
                tracks = load_tracks_from_text(text)
            # Fallback: si tracks vide mais data contient tracks pre-parses
            if not tracks and "tracks" in data:
                tracks = [(t["artiste"], t["titre"]) for t in data["tracks"]]

            if not tracks:
                self._json({"error": "Aucun morceau (colle une liste Artiste - Titre ou upload un fichier)"}, 400)
                return

            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            total = len(tracks)
            for i, (artiste, titre) in enumerate(tracks, 1):
                filename = sanitize_filename(f"{artiste} - {titre}")
                expected = DOWNLOADS / f"{filename}.mp3"
                if expected.exists():
                    msg = {"i": i, "total": total, "artiste": artiste, "titre": titre, "status": "skip"}
                    self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                    continue
                # searching
                msg = {"i": i, "total": total, "artiste": artiste, "titre": titre, "status": "searching"}
                self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                try:
                    download_track(artiste, titre, DOWNLOADS, quality)
                    msg = {"i": i, "total": total, "artiste": artiste, "titre": titre, "status": "ok"}
                except Exception as e:
                    msg = {"i": i, "total": total, "artiste": artiste, "titre": titre, "status": "fail", "error": str(e)}
                self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()

            self.wfile.write(f"data: {json.dumps({'done': True, 'total': total}, ensure_ascii=False)}\n\n".encode())
        except Exception as e:
            try:
                self.wfile.write(f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n".encode())
            except Exception:
                pass

    def _open_folder(self):
        try:
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            if platform.system() == "Windows":
                os.startfile(str(DOWNLOADS))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(DOWNLOADS)])
            else:
                subprocess.Popen(["xdg-open", str(DOWNLOADS)])
            self._json({"ok": True})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _serve_file(self, name):
        try:
            name = urllib.parse.unquote(name)
            safe = Path(name).name
            f = DOWNLOADS / safe
            if not f.exists() or not f.is_file():
                self.send_error(404); return
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(404)

    def _serve_file_head(self, name):
        try:
            name = urllib.parse.unquote(name)
            f = DOWNLOADS / Path(name).name
            if not f.exists():
                self.send_error(404); return
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(f.stat().st_size))
            self.end_headers()
        except Exception:
            self.send_error(404)

    def _serve_zip(self):
        try:
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            tmpzip = Path(tempfile.gettempdir()) / "downloads.zip"
            with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED) as z:
                for f in DOWNLOADS.glob("*.mp3"):
                    z.write(f, f.name)
            data = tmpzip.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="downloads.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="App web youtube-audio-dl")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    port = find_free_port(args.port)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Serveur lance sur {url}")
    print(f"Dossier downloads: {DOWNLOADS}")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open_new_tab(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArret.")


if __name__ == "__main__":
    main()
