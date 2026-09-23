"""app.py - Mini serveur web local pour youtube-audio-dl. Stdlib uniquement."""
import http.server
import itertools
import json
import os
import platform
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
import zipfile
from pathlib import Path

APP_VERSION = "1.2.0"

BASE_DIR = Path(__file__).parent
DOWNLOADS = BASE_DIR / "downloads"
PROMPT_FILE = BASE_DIR / "PROMPT.md"
LAST_IMPORT = BASE_DIR / "last_import.json"
PORT_FILE = BASE_DIR / "port.txt"
MAX_IMPORT_TRACKS = 2000

sys.path.insert(0, str(BASE_DIR))
from download_music import Aborted, download_track, friendly_error, is_valid_mp3, load_tracks, load_tracks_from_text, sanitize_filename

PORT = 8000


def _origin_allowed(origin: str | None) -> bool:
    """Garde-fou CSRF : n'autorise que la page locale et les extensions navigateur.
    Absent (navigation, curl, <audio>) = OK. Extension (chrome/moz-extension) = OK.
    Même origine 127.0.0.1/localhost = OK. Tout site https tiers = refusé."""
    if not origin or origin == "null":
        return origin != "null"
    try:
        u = urllib.parse.urlparse(origin)
    except Exception:
        return False
    if u.scheme in ("chrome-extension", "moz-extension"):
        return True
    return u.hostname in ("127.0.0.1", "localhost") and u.scheme in ("http", "https")


def _health():
    try:
        import yt_dlp
        ytdlp_v = yt_dlp.version.__version__
    except Exception:
        ytdlp_v = None
    try:
        pending = len(json.loads(LAST_IMPORT.read_text(encoding="utf-8")).get("tracks", [])) if LAST_IMPORT.exists() else 0
    except Exception:
        pending = -1
    active = _active_job()
    return {
        "ok": True,
        "app": APP_VERSION,
        "downloads": str(DOWNLOADS),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "yt_dlp": ytdlp_v,
        "python": platform.python_version(),
        "pending_import": pending,
        "job": {"id": active.id, "state": active.state} if active else None,
    }


class Job:
    """Un run de téléchargement pilotable : pause (entre pistes), stop, relecture."""

    def __init__(self, tracks, quality):
        self.id = f"job-{next(_JOB_SEQ)}"
        self.tracks = tracks
        self.quality = quality
        self.total = len(tracks)
        self.pause = threading.Event()   # set = suspendu
        self.cancel = threading.Event()  # set = arrêté
        self.lock = threading.Lock()
        self.subs = []
        self.events = []  # rejoués aux streams qui se rattachent (hors heartbeats)
        self.state = "running"  # running | paused | done | cancelled
        self.ok = self.skip = self.fail = 0

    def _emit(self, msg, store=True):
        msg = {"job": self.id, **msg}
        with self.lock:
            if store:
                self.events.append(msg)
            subs = list(self.subs)
        for q in subs:
            q.put(msg)

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.subs.append(q)
            past = list(self.events)
        return q, past

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subs:
                self.subs.remove(q)

    def finish(self, state):
        with self.lock:
            self.state = state
        final = {"state": state, "total": self.total, "ok": self.ok, "skip": self.skip, "fail": self.fail}
        final["cancelled" if state == "cancelled" else "done"] = True
        self._emit(final)
        with self.lock:
            subs = list(self.subs)
        for q in subs:
            q.put(None)

    def snapshot(self):
        with self.lock:
            return {"job": self.id, "state": self.state, "quality": self.quality,
                    "total": self.total, "ok": self.ok, "skip": self.skip, "fail": self.fail,
                    "tracks": [{"artiste": a, "titre": t} for a, t in self.tracks],
                    "events": list(self.events)}


_JOB_SEQ = itertools.count(1)
_JOBS = {}
_JOBS_LOCK = threading.Lock()
_ACTIVE_ID = None


def _active_job():
    with _JOBS_LOCK:
        j = _JOBS.get(_ACTIVE_ID)
    return j if j is not None and j.state in ("running", "paused") else None


def _get_job(jid):
    with _JOBS_LOCK:
        return _JOBS.get(jid)


