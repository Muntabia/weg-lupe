"use strict";
// WEG-Lupe Oberfläche. Bewusst ohne Framework und ohne Build-Schritt.

const $ = (s, el = document) => el.querySelector(s);
const state = { meta: null, objects: [], current: null, data: null, findings: [], sev: new Set(["hoch", "mittel"]), pollTimer: null };

const SEV_LABEL = { hoch: "Hoch", mittel: "Nachfragen", info: "Info" };
const FIG_LABEL = {
  ruecklage_stand: "Rücklage (Stand)", ruecklage_zufuehrung: "Rücklage: Zuführung", ruecklage_entnahme: "Rücklage: Entnahme", hausgeld: "Hausgeld",
};

// ---------- Hilfsfunktionen ----------
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function eur(v, digits = 0) { return v == null || isNaN(v) ? "–" : v.toLocaleString("de-DE", { maximumFractionDigits: digits, minimumFractionDigits: digits }) + " €"; }
function num(v) {
  if (v == null) return null;
  const s = String(v).trim();
  if (!s) return null;
  if (s.includes("/")) { const [a, b] = s.split("/").map(x => parseFloat(x.replace(/\./g, "").replace(",", "."))); return b ? a / b : null; }
  const n = parseFloat(s.replace(/\s/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", "."));
  return isNaN(n) ? null : n;
}
function toast(msg, ms = 3500) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), ms); }
async function api(path, opts = {}) {
  const o = { ...opts, headers: { ...(opts.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers["Content-Type"] = "application/json"; delete o.json; }
  const r = await fetch(path, o);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}
function md(src) {
  const out = []; let list = false;
  for (const raw of (src || "").split("\n")) {
    let line = esc(raw.trimEnd()).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (/^\s*[-*] /.test(line)) { if (!list) { out.push("<ul>"); list = true; } out.push("<li>" + line.replace(/^\s*[-*] /, "") + "</li>"); continue; }
    if (list) { out.push("</ul>"); list = false; }
    const h = line.match(/^(#{1,4}) (.*)/);
    if (h) out.push(`<h3>${h[2]}</h3>`); else if (line.trim()) out.push(`<p>${line}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("");
}
function snippetHtml(s) { return esc(s).replace(/\x01/g, "<mark>").replace(/\x02/g, "</mark>"); }
function docLabel(d) { return `${state.meta.doc_types[d.doc_type] || d.doc_type}${d.doc_year ? " " + d.doc_year : ""}`; }

// ---------- Objekte ----------
async function loadObjects() {
  state.objects = await api("/api/objects");
  const ul = $("#objList");
  ul.innerHTML = state.objects.map(o => `<li data-id="${o.id}" class="${o.id === state.current ? "active" : ""}">
    <span>${esc(o.name)}</span>${o.high_count ? `<span class="cnt" title="Befunde mit hoher Relevanz">${o.high_count} hoch</span>` : ""}</li>`).join("")
    || `<li class="muted" style="cursor:default">Noch keine Objekte</li>`;
  $("#emptyState").hidden = state.objects.length > 0 && state.current != null;
  if (!state.objects.length) { $("#objView").hidden = true; $("#emptyState").hidden = false; }
}

async function createObject() {
  const name = prompt("Name des Objekts (z. B. „Musterstraße 12, 3. OG links“):");
  if (!name) return;
  const o = await api("/api/objects", { method: "POST", json: { name } });
  await loadObjects();
  openObject(o.id, true);
}

async function openObject(id, editForm = false) {
  state.current = id;
  try { localStorage.setItem("weglupe.obj", id); } catch { }
  $("#sidebar").classList.remove("open");
  $("#emptyState").hidden = true;
  $("#settingsView").hidden = true;
  $("#objView").hidden = false;
  $("#searchResults").innerHTML = ""; $("#searchInput").value = "";
  await refresh();
  document.querySelectorAll("#objList li").forEach(li => li.classList.toggle("active", +li.dataset.id === id));
  if (editForm) showObjForm(true);
}

async function refresh() {
  if (state.current == null) return;
  const [data, findings] = await Promise.all([
    api(`/api/objects/${state.current}`),
    api(`/api/objects/${state.current}/findings?include_dismissed=${$("#showDismissed").checked}`),
  ]);
  state.data = data; state.findings = findings;
  renderHead(); renderKpis(); renderSummary(); renderDocs(); renderFindings(); renderFigures();
  schedulePoll();
}

function isBusy() {
  const d = state.data; if (!d) return false;
  const docBusy = d.documents.some(x => ["wartet", "liest"].includes(x.status) || x.ai_status === "wartet" || (x.ai_status || "").startsWith("läuft"));
  const sumBusy = d.summary && ["wartet", "läuft"].includes(d.summary.status);
  return docBusy || sumBusy;
}
function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (isBusy()) state.pollTimer = setTimeout(async () => { await refresh(); if (!isBusy()) loadObjects(); }, 2500);
}

// ---------- Kopf & Stammdaten ----------
function renderHead() {
  const o = state.data.object;
  $("#objName").textContent = o.name;
  $("#objAddr").textContent = o.address || "";
  $("#reportBtn").href = `/api/objects/${o.id}/report`;
}
function showObjForm(show) {
  const f = $("#objForm"); f.hidden = !show; if (!show) return;
  const o = state.data.object;
  for (const k of ["name", "address", "notes"]) f.elements[k].value = o[k] || "";
  for (const k of ["total_area_m2", "unit_area_m2", "price_eur"]) f.elements[k].value = o[k] != null ? String(o[k]).replace(".", ",") : "";
  f.elements.mea_share.value = o.mea_share != null ? String(o.mea_share).replace(".", ",") : "";
  f.elements.name.focus();
}
async function saveObjForm(ev) {
  ev.preventDefault();
  const f = ev.target;
  const body = {
    name: f.elements.name.value.trim(), address: f.elements.address.value.trim(), notes: f.elements.notes.value,
    total_area_m2: num(f.elements.total_area_m2.value), unit_area_m2: num(f.elements.unit_area_m2.value),
    mea_share: num(f.elements.mea_share.value), price_eur: num(f.elements.price_eur.value),
  };
  if (body.mea_share != null && body.mea_share > 1) { toast("Miteigentumsanteil bitte als Bruch angeben, z. B. 85/10000."); return; }
  await api(`/api/objects/${state.current}`, { method: "PUT", json: body });
  showObjForm(false); toast("Gespeichert"); await loadObjects(); await refresh();
}

// ---------- Kennzahlen oben ----------
function latestChosen(kind) {
  return state.data.figures.filter(f => f.kind === kind && f.chosen).sort((a, b) => (b.year || 0) - (a.year || 0))[0];
}
function renderKpis() {
  const d = state.data, o = d.object;
  const cnt = s => d.counts.filter(c => c.severity === s).reduce((a, c) => a + c.n, 0);
  const pages = d.documents.reduce((a, x) => a + (x.pages || 0), 0);
  const tiles = [
    { cls: "hoch", label: "Hohe Relevanz", value: cnt("hoch"), sub: "Befunde" },
    { cls: "mittel", label: "Nachfragen", value: cnt("mittel"), sub: "Befunde" },
    { label: "Unterlagen", value: d.documents.length, sub: `${pages} Seiten` },
  ];
  const rl = latestChosen("ruecklage_stand");
  if (rl) {
    const perM2 = o.total_area_m2 ? rl.value_eur / o.total_area_m2 : null;
    const own = o.mea_share ? rl.value_eur * o.mea_share : null;
    tiles.push({ label: `Rücklage${rl.year ? " " + rl.year : ""}`, value: eur(rl.value_eur),
      sub: [perM2 != null ? `${eur(perM2, 2)}/m² WEG` : "Gesamtfläche fehlt", own != null ? `dein Anteil ≈ ${eur(own)}` : ""].filter(Boolean).join(" · ") });
  } else {
    tiles.push({ label: "Rücklage", value: "–", sub: "unten bei Kennzahlen bestätigen" });
  }
  const zf = latestChosen("ruecklage_zufuehrung");
  if (zf && o.total_area_m2) tiles.push({ label: `Zuführung${zf.year ? " " + zf.year : ""}`, value: `${eur(zf.value_eur / o.total_area_m2, 2)}`, sub: "pro m² und Jahr" });
  const su = state.findings.filter(f => f.category === "Sonderumlage" && f.amount_eur && !f.dismissed && f.verified && f.severity !== "info");
  if (su.length) {
    const max = Math.max(...su.map(f => f.amount_eur));
    tiles.push({ cls: "hoch", label: "Größte genannte Sonderumlage", value: eur(max),
      sub: o.mea_share ? `dein Anteil ≈ ${eur(max * o.mea_share)} (Schätzung nach MEA)` : "MEA eintragen für deinen Anteil" });
  }
  $("#kpis").innerHTML = tiles.map(t => `<div class="kpi ${t.cls || ""}"><div class="label">${esc(t.label)}</div><div class="value">${esc(t.value)}</div><div class="sub">${esc(t.sub || "")}</div></div>`).join("");
}

// ---------- KI-Zusammenfassung ----------
function renderSummary() {
  const s = state.data.summary, body = $("#summaryBody"), btn = $("#aiBtn"), meta = $("#summaryMeta");
  const docsReady = state.data.documents.some(d => d.status === "fertig");
  if (!state.meta.llm_enabled) {
    btn.hidden = true; meta.textContent = "";
    body.innerHTML = `<div class="notice">Keine KI eingerichtet. Die Stichwort-Prüfung unten funktioniert trotzdem.
      Für eine Einschätzung mit Fragen an den Verkäufer wähle unter <button type="button" class="linkish" data-open-settings>Einstellungen</button> einen KI-Anbieter.</div>`;
    return;
  }
  btn.hidden = false;
  const running = s && ["wartet", "läuft"].includes(s.status);
  const aiDocsRunning = state.data.documents.some(d => d.ai_status === "wartet" || (d.ai_status || "").startsWith("läuft"));
  btn.disabled = running || aiDocsRunning || !docsReady;
  btn.textContent = s && s.text ? "Neu analysieren" : "KI-Analyse starten";
  if (aiDocsRunning || running) {
    const d = state.data.documents.find(x => (x.ai_status || "").startsWith("läuft"));
    meta.textContent = d ? `KI liest ${d.filename} (${d.ai_status.replace("läuft ", "Abschnitt ")}) …` : "KI schreibt die Einschätzung …";
  } else if (s && s.status && s.status.startsWith("fehler")) {
    meta.textContent = "";
    body.innerHTML = `<div class="notice" style="color:var(--hoch)">${esc(s.status)}</div>` + (s.text ? md(s.text) : "");
    return;
  } else meta.textContent = s && s.text ? `${s.model} · ${s.created_at}` : "";
  if (s && s.text) body.innerHTML = md(s.text);
  else if (!running && !aiDocsRunning) body.innerHTML = `<div class="notice">${docsReady ? "Die KI liest alle Unterlagen, prüft jedes Zitat gegen das Dokument und schreibt eine Einschätzung mit Fragen an den Verkäufer." : "Lade zuerst Unterlagen hoch."}</div>`;
  else body.innerHTML = "";
}
async function startAi() {
  const redo = !!(state.data.summary && state.data.summary.text);
  if (redo && !confirm("Alle Unterlagen erneut durch die KI prüfen? (Kostet bei Cloud-KI erneut API-Guthaben.)\n\nAbbrechen = nur neue Unterlagen prüfen und Einschätzung neu schreiben.")) {
    await api(`/api/objects/${state.current}/ai?only_new=true`, { method: "POST" });
  } else {
    await api(`/api/objects/${state.current}/ai?only_new=${!redo}`, { method: "POST" });
  }
  toast("KI-Analyse gestartet"); refresh();
}

// ---------- Unterlagen ----------
function statusHtml(d) {
  if (d.status === "fertig") return `<span class="status ok">gelesen</span>`;
  if (d.status === "fehler") return `<span class="status err" title="${esc(d.error)}">Fehler</span>`;
  return `<span class="status run">${esc(d.progress || d.status)}</span>`;
}
function aiHtml(d) {
  const a = d.ai_status || "";
  if (!a) return `<span class="muted small">–</span>`;
  if (a.startsWith("fertig")) return `<span class="status ok">${esc(a)}</span>`;
  if (a.startsWith("fehler")) return `<span class="status err" title="${esc(a)}">Fehler</span>`;
  return `<span class="status run">${esc(a)}</span>`;
}
function renderDocs() {
  const docs = state.data.documents, t = $("#docsTable");
  if (!docs.length) { t.innerHTML = ""; }
  else {
    const typeOpts = sel => Object.entries(state.meta.doc_types).filter(([k]) => k !== "auto")
      .map(([k, v]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${esc(v)}</option>`).join("");
    t.innerHTML = `<thead><tr><th>Datei</th><th>Art</th><th>Jahr</th><th>Seiten</th><th>Text</th><th>KI</th><th></th></tr></thead><tbody>` +
      docs.map(d => `<tr data-id="${d.id}">
        <td class="fname" title="${esc(d.filename)}">${esc(d.filename)}</td>
        <td>${d.doc_type === "auto" ? '<span class="muted small">wird erkannt …</span>' : `<select data-f="doc_type">${typeOpts(d.doc_type)}</select>`}</td>
        <td><input data-f="doc_year" value="${d.doc_year || ""}" size="4" inputmode="numeric"></td>
        <td>${d.pages || "–"}${d.ocr_pages ? ` <span class="muted small" title="per Texterkennung gelesen">(${d.ocr_pages} OCR)</span>` : ""}</td>
        <td>${statusHtml(d)}</td><td>${aiHtml(d)}</td>
        <td class="doc-actions">
          <a class="icon-btn" href="/api/documents/${d.id}/file" target="_blank" rel="noopener" title="PDF öffnen">📄</a>
          <button class="icon-btn" data-act="reprocess" title="Neu einlesen">↻</button>
          <button class="icon-btn" data-act="delete" title="Löschen">🗑</button>
        </td></tr>`).join("") + "</tbody>";
  }
  const miss = state.data.missing;
  $("#missingBox").innerHTML = miss.length && docs.length
    ? `<div class="missing"><strong>Für eine vollständige Prüfung fehlt noch:</strong><ul>${miss.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>` : "";
}
async function onDocsChange(ev) {
  const tr = ev.target.closest("tr[data-id]"); if (!tr) return;
  const f = ev.target.dataset.f; if (!f) return;
  const val = f === "doc_year" ? (parseInt(ev.target.value, 10) || 0) : ev.target.value;
  await api(`/api/documents/${tr.dataset.id}`, { method: "PATCH", json: { [f]: val } });
  toast("Gespeichert"); refresh();
}
async function onDocsClick(ev) {
  const b = ev.target.closest("button[data-act]"); if (!b) return;
  const id = b.closest("tr").dataset.id;
  if (b.dataset.act === "delete") {
    if (!confirm("Dokument und seine Befunde löschen?")) return;
    await api(`/api/documents/${id}`, { method: "DELETE" });
  } else if (b.dataset.act === "reprocess") {
    await api(`/api/documents/${id}/reprocess`, { method: "POST" });
  }
  refresh(); loadObjects();
}
async function uploadFiles(files) {
  const pdfs = [...files].filter(f => f.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) { toast("Bitte PDF-Dateien wählen."); return; }
  const fd = new FormData();
  pdfs.forEach(f => fd.append("files", f));
  fd.append("doc_type", $("#upType").value);
  fd.append("doc_year", $("#upYear").value);
  $("#uploadMsg").textContent = `Lade ${pdfs.length} Datei(en) hoch …`;
  try {
    await api(`/api/objects/${state.current}/documents`, { method: "POST", body: fd });
    $("#uploadMsg").textContent = "";
    toast(`${pdfs.length} Datei(en) hochgeladen, werden gelesen`);
  } catch (e) { $("#uploadMsg").textContent = "Fehler: " + e.message; }
  $("#fileInput").value = "";
  refresh();
}

// ---------- Befunde ----------
function renderFilters() {
  $("#sevChips").innerHTML = ["hoch", "mittel", "info"].map(s =>
    `<button type="button" class="chip ${s} ${state.sev.has(s) ? "on" : ""}" data-sev="${s}">${SEV_LABEL[s]}</button>`).join("");
}
function renderFindings() {
  renderFilters();
  const src = $("#srcFilter").value, cat = $("#catFilter").value;
  const docs = Object.fromEntries(state.data.documents.map(d => [d.id, d]));
  const list = state.findings.filter(f => state.sev.has(f.severity) && (!src || f.source === src) && (!cat || f.category === cat));
  const box = $("#findings");
  if (!state.findings.length) {
    box.innerHTML = `<div class="empty-list">${state.data.documents.length ? "Noch keine Befunde. Wenn Unterlagen gerade gelesen werden, erscheinen sie gleich." : "Lade Unterlagen hoch, um Befunde zu sehen."}</div>`;
    return;
  }
  if (!list.length) { box.innerHTML = `<div class="empty-list">Keine Befunde für diesen Filter.</div>`; return; }
  const groups = new Map();
  for (const c of state.meta.categories) groups.set(c, []);
  for (const f of list) { if (!groups.has(f.category)) groups.set(f.category, []); groups.get(f.category).push(f); }
  box.innerHTML = [...groups].filter(([, items]) => items.length).map(([c, items]) => `<div class="cat"><h3>${esc(c)} (${items.length})</h3>` +
    items.map(f => {
      const d = docs[f.document_id];
      return `<div class="finding ${f.severity} ${f.dismissed ? "dismissed" : ""}" data-id="${f.id}">
        <div class="f-top">
          <span class="f-title">${esc(f.title)}</span>
          ${f.source === "ki" ? `<span class="tag ki">KI</span>` : `<span class="tag">Stichwort${f.hits > 1 ? ` ×${f.hits}` : ""}</span>`}
          ${f.source === "ki" && !f.verified ? `<span class="tag warn" title="Das Zitat der KI wurde im Dokument nicht gefunden. Selbst prüfen!">Zitat nicht gefunden</span>` : ""}
          <span class="f-meta">
            ${f.amount_eur ? `<span class="amount">${eur(f.amount_eur)}</span>` : ""}
            <span class="f-links"><a href="/api/documents/${f.document_id}/file#page=${f.page_no}" target="_blank" rel="noopener">${esc(d ? docLabel(d) : f.filename)}, S. ${f.page_no}</a></span>
            <button class="linkish small" data-act="text" data-doc="${f.document_id}" data-page="${f.page_no}">Text</button>
            <button class="linkish small" data-act="dismiss">${f.dismissed ? "einblenden" : "ausblenden"}</button>
          </span>
        </div>
        ${f.detail ? `<div class="f-detail">${esc(f.detail)}</div>` : ""}
        ${f.snippet ? `<div class="f-snip">${f.source === "ki" ? "„" + snippetHtml(f.snippet) + "“" : snippetHtml(f.snippet)}</div>` : ""}
      </div>`;
    }).join("") + `</div>`).join("");
}
async function onFindingsClick(ev) {
  const b = ev.target.closest("button[data-act]"); if (!b) return;
  if (b.dataset.act === "text") return showPage(b.dataset.doc, b.dataset.page);
  const card = b.closest(".finding"), id = card.dataset.id;
  const f = state.findings.find(x => x.id == id);
  await api(`/api/findings/${id}`, { method: "PATCH", json: { dismissed: !f.dismissed } });
  refresh(); loadObjects();
}
async function showPage(docId, page) {
  const p = await api(`/api/documents/${docId}/pages/${page}`);
  const d = state.data.documents.find(x => x.id == docId);
  $("#pageTitle").textContent = `${d ? docLabel(d) : ""}, Seite ${page}${p.ocr ? " (Texterkennung)" : ""}`;
  $("#pageText").textContent = p.text;
  $("#pageDialog").showModal();
}

// ---------- Kennzahlen ----------
function renderFigures() {
  const figs = state.data.figures, docs = Object.fromEntries(state.data.documents.map(d => [d.id, d]));
  if (!figs.length) { $("#figures").innerHTML = `<div class="empty-list">Noch keine Zahlen gefunden. Am besten die Jahresabrechnung mit Vermögensbericht hochladen.</div>`; return; }
  $("#figures").innerHTML = `<div class="table-wrap"><table class="figs"><thead><tr><th></th><th>Art</th><th>Jahr</th><th class="num">Betrag</th><th>Fundstelle</th></tr></thead><tbody>` +
    figs.map(f => { const d = docs[f.document_id]; return `<tr class="${f.chosen ? "chosen" : ""}">
      <td><input type="checkbox" data-fig="${f.id}" ${f.chosen ? "checked" : ""} title="Diesen Wert bestätigen"></td>
      <td>${esc(FIG_LABEL[f.kind] || f.kind)}</td><td>${f.year || ""}</td><td class="num">${eur(f.value_eur, 2)}</td>
      <td><div class="ctx">${esc(f.context)}</div><a class="small" href="/api/documents/${f.document_id}/file#page=${f.page_no}" target="_blank" rel="noopener">${esc(d ? docLabel(d) : "")}, S. ${f.page_no}</a></td></tr>`; }).join("") +
    `</tbody></table></div>`;
}
async function onFigureChange(ev) {
  const id = ev.target.dataset.fig; if (!id) return;
  await api(`/api/figures/${id}`, { method: "PATCH", json: { chosen: ev.target.checked } });
  refresh();
}

// ---------- Suche ----------
async function doSearch(ev) {
  ev.preventDefault();
  const q = $("#searchInput").value.trim(); if (q.length < 2) return;
  const hits = await api(`/api/objects/${state.current}/search?q=${encodeURIComponent(q)}`);
  const rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  $("#searchResults").innerHTML = hits.length ? hits.map(h => `<div class="hit">
      <a href="/api/documents/${h.document_id}/file#page=${h.page_no}" target="_blank" rel="noopener">${esc(docLabel(h))}, S. ${h.page_no}</a>
      <div class="muted">${esc(h.snippet).replace(rx, m => `<mark>${m}</mark>`)}</div></div>`).join("")
    : `<div class="empty-list">Nichts gefunden.</div>`;
}

// ---------- Einstellungen ----------
async function refreshMeta() {
  state.meta = await api("/api/status");
  const badge = $("#aiBadge");
  badge.textContent = state.meta.llm_enabled ? `KI: ${state.meta.model}` : "KI: aus";
  badge.classList.toggle("on", state.meta.llm_enabled);
  $("#pwBadge").hidden = state.meta.password_set;
}
function showSettings(show) {
  $("#settingsView").hidden = !show;
  $("#sidebar").classList.remove("open");
  if (show) { $("#objView").hidden = true; $("#emptyState").hidden = true; loadSettings().catch(e => toast(e.message)); }
  else if (state.current != null) { $("#objView").hidden = false; refresh(); }
  else $("#emptyState").hidden = false;
}
function setProviderVisibility() {
  const p = $("#aiForm").elements.llm_provider.value || "none";
  document.querySelectorAll("#aiForm [data-for]").forEach(el => { el.hidden = !el.dataset.for.split(" ").includes(p); });
  $("#testAi").hidden = p === "none";
}
async function loadSettings() {
  const st = await api("/api/settings");
  state.settings = st;
  const f = $("#aiForm").elements;
  f.llm_provider.value = st.llm_provider;
  for (const k of ["openai_base_url", "llm_model", "llm_chunk_chars", "llm_timeout"]) f[k].value = st[k] ?? "";
  f.anthropic_api_key.value = ""; f.openai_api_key.value = "";
  f.llm_model.placeholder = `Standard: ${st.llm_provider === "openai" ? "qwen2.5:14b" : "claude-sonnet-5"}`;
  const keyInfo = (name) => st[name + "_set"] ? `Gespeichert (${esc(st[name + "_masked"])}). Leer lassen, um ihn zu behalten. <button type="button" class="linkish" data-clear="${name}">Key löschen</button>` : "Noch kein Key gespeichert.";
  $("#anthropicKeyInfo").innerHTML = keyInfo("anthropic_api_key");
  $("#openaiKeyInfo").innerHTML = keyInfo("openai_api_key");
  setProviderVisibility();
  $("#aiTestMsg").textContent = "";

  const pf = $("#pwForm").elements;
  pf.user.value = st.auth_user; pf.password.value = ""; pf.password2.value = "";
  $("#pwState").innerHTML = st.password_set ? `<span class="ok-text">Passwortschutz aktiv</span>` : `<span class="err-text">kein Passwort</span>`;
  $("#pwRemove").hidden = !st.password_set;
  $("#pwWarn").hidden = st.password_set;

  const of = $("#ocrForm").elements;
  const langs = st.ocr_langs.length ? st.ocr_langs : [st.ocr_lang];
  const langName = { deu: "Deutsch", eng: "Englisch", "deu+eng": "Deutsch + Englisch" };
  const opts = [...new Set([...langs, ...(langs.includes("deu") && langs.includes("eng") ? ["deu+eng"] : [])])];
  $("#ocrLang").innerHTML = opts.map(l => `<option value="${esc(l)}">${esc(langName[l] || l)}</option>`).join("");
  of.ocr_lang.value = st.ocr_lang;
  of.ocr_dpi.value = [200, 300, 400].includes(st.ocr_dpi) ? String(st.ocr_dpi) : "300";
  of.max_upload_mb.value = st.max_upload_mb;
  $("#setVersion").textContent = `Version ${st.version}`;
  $("#dataDir").textContent = `Daten liegen in ${st.data_dir}. Für ein Backup diesen Ordner sichern.`;
}
async function saveAi(ev) {
  ev.preventDefault();
  const f = ev.target.elements;
  const body = {
    llm_provider: f.llm_provider.value || "none", openai_base_url: f.openai_base_url.value, llm_model: f.llm_model.value,
    llm_chunk_chars: f.llm_chunk_chars.value, llm_timeout: f.llm_timeout.value,
    anthropic_api_key: f.anthropic_api_key.value, openai_api_key: f.openai_api_key.value,
  };
  if (body.llm_provider === "anthropic" && !body.anthropic_api_key && !state.settings.anthropic_api_key_set) { toast("Bitte einen API-Key eintragen."); return; }
  await api("/api/settings", { method: "PUT", json: body });
  await refreshMeta(); await loadSettings(); toast("Gespeichert");
}
async function clearKey(name) {
  if (!confirm("Gespeicherten Key löschen?")) return;
  await api("/api/settings", { method: "PUT", json: { [name + "_clear"]: true } });
  await refreshMeta(); await loadSettings(); toast("Key gelöscht");
}
async function testAi() {
  const msg = $("#aiTestMsg");
  msg.className = "small"; msg.textContent = "Teste … (zuerst speichern, falls du etwas geändert hast)";
  try {
    const r = await api("/api/settings/test", { method: "POST" });
    msg.className = "small ok-text"; msg.textContent = `Verbindung klappt. ${r.model} antwortet: „${r.reply}“`;
  } catch (e) { msg.className = "small err-text"; msg.textContent = e.message; }
}
async function loadModels() {
  const btn = $("#loadModels"); btn.disabled = true;
  try {
    const r = await api("/api/settings/models");
    $("#modelList").innerHTML = r.models.map(m => `<option value="${esc(m)}">`).join("");
    toast(r.models.length ? `${r.models.length} Modelle gefunden. Ins Feld klicken zum Auswählen.` : "Keine Modelle gefunden.");
    if (r.models.length) $("#aiForm").elements.llm_model.focus();
  } catch (e) { toast("Zuerst speichern, dann Modelle laden. " + e.message, 6000); }
  btn.disabled = false;
}
async function savePassword(ev) {
  ev.preventDefault();
  const f = ev.target.elements;
  if (f.password.value.length < 8) { toast("Das Passwort muss mindestens 8 Zeichen haben."); return; }
  if (f.password.value !== f.password2.value) { toast("Die Passwörter stimmen nicht überein."); return; }
  await api("/api/settings/password", { method: "PUT", json: { user: f.user.value, password: f.password.value } });
  toast("Passwort gesetzt. Der Browser fragt gleich danach.", 5000);
  setTimeout(() => location.reload(), 1200);
}
async function removePassword() {
  if (!confirm("Passwortschutz wirklich entfernen?")) return;
  await api("/api/settings/password", { method: "PUT", json: { password: "" } });
  await refreshMeta(); await loadSettings(); toast("Passwort entfernt");
}
async function saveOcr(ev) {
  ev.preventDefault();
  const f = ev.target.elements;
  await api("/api/settings", { method: "PUT", json: { ocr_lang: f.ocr_lang.value, ocr_dpi: f.ocr_dpi.value, max_upload_mb: f.max_upload_mb.value } });
  await loadSettings(); toast("Gespeichert");
}

// ---------- Start ----------
async function init() {
  await refreshMeta();
  $("#upType").innerHTML = Object.entries(state.meta.doc_types).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#catFilter").innerHTML += state.meta.categories.map(c => `<option>${esc(c)}</option>`).join("");

  $("#newObjBtn").onclick = createObject; $("#emptyNewBtn").onclick = createObject;
  $("#objList").onclick = e => { const li = e.target.closest("li[data-id]"); if (li) openObject(+li.dataset.id); };
  $("#menuBtn").onclick = () => $("#sidebar").classList.toggle("open");
  $("#editObjBtn").onclick = () => showObjForm($("#objForm").hidden);
  $("#cancelObjForm").onclick = () => showObjForm(false);
  $("#objForm").onsubmit = saveObjForm;
  $("#delObjBtn").onclick = async () => {
    if (!confirm(`„${state.data.object.name}“ mit allen Unterlagen löschen?`)) return;
    await api(`/api/objects/${state.current}`, { method: "DELETE" });
    state.current = null; $("#objView").hidden = true; await loadObjects(); $("#emptyState").hidden = false;
  };
  $("#aiBtn").onclick = () => startAi().catch(e => toast(e.message, 6000));

  const dz = $("#dropzone"), fi = $("#fileInput");
  $("#pickBtn").onclick = e => { e.stopPropagation(); fi.click(); };
  dz.onclick = e => { if (!e.target.closest("select,input,label")) fi.click(); };
  dz.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fi.click(); } };
  fi.onchange = () => uploadFiles(fi.files);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("drag"); };
  dz.ondragleave = () => dz.classList.remove("drag");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("drag"); uploadFiles(e.dataTransfer.files); };

  $("#docsTable").addEventListener("change", e => onDocsChange(e).catch(err => toast(err.message)));
  $("#docsTable").addEventListener("click", e => onDocsClick(e).catch(err => toast(err.message)));
  $("#sevChips").onclick = e => { const c = e.target.closest("[data-sev]"); if (!c) return; const s = c.dataset.sev; state.sev.has(s) ? state.sev.delete(s) : state.sev.add(s); renderFindings(); };
  $("#srcFilter").onchange = renderFindings; $("#catFilter").onchange = renderFindings;
  $("#showDismissed").onchange = refresh;
  $("#findings").addEventListener("click", e => onFindingsClick(e).catch(err => toast(err.message)));
  $("#figures").addEventListener("change", e => onFigureChange(e).catch(err => toast(err.message)));
  $("#searchForm").onsubmit = e => doSearch(e).catch(err => toast(err.message));
  $("#pageClose").onclick = () => $("#pageDialog").close();

  const guard = fn => (...a) => fn(...a).catch(e => toast(e.message, 6000));
  $("#settingsBtn").onclick = () => showSettings($("#settingsView").hidden);
  $("#aiBadge").onclick = () => showSettings(true);
  $("#pwBadge").onclick = () => showSettings(true);
  $("#settingsClose").onclick = () => showSettings(false);
  document.addEventListener("click", e => { if (e.target.closest("[data-open-settings]")) showSettings(true); });
  $("#providerCards").onchange = setProviderVisibility;
  $("#aiForm").onsubmit = guard(saveAi);
  $("#testAi").onclick = guard(testAi);
  $("#loadModels").onclick = guard(loadModels);
  $("#aiForm").addEventListener("click", e => { const b = e.target.closest("[data-clear]"); if (b) guard(clearKey)(b.dataset.clear); });
  $("#pwForm").onsubmit = guard(savePassword);
  $("#pwRemove").onclick = guard(removePassword);
  $("#ocrForm").onsubmit = guard(saveOcr);

  await loadObjects();
  let last = null; try { last = +localStorage.getItem("weglupe.obj"); } catch { }
  const target = state.objects.find(o => o.id === last) || state.objects[0];
  if (target) openObject(target.id); else { $("#emptyState").hidden = false; }
}
init().catch(e => toast("Fehler beim Laden: " + e.message, 8000));
