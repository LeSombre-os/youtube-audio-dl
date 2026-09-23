/* Popup : capture via content.js, envoi direct localhost + fallback clipboard/.txt */
const $ = (s) => document.querySelector(s);
let data = null, port = null;

const SUPPORTED = ["open.spotify.com", "deezer.com", "music.youtube.com"];

async function activeTab() {
  const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
  return t;
}

// Diagnostic immédiat : dit si l'onglet actuel est une page supportée
(async () => {
  try {
    const tab = await activeTab();
    const u = new URL(tab.url);
    const ok = SUPPORTED.some((h) => u.hostname === h || u.hostname.endsWith("." + h));
    if (ok) $("#src").textContent = `✅ ${u.hostname} détecté — clique Capturer.`;
    else {
      $("#src").textContent = `❌ Page non supportée (${u.hostname}). Ouvre une playlist Deezer / Spotify / YT Music.`;
      $("#cap").disabled = true;
    }
  } catch {
    $("#src").textContent = "Ouvre une playlist Deezer / Spotify / YT Music.";
  }
})();

async function findPort() {
  try {
    const s = await chrome.storage.local.get("yadl_port");
    if (s.yadl_port) {
      try {
        const r = await fetch(`http://127.0.0.1:${s.yadl_port}/api/health`);
        if (r.ok) return s.yadl_port;
      } catch {}
    }
  } catch {}
  // ponytail: scan parallele (~0.6s) au lieu de sequentiel (~10s pire cas)
  const probe = (p) => fetch(`http://127.0.0.1:${p}/api/health`, { signal: AbortSignal.timeout(600) })
    .then((r) => (r.ok ? p : Promise.reject()));
  try {
    const winner = await Promise.any(Array.from({ length: 21 }, (_, i) => probe(8000 + i)));
    try { await chrome.storage.local.set({ yadl_port: winner }); } catch {}
    return winner;
  } catch { return null; }
}

// Pastille moteur : verte si le serveur local répond, rouge sinon.
// L'app s'ouvre toute seule à l'envoi réussi : aucun bouton d'ouverture séparé.
(async () => {
  const p = await findPort();
  port = p;
  $("#engine").textContent = p
    ? `🟢 Moteur prêt (:${p})`
    : "🔴 Moteur éteint — lance le raccourci Youtube Audio DL, puis reclique Envoyer.";
})();

const toText = () => data.tracks.map((t) => `${t.artiste} - ${t.titre}`).join("\n");

function render() {
  if (!data) return;
  $("#src").textContent = `${data.source} · ${data.tracks.length} titres`;
  $("#status").textContent = data.tracks.length
    ? (port ? `✅ App trouvée (:${port}) — prêt à envoyer.` : `🔴 Moteur éteint — lance le raccourci, puis Envoyer.`)
    : "❌ Rien trouvé. Lance la playlist puis re-capture (scroll auto inclus).";
  const pv = $("#preview");
  pv.hidden = !data.tracks.length;
  pv.textContent = data.tracks.slice(0, 10).map((t) => `${t.artiste} - ${t.titre}`).join("\n")
    + (data.tracks.length > 10 ? `\n… +${data.tracks.length - 10}` : "");
  $("#send").disabled = $("#copy").disabled = $("#dl").disabled = !data.tracks.length;
}

$("#cap").onclick = async () => {
  $("#status").textContent = "⏳ capture + scroll auto…";
  try {
    const tab = await activeTab();
    data = await chrome.tabs.sendMessage(tab.id, { type: "YADL_SCRAPE", scroll: true });
    port = await findPort();
    render();
  } catch {
    $("#status").textContent = "❌ Ouvre une playlist Deezer / Spotify / YT Music puis recharge la page.";
  }
};

async function postImport(p) {
  let r;
  try {
    r = await fetch(`http://127.0.0.1:${p}/api/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    const t = new Error("serveur injoignable");
    t.retryable = true; // réseau/timeout : le port en cache est peut-être périmé
    throw t;
  }
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.error || `HTTP ${r.status}`); // refus serveur : inutile de réessayer
  }
  return r.json();
}

$("#send").onclick = async () => {
  if (!data || !data.tracks.length) return;
  const btn = $("#send");
  btn.disabled = true;
  $("#status").textContent = "⏳ envoi vers l'app…";
  try {
    port = port || await findPort();
    if (!port) { $("#status").textContent = "🔴 Moteur éteint — lance le raccourci Youtube Audio DL, puis reclique Envoyer (ou Copier/.txt en attendant)."; return; }
    let j;
    try {
      j = await postImport(port);
    } catch (e) {
      if (!e.retryable) throw e;
      // Port en cache périmé (serveur relancé ailleurs) : re-sonde puis 2ᵉ tentative.
      port = await findPort();
      if (!port) { $("#status").textContent = "🔴 Moteur éteint — lance le raccourci Youtube Audio DL, puis reclique Envoyer (ou Copier/.txt en attendant)."; return; }
      j = await postImport(port);
    }
    $("#status").textContent = `✅ ${j.count} titres envoyés — bascule sur l'onglet app.`;
    await openApp(port);
  } catch (e) {
    $("#status").textContent = `❌ Envoi impossible (${e.message || "réseau"}) — copie la liste.`;
  } finally {
    btn.disabled = !data.tracks.length;
  }
};

// Bascule sur l'onglet app s'il existe déjà, sinon l'ouvre (fini les doublons)
async function openApp(port, note = " La liste est déjà dans l'app.") {
  try {
    const tabs = await chrome.tabs.query({ url: "http://127.0.0.1/*" });
    const hit = tabs.find((t) => {
      try { const u = new URL(t.url); return u.hostname === "127.0.0.1" && u.port === String(port); }
      catch { return false; }
    });
    if (hit) {
      await chrome.tabs.update(hit.id, { active: true });
      await chrome.windows.update(hit.windowId, { focused: true });
      $("#status").textContent += note;
      return;
    }
  } catch {}
  chrome.tabs.create({ url: `http://127.0.0.1:${port}/?import=1` }); // auto-remplit, usage unique
}

$("#copy").onclick = async () => {
  await navigator.clipboard.writeText(toText());
  $("#status").textContent = "📋 Copié — colle dans le textarea de l'app.";
};

$("#dl").onclick = () => {  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  const name = `playlist-${data.source}-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.txt`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([toText()], { type: "text/plain;charset=utf-8" }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
  $("#status").textContent = "💾 .txt téléchargé — glisse-le dans l'app.";
};

$("#diag").onclick = async () => {
  $("#status").textContent = "⏳ analyse de la page…";
  try {
    const tab = await activeTab();
    const d = await chrome.tabs.sendMessage(tab.id, { type: "YADL_DIAG" });
    const lines = Object.entries(d.counts || {}).map(([s, n]) => `${n} × ${s}`);
    const pv = $("#preview");
    pv.hidden = false;
    pv.textContent = [d.source + " · " + d.url, "", ...lines, "", "Parents : " + (d.chain || "?")].join("\n");
    await navigator.clipboard.writeText(JSON.stringify(d)).catch(() => {});
    $("#status").textContent = "📋 Diagnostic copié — colle-le moi pour que j'ajuste les sélecteurs.";
  } catch {
    $("#status").textContent = "❌ Recharge la page (F5) puis re-clique Diag.";
  }
};