def _run_job(job):
    global _ACTIVE_ID
    try:
        job._emit({"total": job.total})
        for i, (artiste, titre) in enumerate(job.tracks, 1):
            if job.cancel.is_set():
                break
            while job.pause.is_set() and not job.cancel.is_set():
                job._emit({"i": i, "total": job.total, "artiste": artiste, "titre": titre,
                           "status": "paused"}, store=False)
                time.sleep(1)
            if job.cancel.is_set():
                break
            filename = sanitize_filename(f"{artiste} - {titre}")
            expected = DOWNLOADS / f"{filename}.mp3"
            if is_valid_mp3(expected):
                job.skip += 1
                job._emit({"i": i, "total": job.total, "artiste": artiste, "titre": titre, "status": "skip"})
                continue
            if expected.exists():
                expected.unlink()  # corrompu/vide : re-télécharge au lieu de skipper
            job._emit({"i": i, "total": job.total, "artiste": artiste, "titre": titre, "status": "searching"})
            try:
                download_track(artiste, titre, DOWNLOADS, job.quality, abort=job.cancel.is_set)
                job.ok += 1
                job._emit({"i": i, "total": job.total, "artiste": artiste, "titre": titre, "status": "ok"})
            except Aborted:
                job._emit({"i": i, "total": job.total, "artiste": artiste, "titre": titre, "status": "stopped"})
                break
            except Exception as e:
                job.fail += 1
                job._emit({"i": i, "total": job.total, "artiste": artiste, "titre": titre,
                           "status": "fail", "error": friendly_error(e)})
        job.finish("cancelled" if job.cancel.is_set() else "done")
    finally:
        with _JOBS_LOCK:
            global _ACTIVE_ID
            if _ACTIVE_ID == job.id:
                _ACTIVE_ID = None


