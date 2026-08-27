"""
download_music - coeur metier telechargement YouTube -> MP3
Utilisation CLI:
    python download_music.py
    python download_music.py fichier.xlsx --quality 320
Utilisation module:
    from download_music import load_tracks, load_tracks_from_text, download_track
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd
import yt_dlp

BASE_DIR = Path(__file__).parent
DEFAULT_DOWNLOADS = BASE_DIR / "downloads"
DEFAULT_LOG = BASE_DIR / "download_failures.log"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:150] if len(name) > 150 else name


def find_spreadsheet(base: Path) -> Path | None:
    for ext in ("*.xlsx", "*.xls", "*.csv"):
        files = list(base.glob(ext))
        if files:
            return files[0]
    return None


def detect_columns(df: pd.DataFrame) -> tuple[str, str]:
    col_map = {c.lower().strip(): c for c in df.columns}
    artiste_col = None
    titre_col = None
    for low, orig in col_map.items():
        if "artiste" in low or low == "artist":
            artiste_col = orig
        if "titre" in low or low == "title" or "titre du morceau" in low:
            titre_col = orig
    if not artiste_col or not titre_col:
        raise ValueError(f"Colonnes Artiste/Titre introuvables. Colonnes detectees: {list(df.columns)}")
    return artiste_col, titre_col


def load_tracks(path: Path) -> list[tuple[str, str]]:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)
    artiste_col, titre_col = detect_columns(df)
    df = df[[artiste_col, titre_col]].copy()
    df[artiste_col] = df[artiste_col].astype(str).str.strip()
    df[titre_col] = df[titre_col].astype(str).str.strip()
    df = df[(df[artiste_col] != "") & (df[titre_col] != "") & (df[artiste_col] != "nan") & (df[titre_col] != "nan")]
    return list(zip(df[artiste_col].tolist(), df[titre_col].tolist()))


def load_tracks_from_text(text: str) -> list[tuple[str, str]]:
    tracks = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sep = None
        for cand in [" - ", " – ", " — ", " | ", ";"]:
            if cand in line:
                sep = cand
                break
        if sep:
            a, t = line.split(sep, 1)
        elif "," in line and line.count(",") == 1:
            a, t = line.split(",", 1)
        else:
            continue
        a, t = a.strip(), t.strip()
        if a and t:
            tracks.append((a, t))
    return tracks


def download_track(artiste: str, titre: str, downloads: Path, quality: str) -> bool:
    filename = sanitize_filename(f"{artiste} - {titre}")
    expected_mp3 = downloads / f"{filename}.mp3"
    if expected_mp3.exists():
        logging.info(f"[SKIP] {filename} deja present")
        return True
    query = f"{artiste} - {titre} Official Audio"
    search_url = f"ytsearch1:{query}"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(downloads / f"{filename}.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality}],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([search_url])
    return True


def main():
    parser = argparse.ArgumentParser(description="Telecharge les audios YouTube depuis un tableur ou une liste")
    parser.add_argument("fichier", nargs="?", help="Chemin vers .xlsx/.csv (auto-detecte sinon)")
    parser.add_argument("--output", "-o", default=str(DEFAULT_DOWNLOADS), help="Dossier de sortie")
    parser.add_argument("--quality", default="192", help="Bitrate MP3 (defaut: 192)")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="Fichier de log des echecs")
    args = parser.parse_args()
    if args.fichier:
        source = Path(args.fichier)
    else:
        source = find_spreadsheet(BASE_DIR)
        if not source:
            print("Aucun .xlsx/.csv trouve dans", BASE_DIR)
            print("Usage: python download_music.py chemin/vers/fichier.xlsx")
            sys.exit(1)
    if not source.exists():
        print(f"Fichier introuvable: {source}")
        sys.exit(1)
    downloads = Path(args.output)
    downloads.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(args.log, encoding="utf-8"), logging.StreamHandler()],
    )
    try:
        tracks = load_tracks(source)
    except Exception as e:
        logging.error(f"Erreur lecture tableur: {e}")
        sys.exit(1)
    logging.info(f"{len(tracks)} morceaux trouves dans {source.name}")
    logging.info(f"Sortie: {downloads} | Qualite: {args.quality} kbps")
    success = skipped = failed = 0
    for artiste, titre in tracks:
        filename = sanitize_filename(f"{artiste} - {titre}")
        expected = downloads / f"{filename}.mp3"
        if expected.exists():
            logging.info(f"[SKIP] {filename}")
            skipped += 1
            continue
        try:
            download_track(artiste, titre, downloads, args.quality)
            logging.info(f"[OK] {filename}")
            success += 1
        except Exception as e:
            logging.error(f"[FAIL] {filename} | {e}")
            with open(args.log, "a", encoding="utf-8") as f:
                f.write(f"[FAIL] {artiste} - {titre} | query: {artiste} - {titre} Official Audio | erreur: {e}\n")
            failed += 1
    logging.info(f"Termine: {success} telecharges, {skipped} deja presents, {failed} echecs sur {len(tracks)}")


if __name__ == "__main__":
    main()
