/* youtube-audio-dl importer — content script (vanilla, sans build) */
(() => {
  "use strict";

  const clean = (s) => (s || "").replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim();

  // Artiste via aria-label "Écouter {titre} par {artiste}" du bouton play (Deezer)
  function artistFromAriaLabel(row) {
    if (!row || !row.querySelectorAll) return "";
    const btns = row.querySelectorAll("button[aria-label]");
    for (const b of btns) {
      const m = clean(b.getAttribute("aria-label")).match(/^(?:Écouter|Listen to|Play)\s+(.+)\s+(?:par|by)\s+(.+)$/);
      if (m && clean(m[2])) return clean(m[2]);
    }
    return "";
  }

  // Conteneur scrollable réel (listes virtualisées Deezer/Spotify)
  function scrollableAncestor(el) {
    let n = el && el.parentElement;
    while (n && n !== document.body) {
      try {
        const st = getComputedStyle(n);
        if ((st.overflowY === "auto" || st.overflowY === "scroll") && n.scrollHeight > n.clientHeight + 50) return n;
      } catch {}
      n = n.parentElement;
    }
    return null;
  }
  // Tous les liens "artiste" d'un conteneur (Spotify/Deezer : href .../artist/...)
  function artistsFrom(node) {
    if (!node || !node.querySelectorAll) return "";
    const arts = [...node.querySelectorAll('a[href*="/artist/"]')]
      .map((a) => clean(a.textContent)).filter((t) => t && t.length < 200);
    return [...new Set(arts)].join(", ");
  }

  function detectSource() {
    const h = location.hostname;
    if (h.includes("spotify.com")) return "spotify";
    if (h.includes("deezer.com")) return "deezer";
    if (h.includes("youtube.com")) return "ytmusic";
    return "page";
  }

  // Scroll par paliers + collecte à chaque pas (les listes virtualisées
  // montent/démonte les lignes : scraper seulement à la fin en perd).
  // collectFn() -> nombre de morceaux collectés jusqu'ici.
  async function scrollCollect(root, collectFn, maxRounds = 80, waitMs = 350) {
    const el = root || document.scrollingElement || document.documentElement;
    const step = () => Math.max(400, (el.clientHeight || 800) * 0.9);
    let last = -1, stable = 0, count = collectFn();
    for (let i = 0; i < maxRounds; i++) {
      el.scrollTop += step(); // un seul scroller : l'élément (ou la page si c'est lui)
      await new Promise((r) => setTimeout(r, waitMs));
      count = collectFn();
      if (count === last) { stable++; if (stable >= 4) break; }
      else { stable = 0; last = count; }
    }
    el.scrollTop = 0;
    return count;
  }

  function scrollRootFor(firstRowSel) {
    const firstRow = document.querySelector(firstRowSel);
    return (
      (firstRow && scrollableAncestor(firstRow)) ||
      document.querySelector('[data-testid="playlist-tracklist"]') ||
      document.querySelector("main") ||
      document.scrollingElement
    );
  }

  function dedupe(rows) {
    const seen = new Set(), out = [];
    for (const r of rows) {
      const a = clean(r.artiste), t = clean(r.titre);
      if (!a || !t) continue;
      const k = (a + "|" + t).toLowerCase();
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({ artiste: a.slice(0, 150), titre: t.slice(0, 150) });
    }
    return out;
  }

  // Écrit dans map (clé = aria-rowindex, stable pendant le scroll). Repli texte sinon.
  function collectSpotifyInto(map) {
    // Lignes officielles : titre = a[data-testid="internal-track-link"]
    document.querySelectorAll('div[data-testid="tracklist-row"]').forEach((row) => {
      const t = row.querySelector('a[data-testid="internal-track-link"]');
      const titre = clean(t && t.textContent);
      if (!titre || titre.length > 200) return;
      const artiste = artistsFrom(row);
      if (!artiste) return;
      const wrap = row.closest('[role="row"]');
      const key = (wrap && wrap.getAttribute("aria-rowindex")) || ("sp|" + artiste + "|" + titre).toLowerCase();
      if (!map.has(key)) map.set(key, { artiste: artiste.slice(0, 150), titre: titre.slice(0, 150) });
    });
    return map.size;
  }

  function scrapeSpotifyStatic() {
    const map = new Map();
    collectSpotifyInto(map);
    return map.size ? [...map.values()] : scrapeByLinks();
  }

  // Écrit dans map (clé = aria-rowindex, stable pendant le scroll). Repli texte sinon.
  function collectDeezerInto(map) {
    // Passe 1 (DOM réel Deezer : lignes role="row", titre = [data-testid="title"])
    document.querySelectorAll('[role="row"]').forEach((row) => {
      const t = row.querySelector('[data-testid="title"]');
      const titre = clean(t && t.textContent);
      if (!titre || titre.length > 200) return;
      const artiste = artistsFrom(row) || artistFromAriaLabel(row);
      if (!artiste) return;
      const key = row.getAttribute("aria-rowindex") || ("dz|" + artiste + "|" + titre).toLowerCase();
      if (!map.has(key)) map.set(key, { artiste: artiste.slice(0, 150), titre: titre.slice(0, 150) });
    });
    return map.size;
  }

  function scrapeDeezer() {
    const map = new Map();
    collectDeezerInto(map);
    if (map.size) return [...map.values()];
    const out = [];
    document.querySelectorAll('[data-testid="track-title"], .track-title').forEach((t) => {
      const row = t.closest("li, tr, div");
      const titre = clean(t.textContent);
      const artiste = artistsFrom(row || t.parentElement);
      if (titre && artiste) out.push({ artiste, titre });
    });
    if (out.length) return out;
    const byLinks = scrapeByLinks();
    if (byLinks.length) return byLinks;
    // Pages type "Coups de cœur" : lignes [role="row"]/li sans lien /track/.
    // Titre = ancre la plus longue de la ligne (ni artiste ni album) + artistes de la ligne.
    document.querySelectorAll('[role="row"], li').forEach((row) => {
      const artiste = artistsFrom(row);
      if (!artiste) return;
      const cands = [...row.querySelectorAll("a")]
        .filter((a) => {
          const h = a.getAttribute("href") || "";
          return !h.includes("/artist/") && !h.includes("/album/") && clean(a.textContent).length > 0;
        })
        .sort((x, y) => clean(y.textContent).length - clean(x.textContent).length);
      const titre = clean(cands[0] && cands[0].textContent);
      if (titre && artiste && titre !== artiste && titre.length < 200) out.push({ artiste, titre });
    });
    return out;
  }

  // Repli universel Spotify/Deezer : chaque lien .../track/... + artistes du conteneur parent
  function scrapeByLinks() {
    const out = [];
    document.querySelectorAll('a[href*="/track/"]').forEach((a) => {
      const titre = clean(a.textContent);
      if (!titre || titre.length > 200) return;
      let node = a.parentElement, artiste = "";
      for (let i = 0; i < 8 && node && node !== document.body; i++) {
        artiste = artistsFrom(node);
        if (artiste) break;
        node = node.parentElement;
      }
      if (titre && artiste) out.push({ artiste, titre });
    });
    return out;
  }

  // videoId stable pendant le scroll (clé de collecte YT Music)
  function ytmVideoId(cols) {
    for (const c of cols) {
      const a = c.querySelector ? c.querySelector('a[href*="watch"]') : null;
      const m = a && (a.getAttribute("href") || "").match(/[?&]v=([\w-]{6,})/);
      if (m) return m[1];
    }
    return "";
  }

  // Écrit dans map. Colonnes light DOM : [0] = titre, [1] = artiste(s), [2] = album.
  function collectYTMInto(map) {
    document.querySelectorAll("ytmusic-responsive-list-item-renderer").forEach((row) => {
      const cols = [...row.querySelectorAll(":scope yt-formatted-string")];
      if (cols.length < 2) return; // indisponible/supprimé : intéléchargeable de toute façon
      const titre = clean(cols[0].textContent);
      const artiste = clean(cols[1].textContent).split("•")[0];
      if (!titre || !artiste || titre.length > 200 || artiste.length > 200) return;
      const key = ytmVideoId(cols) || ("ytm|" + artiste + "|" + titre).toLowerCase();
      if (!map.has(key)) map.set(key, { artiste: artiste.slice(0, 150), titre: titre.slice(0, 150) });
    });
    return map.size;
  }

  function scrapeYTMusic() {
    const map = new Map();
    collectYTMInto(map);
    return [...map.values()];
  }

  async function scrape(withScroll = true) {
    const source = detectSource();
    const url = location.href;
    // Deezer/Spotify : collecte incrémentale pendant le scroll (lignes virtualisées)
    if (source === "deezer" || source === "spotify") {
      const map = new Map();
      const collect = source === "deezer" ? () => collectDeezerInto(map) : () => collectSpotifyInto(map);
      if (withScroll) {
        await scrollCollect(scrollRootFor('[role="row"], div[data-testid="tracklist-row"]'), collect);
      } else collect();
      let rows = [...map.values()];
      if (!rows.length) rows = source === "deezer" ? scrapeDeezer() : scrapeSpotifyStatic();
      return { source, url, tracks: dedupe(rows).slice(0, 2000) };
    }
    // YT Music : chargement par continuations -> collecte incrémentale + attente plus longue
    const ytmMap = new Map();
    if (withScroll) {
      await scrollCollect(
        scrollRootFor("ytmusic-responsive-list-item-renderer"),
        () => collectYTMInto(ytmMap),
        80, 600
      );
    } else collectYTMInto(ytmMap);
    const rows = source === "ytmusic" ? [...ytmMap.values()] : [];
    return { source, url, tracks: dedupe(rows).slice(0, 2000) };
  }

  // Sonde diagnostic : renvoie les compteurs de sélecteurs + un échantillon HTML
  // pour ajuster les scrapers au DOM réel du site.
  function diagnose() {
    const sels = [
      'div[data-testid="tracklist-row"]',
      'a[data-testid="internal-track-link"]',
      '[role="row"]',
      'a[href*="/track/"]',
      'a[href*="/artist/"]',
      'a[href*="/album/"]',
      '[data-testid="track-title"]',
      ".track-title",
      '[class*="title" i]',
      "ytmusic-responsive-list-item-renderer",
      "ytmusic-playlist-shelf-renderer",
      "yt-formatted-string",
      "a[href*=\"watch\"]",
      "main",
    ];
    const counts = {};
    sels.forEach((s) => {
      try { counts[s] = document.querySelectorAll(s).length; }
      catch { counts[s] = -1; }
    });
    let sample = "", chain = "";
    const first = document.querySelector(
      'a[data-testid="internal-track-link"], a[href*="/track/"], ytmusic-responsive-list-item-renderer, [role="row"]'
    );
    if (first) {
      sample = (first.outerHTML || "").slice(0, 1500);
      const tags = [];
      let n = first;
      for (let i = 0; i < 6 && n && n !== document.body; i++) {
        let cls = "";
        if (typeof n.className === "string" && n.className.trim())
          cls = "." + n.className.trim().split(/\s+/).slice(0, 3).join(".");
        tags.push(n.tagName.toLowerCase() + (n.id ? "#" + n.id : "") + cls);
        n = n.parentElement;
      }
      chain = tags.join(" < ");
    }
    return { url: location.href, source: detectSource(), counts, sample, chain };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg && msg.type === "YADL_SCRAPE") {
      scrape(msg.scroll !== false).then(reply);
      return true;
    }
    if (msg && msg.type === "YADL_DIAG") {
      try { reply(diagnose()); } catch (e) { reply({ error: String(e) }); }
      return true;
    }
  });

  window.__YADL = { scrape };
})();