def _parse_tracks(data):
    text = data.get("text", "")
    quality = str(data.get("quality", "192"))
    if quality not in ("192", "256", "320"):
        quality = "192"
    tracks = []
    if text:
        tracks = load_tracks_from_text(text)
    if not tracks and "tracks" in data:
        raw = data["tracks"] if isinstance(data["tracks"], list) else []
        tracks = [(str(t.get("artiste", "")).strip(), str(t.get("titre", "")).strip())
                  for t in raw if isinstance(t, dict)]
        tracks = [(a, t) for a, t in tracks if a and t]
    if not tracks:
        return None, quality, "Aucun morceau (colle une liste Artiste - Titre ou upload un fichier)"
    if len(tracks) > MAX_IMPORT_TRACKS:
        return None, quality, f"Trop de morceaux ({len(tracks)} > {MAX_IMPORT_TRACKS}) — découpe ta liste"
    return tracks, quality, None


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

    def do_OPTIONS(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/import", "/api/health", "/api/preview", "/api/start", "/api/upload", "/api/job"):
            origin = self.headers.get("Origin")
            self.send_response(204)
            if origin and _origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_error(404)

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
            if not _origin_allowed(self.headers.get("Origin")):
                self._forbidden_origin()
            else:
                self._open_folder()
        elif path == "/api/zip":
            if not _origin_allowed(self.headers.get("Origin")):
                self._forbidden_origin()
            else:
                self._serve_zip()
        elif path == "/api/health":
            self._json(_health())
        elif path == "/api/job":
            self._handle_job_get(parsed.query)
        elif path == "/api/stream":
            self._handle_stream(parsed.query)
        elif path == "/api/import":
            self._handle_import_get()
        elif path.startswith("/downloads/"):
            self._serve_file(path[len("/downloads/"):])
        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/import":
            if not _origin_allowed(self.headers.get("Origin")):
                self._forbidden_origin()
                return
            try:
                if LAST_IMPORT.exists():
                    LAST_IMPORT.unlink()
                self._json({"ok": True})
            except Exception as e:
                self._json({"error": str(e)}, 500)
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
        if not _origin_allowed(self.headers.get("Origin")):
            self._forbidden_origin()
            return

        if parsed.path == "/api/preview":
            self._handle_preview(body)
        elif parsed.path == "/api/import":
            self._handle_import_post(body)
        elif parsed.path == "/api/start":
            self._handle_start(body)
        elif parsed.path == "/api/upload":
            self._handle_upload(body)
        elif parsed.path == "/api/job":
            self._handle_job_post(body)
        else:
            self.send_error(404)

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        origin = self.headers.get("Origin")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if origin and _origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _forbidden_origin(self):
        data = json.dumps({"error": "origine non autorisée"}).encode()
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_import_get(self):
        try:
            if LAST_IMPORT.exists():
                origin = self.headers.get("Origin")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                if origin and _origin_allowed(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                data = LAST_IMPORT.read_bytes()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json({"tracks": []})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _handle_import_post(self, body):
        try:
            data = json.loads(body) if body else {}
            raw = data.get("tracks", [])
            source = str(data.get("source", "extension"))[:40]
            url = str(data.get("url", ""))[:500]
            # Normalise via le parseur existant (garde-fou format unique)
            text = "\n".join(
                f"{str(t.get('artiste', '')).strip()} - {str(t.get('titre', '')).strip()}"
                for t in raw if isinstance(t, dict)
            )
            tracks = load_tracks_from_text(text)[:MAX_IMPORT_TRACKS]
            if not tracks:
                self._json({"error": "Aucun morceau valide (attendu: [{artiste, titre}])"}, 400)
                return
            payload = {
                "tracks": [{"artiste": a, "titre": t} for a, t in tracks],
                "source": source,
                "url": url,
            }
            import time
            payload["at"] = int(time.time())
            LAST_IMPORT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            payload["ok"] = True
            payload["count"] = len(tracks)
            self._json(payload)
        except Exception as e:
            self._json({"error": str(e)}, 400)

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
            tmp = Path(tempfile.gettempdir()) / (sanitize_filename(filename) or "upload.xlsx")
            tmp.write_bytes(file_data)
            try:
                if tmp.suffix.lower() == ".txt":
                    tracks = load_tracks_from_text(file_data.decode("utf-8", errors="ignore"))
                else:
                    tracks = load_tracks(tmp)
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            self._json({"tracks": [{"artiste": a, "titre": t} for a, t in tracks], "filename": filename})
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def _handle_start(self, body):
        try:
            data = json.loads(body) if body else {}
        except Exception:
            self._json({"error": "JSON invalide"}, 400)
            return
        tracks, quality, err = _parse_tracks(data)
        if err:
            self._json({"error": err}, 400)
            return
        with _JOBS_LOCK:
            global _ACTIVE_ID
            cur = _JOBS.get(_ACTIVE_ID)
            if cur is not None and cur.state in ("running", "paused"):
                self._json({"error": "Un téléchargement tourne déjà (pause ou stop d'abord)"}, 409)
                return
            DOWNLOADS.mkdir(parents=True, exist_ok=True)
            job = Job(tracks, quality)
            _JOBS[job.id] = job
            finished = [jid for jid, j in _JOBS.items() if j.state in ("done", "cancelled")]
            for jid in finished[:-4]:
                del _JOBS[jid]
            _ACTIVE_ID = job.id
        threading.Thread(target=_run_job, args=(job,), daemon=True).start()
        self._stream_job(job)

    def _stream_job(self, job):
        finished = job.state in ("done", "cancelled")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        # Job fini : on ferme derrière (le client reçoit EOF). Sinon keep-alive + ping.
        self.send_header("Connection", "close" if finished else "keep-alive")
        self.end_headers()
        # Un stream = une réponse terminale : pas de réutilisation de la connexion.
        self.close_connection = True
        q, past = job.subscribe()
        try:
            for m in past:
                self.wfile.write(f"data: {json.dumps(m, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            if finished:
                return  # rattaché à un job fini : l'historique suffit
            while True:
                try:
                    m = q.get(timeout=25)
                except queue.Empty:
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    continue
                if m is None:
                    return
                self.wfile.write(f"data: {json.dumps(m, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            job.unsubscribe(q)

    def _handle_stream(self, query):
        qs = urllib.parse.parse_qs(query)
        job = _get_job((qs.get("id") or [""])[0])
        if job is None:
            self._json({"error": "job inconnu ou expiré"}, 404)
            return
        self._stream_job(job)

    def _handle_job_get(self, query):
        qs = urllib.parse.parse_qs(query)
        jid = (qs.get("id") or [None])[0]
        job = _get_job(jid) if jid else _active_job()
        if job is None:
            if jid:
                # Dernier état connu ? job expiré/élagué.
                self._json({"job": jid, "state": "unknown"})
            else:
                self._json({"job": None})
            return
        self._json(job.snapshot())

    def _handle_job_post(self, body):
        try:
            data = json.loads(body) if body else {}
        except Exception:
            self._json({"error": "JSON invalide"}, 400)
            return
        action = str(data.get("action", ""))
        job = _get_job(data.get("id")) if data.get("id") else _active_job()
        if job is None or job.state not in ("running", "paused"):
            self._json({"error": "Aucun téléchargement actif"}, 400)
            return
        if action == "pause" and job.state == "running":
            job.pause.set()
            with job.lock:
                job.state = "paused"
        elif action == "resume" and job.state == "paused":
            job.pause.clear()
            with job.lock:
                job.state = "running"
            job._emit({"status": "resumed", "total": job.total})
        elif action == "stop":
            job.cancel.set()
            job.pause.clear()
        else:
            self._json({"error": f"Action inconnue ou sans effet : {action} (état {job.state})"}, 400)
            return
        self._json({"job": job.id, "state": job.state})

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

    def _resolve_download(self, name):
        f = DOWNLOADS / Path(urllib.parse.unquote(name)).name
        return f if f.is_file() else None

    def _serve_file(self, name):
        try:
            f = self._resolve_download(name)
            if not f:
                self.send_error(404); return
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self.send_error(404)

    def _serve_file_head(self, name):
        try:
            f = self._resolve_download(name)
            if not f:
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


def preflight() -> list[str]:
    """Verifie l'environnement avant de demarrer. Retourne la liste des problemes (vide = OK)."""
    problems = []
    if sys.version_info < (3, 10):
        problems.append(f"Python 3.10+ requis (actuel : {platform.python_version()}) → https://www.python.org/downloads/")
    if shutil.which("ffmpeg") is None:
        if platform.system() == "Windows":
            problems.append("ffmpeg introuvable → winget install Gyan.FFmpeg (puis rouvre le terminal)")
        elif platform.system() == "Darwin":
            problems.append("ffmpeg introuvable → brew install ffmpeg")
        else:
            problems.append("ffmpeg introuvable → sudo apt install ffmpeg")
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        problems.append("yt-dlp manquant → pip install -r requirements.txt")
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        problems.append("openpyxl manquant → pip install -r requirements.txt")
    return problems


def main():
    import argparse

    parser = argparse.ArgumentParser(description="App web youtube-audio-dl")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--silent", action="store_true", help="autostart : ni navigateur, ni messages")
    args = parser.parse_args()

    problems = preflight()
    if problems:
        print("Impossible de démarrer :")
        for p in problems:
            print(f"  ❌ {p}")
        sys.exit(1)

    # Instance unique : si le port mémorisé répond, on réutilise l'onglet existant.
    if not args.silent:
        try:
            saved = int(PORT_FILE.read_text(encoding="utf-8").strip())
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{saved}/api/health", timeout=2) as r:
                if r.status == 200:
                    url = f"http://127.0.0.1:{saved}"
                    print(f"Déjà lancé sur {url}")
                    if not args.no_browser:
                        webbrowser.open_new_tab(url)
                    return
        except Exception:
            pass

    port = find_free_port(args.port)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    try:
        PORT_FILE.write_text(str(port), encoding="utf-8")
    except OSError:
        pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    if not args.silent:
        print(f"Serveur lance sur {url}")
        print(f"Dossier downloads: {DOWNLOADS}")
    if not args.no_browser and not args.silent:
        threading.Timer(0.8, lambda: webbrowser.open_new_tab(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if not args.silent:
            print("\nArret.")
    finally:
        try:
            if PORT_FILE.exists() and PORT_FILE.read_text(encoding="utf-8").strip() == str(port):
                PORT_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
