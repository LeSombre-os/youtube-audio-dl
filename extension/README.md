# Extension youtube-audio-dl importer (Brave / Chrome MV3)

Capture les `Artiste - Titre` d'une playlist **Deezer / Spotify / YouTube Music** et envoie vers l'app locale.

## Installation (Brave)

1. Lance le moteur une fois (raccourci ou `python app.py`). La popup affiche 🟢 quand il répond — plus besoin de garder l'onglet ouvert.
2. Va sur `brave://extensions` → active **Mode développeur** (en haut à droite).
3. **Charger l'extension non empaquetée** → sélectionne ce dossier `extension/`.
4. Épingle l'icône ⬇️ dans la barre d'outils.

Aucun build, aucune dépendance, aucune donnée externe : tout reste en local.

## Usage

**Étape 1 — le moteur** : ouvre la popup → 🟢 = prêt. Si 🔴, ouvre le raccourci une fois (ou active le démarrage auto, voir README principal).
```bash
cd youtube-audio-dl
python app.py
```
Un 2ᵉ lancement réutilise le moteur existant au lieu d'en créer un autre.

**Étape 2 — ouvre une playlist dans Brave**, par exemple :
- Spotify : `https://open.spotify.com/playlist/...` (ou un album)
- Deezer : `https://www.deezer.com/fr/playlist/...` (ou un album)
- YouTube Music : `https://music.youtube.com/playlist?list=...`

⚠️ **Après avoir installé l'extension, recharge l'onglet de la playlist (F5)** : sans ça, l'extension ne voit pas la page déjà ouverte et ne détecte rien. La popup doit afficher `✅ ... détecté`.

**Étape 3 — capture** : icône de l'extension → **🔍 Capturer** → **Envoyer** (`✅ N titres envoyés` ; en cas d'échec réseau la popup retente une fois après re-sonde — reclique sinon, la capture est conservée).
4. L'onglet de l'app s'ouvre avec la liste pré-remplie (ou se remplit au retour dessus s'il était déjà ouvert) → **Lancer**.

YouTube Music : page plus lourde, attends son chargement complet et prévois une capture plus longue.

## Dépannage

- `❌ rien trouvé` → attends le chargement complet de la playlist, re-capture (le scroll auto charge les listes virtualisées). Vérifie aussi que tu es bien sur une URL playlist/album (pas l'accueil ni la recherche).
- Si ça persiste : ouvre la popup → **🛠️ Diag** → le diagnostic est copié, envoie-le au développeur (il contient les compteurs de sélecteurs, aucun mot de passe).
- Pastille 🔴 (`Moteur éteint`) → lance le raccourci une fois, puis reclique **Envoyer** (ta capture est conservée). Sinon fallback Copier/.txt.
- Port personnalisé → l'extension ne sonde que **8000→8020** : reste dans cette plage en usage extension (`--port 9000` la rend invisible pour la popup).
- Sélecteurs cassés après un redesign du site → ouvre un ticket avec l'URL + une capture.
