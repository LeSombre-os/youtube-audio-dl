# youtube-audio-dl

Télécharge des audios YouTube en MP3 depuis une liste `Artiste - Titre`. Interface web locale (sans build) + CLI. Recherche `Artiste - Titre Official Audio` via `yt-dlp` + conversion `ffmpeg`.

## Fonctionnalités

- **App web** : drag & drop `.xlsx`/`.csv`/`.txt`, collage `Artiste - Titre`, qualité 192/256/320 kbps, progression SSE temps réel, **pause / arrêter / reprendre**, reconnexion auto, lecture audio intégrée, dark/light, ZIP
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

Double-clic sur **`lancer.bat`** (terminal visible) ou **`lancer-sans-fenetre.vbs`** (silencieux). Ouvre `http://127.0.0.1:8000` automatiquement. Un 2ᵉ double-clic réutilise le moteur déjà lancé au lieu d'en créer un autre.

### Avec terminal

```bash
python app.py                 # http://127.0.0.1:8000
python app.py --port 9000
python app.py --no-browser
python app.py --silent        # autostart : ni navigateur, ni messages
```

### Démarrage automatique (optionnel)

Le moteur peut tourner en fond dès l'ouverture de session — ensuite l'extension suffit, plus rien à lancer :

- **Linux** : copie `Youtube Audio DL.desktop` dans `~/.config/autostart/`, puis édite la copie : `Exec=/chemin/absolu/vers/lancer.sh --silent` (le mode `--silent` n'ouvre ni terminal ni navigateur)
- **Windows** : `Win+R` → `shell:startup` → copie `lancer-sans-fenetre.vbs` dedans (aucune fenêtre ; un onglet s'ouvre une fois par session, ferme-le, le moteur reste en fond)

Pastille 🔴 dans la popup ? Ouvre le raccourci une fois, ou vérifie la carte **Diagnostic** de l'app (bouton 📋 pour copier l'état du moteur).

### CLI (avancé / dépannage — l'app web suffit en usage normal)

```bash
python download_music.py                          # auto-détecte .xlsx/.csv
python download_music.py playlist.xlsx --quality 320
python download_music.py playlist.csv -o ./out
```

## Usage quotidien (extension)

Principe : tu captures une playlist dans le navigateur, l'app se remplit toute seule, tu cliques **Lancer**.

**Première fois uniquement** : `brave://extensions` → mode développeur → **Charger `extension/`** → épingle l'icône ⬇️ → **recharge (F5)** les onglets de playlists déjà ouverts, sinon l'extension ne les voit pas.

### Spotify

1. Ouvre une **playlist** ou un **album** (`open.spotify.com/playlist/...` ou `/album/...`). L'accueil et la recherche ne donnent rien.
2. Icône ⬇️ → pastille 🟢 = moteur prêt → **🔍 Capturer** (scroll auto, ~10-30 s pour 100 titres) → l'aperçu affiche les 10 premiers.
3. **Envoyer** → `✅ N titres envoyés` → l'onglet de l'app s'ouvre (ou bascule dessus) avec la liste déjà remplie → **Lancer**.
4. Si l'onglet de l'app était déjà ouvert : bascule dessus, la liste s'y remplit toute seule au retour sur l'onglet.

### Deezer

Même flux que Spotify. Fonctionne sur **playlists**, **albums** et **Coups de cœur** (`deezer.com/.../playlist/...`, `/album/...`). Même remarque F5 après installation de l'extension.

### YouTube Music

Même flux, avec 2 différences : la page est plus lourde, donc **attends son chargement complet** avant de capturer, et la capture dure plus longtemps (défilement ralenti pour laisser charger les morceaux). URL type : `music.youtube.com/playlist?list=...`.

### Sans extension (manuel)

Colle des lignes `Artiste - Titre` dans la zone de texte, ou glisse un `.xlsx` / `.csv` / `.txt` dans la zone de dépôt (exemple : `exemple-playlist.txt`). Choisis la qualité → **Lancer**. Suivi : barre globale + tableau par morceau + lecture audio dès que disponible. Récupère via **📂 Dossier** ou **📦 ZIP**.

### Contrôles pendant un téléchargement

- **⏸️ Pause** : le morceau en cours finit, puis tout se suspend (badge ⏸️, chrono gelé). Reclique (▶️) pour reprendre où ça en était.
- **⏹️ Arrêter** : stoppe au point de contrôle suivant (fin de la recherche en cours, quelques secondes max, ou immédiat en plein morceau — le partiel est jeté). Le bouton attend l'arrêt réel avant de libérer **Lancer** : pas de « tourne en fond » fantôme. Les morceaux ✅/⏭️ sont gardés : **relance la même liste pour reprendre**, le skip auto saute ce qui est déjà là.
- **Fermer l'onglet** n'arrête rien : le moteur finit en fond. Rouvre la page : elle se reconnecte et rejoue la progression.
- Statuts : 🔍 recherche → ✅ OK / ⏭️ skip (déjà présent) / ❌ échec (détail au survol + journal) / ⏸️ pause / ⏹️ arrêté.

### Format

- **Fichier** : `.xlsx`/`.csv`/`.txt` avec colonnes `Artiste` / `Titre` (détection par nom, ordre indifférent, `Titre du morceau`/`Title` acceptés)
- **Texte** : `Artiste - Titre` par ligne, séparateurs ` - ` ` – ` ` — ` ` | ` `;` `,`

```
PERXLOM - lunacy (Slowed)
SXCREDMANE - byebye.wav - Slowed
DudePlaya - DYSTOPIA
```

L'import extension est à usage unique : la liste est vide à chaque réouverture de l'app (pas de vieux résidu). Astuce LLM : copie `PROMPT.md` vers ChatGPT/Claude pour formatter une liste brute (bouton **📋 Copier prompt** dans l'app).

### Podcasts

Oui, si le podcast est sur **YouTube** : colle `Nom du podcast - Titre de l'épisode` par ligne, même flux que la musique. Les longues durées sont acceptées quand le titre contient `podcast`, `épisode`/`episode`, `émission`, `interview` ou `documentaire` (sinon les vidéos de 30 min+ sont écartées comme compilations). Non supporté : flux RSS pur, podcasts exclusifs Spotify/Apple (pas de flux audio accessible).

## Structure

```
youtube-audio-dl/
├── app.py              # serveur web (stdlib, SSE)
├── index.html          # UI
├── download_music.py   # cœur yt-dlp
├── PROMPT.md           # prompt LLM (formateur CSV)
├── exemple-playlist.txt# exemple Artiste - Titre
├── extension/          # extension Brave/Chrome MV3 (sans build)
├── downloads/          # MP3 (ignoré par git, .gitkeep fourni)
├── lancer.bat / lancer.sh / lancer-sans-fenetre.vbs / maj.bat / maj.sh
├── Youtube Audio DL.desktop  # lanceur Linux portable (+ autostart si copié dans ~/.config/autostart/)
├── LICENSE             # MIT
└── requirements.txt    # yt-dlp + openpyxl (plus de pandas)
```

## En cas de problème (technique)

Lecture : symptôme → cause probable → remède. La carte **Diagnostic** en bas du panneau gauche de l'app (bouton 📋) copie l'état du moteur — utile pour demander de l'aide.

### Côté extension

- **Pastille 🔴 / « App fermée »** → le moteur ne tourne pas. Ouvre le raccourci une fois (ou active le démarrage auto). Vérifie aussi que le port est entre 8000 et 8020 : l'extension ne sonde que cette plage.
- **« Envoi impossible (serveur injoignable) »** → le moteur a redémarré ailleurs entre la capture et l'envoi. La popup re-sonde et retente une fois toute seule ; si ça persiste, rouvre le raccourci puis reclique **Envoyer** (la capture est conservée dans la popup, pas besoin de rescanner).
- **« Envoi impossible (Aucun morceau valide…) »** → la page a changé de structure et la capture est vide ou mal formée. Ouvre la popup → **🛠️ Diag** (compteurs copiés) et transmets le résultat.
- **« ❌ rien trouvé » après capture** → attends le chargement complet de la playlist, vérifie que c'est bien une URL playlist/album (pas accueil/recherche), F5 puis re-capture. Sur YT Music, laisse plus de temps.
- **L'app ne se remplit pas alors que `✅ N titres envoyés`** → bascule sur l'onglet de l'app (remplissage au retour sur l'onglet) ou recharge-le. En dernier recours : **Copier** ou **.txt** dans la popup, colle dans l'app.
- **L'extension ne voit pas la page** (« recharge la page » en boucle) → supprime-la de `brave://extensions`, recharge-la depuis `extension/`, **F5** sur la playlist.

### Côté téléchargement

- Démarrage impossible → l'app dit exactement ce qui manque (Python 3.10+, ffmpeg, dépendances) avec la commande à lancer.
- `403 Forbidden` → double-clic `maj.bat` / `./maj.sh` (met à jour `yt-dlp`, cause n°1 quand YouTube change son site)
- Port occupé → relance simplement : le moteur réutilise l'instance existante ou prend le port libre suivant (8000→8020). Si tu forces `--port`, reste dans **8000-8020** pour que l'extension trouve le moteur.
- **« Un téléchargement tourne déjà » (409)** → un seul run à la fois : mets-le en pause ou arrête-le depuis l'onglet qui l'a lancé (ou recharge la page : elle se reconnecte au run en cours).
- **Mauvais morceau téléchargé** → la recherche compare les 8 premiers résultats (titre exact > remix/cover/live/compilations, bonus piste "Official Audio"). Si le bon n'y est toujours pas, renomme `Artiste - Titre` au plus proche du titre YouTube et relance.
- **« aucun résultat » sur des titres obscurs** → 3 requêtes de repli automatiques (`A - T Official Audio`, puis `A - T`, puis `T` seul). Les fins de noms de fichiers (`.mp3`, `.Exe`) et tirets parasites sont nettoyés avant recherche.
- **HTTP 503 en fin de grosse liste** → YouTube ralentit après ~150 requêtes enchaînées (pauses + 10 essais auto ajoutés). Attends quelques minutes puis **relance la même liste** : les OK sont skippés, seuls les échecs sont repris.
- **« Sign in to confirm you're not a bot » en masse** → YouTube a classé ton IP en bot. Remède :
  1. Dans Brave, installe l'extension **Get cookies.txt LOCALLY** → exporte les cookies de `youtube.com`
  2. Enregistre le fichier sous `youtube-audio-dl/cookies.txt` (à côté de `app.py`, jamais partagé — déjà ignoré par git)
  3. Relance l'app : cookies repris automatiquement pour la recherche + le téléchargement
  4. Alternative CLI : `python download_music.py playlist.xlsx --cookies cookies.txt` ou `--cookies-from-browser brave`
  5. Relance ta liste : les OK sont skippés, seuls les échecs repartent
- **OK sans son / skip fantôme** → les MP3 < 50 Ko sont considérés comme corrompus : affichés en échec (pas OK) et re-téléchargés au lieu d'être skippés. `skip` = fichier valide déjà présent, c'est normal.

## Licence

MIT — voir `LICENSE`.

## Usage personnel

Outil pour ton usage personnel : le téléchargement d'audios YouTube est soumis à ses CGU (pas de contournement DRM, `yt-dlp` seul). Le serveur n'écoute que sur `127.0.0.1` et refuse les sites tiers (contrôle d'origine) : garde-le en local, ne l'expose pas sur le réseau.
