# youtube-audio-dl

Télécharge des audios YouTube en MP3 depuis une liste `Artiste - Titre`. Interface web locale (sans build) + CLI. Recherche `Artiste - Titre Official Audio` via `yt-dlp` + conversion `ffmpeg`.

## Fonctionnalités

- **App web** : drag & drop `.xlsx`/`.csv`, collage `Artiste - Titre`, qualité 192/256/320 kbps, progression SSE temps réel, lecture audio intégrée, dark/light, ZIP
- **CLI** : `python download_music.py playlist.xlsx`
- **LLM** : prompt `PROMPT.md` pour formatter une liste brute en CSV
- Fichiers existants = skip automatique

## Prérequis

- Python 3.10+
- ffmpeg dans le PATH (`ffmpeg -version` doit répondre)
- pip

```bash
# ffmpeg — Windows
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Linux
sudo apt update && sudo apt install ffmpeg
```

## Installation

```bash
git clone https://github.com/<user>/youtube-audio-dl.git
cd youtube-audio-dl
pip install -r requirements.txt
```

## Lancement

### Sans terminal (Windows)

Double-clic sur **`lancer.bat`** (terminal visible) ou **`lancer-sans-fenetre.vbs`** (silencieux). Ouvre `http://127.0.0.1:8000` automatiquement.

### Avec terminal

```bash
python app.py                 # http://127.0.0.1:8000
python app.py --port 9000
python app.py --no-browser
```

### CLI

```bash
python download_music.py                          # auto-détecte .xlsx/.csv
python download_music.py playlist.xlsx --quality 320
python download_music.py playlist.csv -o ./out
```

## Utilisation

1. **Copie** `PROMPT.md` vers ChatGPT/Claude pour formatter une liste, **ou** dépose un `.xlsx/.csv`, **ou** colle `Artiste - Titre` par ligne dans la zone de texte
2. Choisis la qualité → **Lancer**
3. Suivi : barre globale + tableau par morceau (🔍 recherche → ✅ OK / ⏭️ skip / ❌ échec) + player audio dès que disponible
4. Récupère via **📂 Dossier** ou **📦 ZIP**

### Format

- **Fichier** : `.xlsx/.xls/.csv` avec colonnes `Artiste` / `Titre` (détection par nom, ordre indifférent, `Titre du morceau`/`Title` acceptés)
- **Texte** : `Artiste - Titre` par ligne, séparateurs ` - ` ` – ` ` — ` ` | ` `;` `,`

```
PERXLOM - lunacy (Slowed)
SXCREDMANE - byebye.wav - Slowed
DudePlaya - DYSTOPIA
```

## Structure

```
youtube-audio-dl/
├── app.py              # serveur web (stdlib, SSE)
├── index.html          # UI
├── download_music.py   # cœur yt-dlp
├── PROMPT.md           # prompt LLM (formateur CSV)
├── downloads/          # MP3 (ignoré par git)
├── lancer.bat          # double-clic Windows
├── lancer-sans-fenetre.vbs
└── requirements.txt
```

## Dépannage

- `ffmpeg not found` → installer ffmpeg et rouvrir le terminal
- `403 Forbidden` → `pip install -U yt-dlp` (client `android` déjà configuré)
- Port occupé → `python app.py --port 9000` (auto-détection sur 20 ports)

## Licence

MIT
