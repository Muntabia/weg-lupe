"""Verarbeitung im Hintergrund: Text lesen, Regeln anwenden, KI-Analyse, Zusammenfassung."""
import logging
import queue
import re
import threading
import traceback
from collections import Counter

from . import config, db, extract, llm, rules

log = logging.getLogger("weglupe")

DOC_TYPES = {
    "auto": "Automatisch erkennen",
    "protokoll": "Versammlungsprotokoll",
    "beschlusssammlung": "Beschlusssammlung",
    "wirtschaftsplan": "Wirtschaftsplan",
    "jahresabrechnung": "Jahres-/Hausgeldabrechnung",
    "teilungserklaerung": "Teilungserklärung / Gemeinschaftsordnung",
    "energieausweis": "Energieausweis",
    "sonstiges": "Sonstiges",
}

DETECT = [
    ("beschlusssammlung", r"beschlu(ss|ß)-?\s?sammlung"),
    ("protokoll", r"(protokoll|niederschrift)[^\n]{0,80}(eigent(ü|ue)mer|versammlung)|eigent(ü|ue)merversammlung"),
    ("wirtschaftsplan", r"wirtschaftsplan"),
    ("jahresabrechnung", r"jahresabrechnung|hausgeldabrechnung|einzelabrechnung|gesamtabrechnung|verm(ö|oe)gensbericht"),
    ("teilungserklaerung", r"teilungserkl(ä|ae)rung|gemeinschaftsordnung"),
    ("energieausweis", r"energieausweis"),
]

_q: "queue.Queue[tuple[str, int]]" = queue.Queue()


def detect_type(first_pages: str) -> tuple[str, int | None]:
    low = first_pages.lower()[:4000]
    kind = "sonstiges"
    best = len(low) + 1
    for k, pat in DETECT:
        m = re.search(pat, low)
        if m and m.start() < best:
            kind, best = k, m.start()
    years = [int(y) for y in re.findall(r"\b(20[0-4]\d)\b", low[:2500])]
    year = Counter(years).most_common(1)[0][0] if years else None
    return kind, year


def _set_doc(doc_id: int, **fields):
    cols = ", ".join(f"{k} = ?" for k in fields)
    db.ex(f"UPDATE documents SET {cols} WHERE id = ?", (*fields.values(), doc_id))


# ---------------- Textextraktion + Regeln ----------------

def run_extract(doc_id: int):
    doc = db.q1("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not doc:
        return
    _set_doc(doc_id, status="liest", progress="Starte …", error="")
    with db.tx() as c:
        c.execute("DELETE FROM pages WHERE document_id = ?", (doc_id,))
        c.execute("DELETE FROM findings WHERE document_id = ? AND source = 'regel'", (doc_id,))
        c.execute("DELETE FROM figures WHERE document_id = ?", (doc_id,))

    total = extract.page_count(doc["path"])
    _set_doc(doc_id, pages=total)
    ocr_count = 0
    head_text = ""
    for page_no, text, used_ocr in extract.extract_pages(doc["path"], lambda p: _set_doc(doc_id, progress=p)):
        ocr_count += int(used_ocr)
        if page_no <= 2:
            head_text += text + "\n"
        hits = rules.scan_page(text)
        figs = rules.scan_figures(text)
        with db.tx() as c:
            c.execute("INSERT INTO pages (document_id, page_no, text, ocr) VALUES (?,?,?,?)",
                      (doc_id, page_no, text, int(used_ocr)))
            for h in hits:
                c.execute(
                    """INSERT INTO findings (object_id, document_id, page_no, source, category, severity, title,
                       snippet, amount_eur, hits) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (doc["object_id"], doc_id, page_no, "regel", h["category"], h["severity"], h["title"],
                     h["snippet"], h["amount_eur"], h["hits"]),
                )
            for f in figs:
                c.execute(
                    "INSERT INTO figures (object_id, document_id, page_no, kind, value_eur, context, year) VALUES (?,?,?,?,?,?,?)",
                    (doc["object_id"], doc_id, page_no, f["kind"], f["value_eur"], f["context"], f["year"]),
                )

    updates = {"status": "fertig", "progress": "", "ocr_pages": ocr_count}
    if doc["doc_type"] == "auto":
        kind, year = detect_type(head_text)
        updates["doc_type"] = kind
        if not doc["doc_year"] and year:
            updates["doc_year"] = year
    _set_doc(doc_id, **updates)


# ---------------- KI je Dokument ----------------

def _norm(s: str) -> str:
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"[^\w€%]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def verify_quote(quote: str, claimed_page: int | None, pages: dict[int, str]) -> tuple[int | None, bool]:
    """Prüft, ob das KI-Zitat wirklich im Dokument steht. Gibt (korrigierte Seite, gefunden) zurück."""
    nq = _norm(quote or "")
    if len(nq) < 8:
        return claimed_page, False
    probes = [nq]
    words = nq.split()
    if len(words) > 8:  # OCR-Fehler tolerieren: auch mittlere Teilstücke prüfen
        probes += [" ".join(words[i : i + 6]) for i in range(0, len(words) - 5, 3)]
    order = ([claimed_page] if claimed_page in pages else []) + [p for p in pages if p != claimed_page]
    for probe in probes:
        for p in order:
            if probe in pages[p]:
                return p, True
    return claimed_page, False


def build_chunks(page_rows: list[dict], limit: int) -> list[str]:
    chunks, cur = [], ""
    for row in page_rows:
        part = f"\n=== Seite {row['page_no']} ===\n{row['text']}\n"
        if cur and len(cur) + len(part) > limit:
            chunks.append(cur)
            cur = ""
        while len(part) > limit:  # sehr lange Einzelseite teilen
            chunks.append(part[:limit])
            part = f"\n=== Seite {row['page_no']} (Fortsetzung) ===\n" + part[limit:]
        cur += part
    if cur.strip():
        chunks.append(cur)
    return chunks


def run_ai_doc(doc_id: int):
    doc = db.q1("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not doc:
        return
    if doc["status"] != "fertig":
        _set_doc(doc_id, ai_status="fehler: Text noch nicht gelesen")
        return
    page_rows = db.q("SELECT page_no, text FROM pages WHERE document_id = ? ORDER BY page_no", (doc_id,))
    chunks = build_chunks(page_rows, config.LLM_CHUNK_CHARS)
    norm_pages = {r["page_no"]: _norm(r["text"]) for r in page_rows}
    label = f"{DOC_TYPES.get(doc['doc_type'], doc['doc_type'])} {doc['doc_year'] or ''} ({doc['filename']})".strip()
    found: list[dict] = []
    try:
        for i, ch in enumerate(chunks, 1):
            _set_doc(doc_id, ai_status=f"läuft {i}/{len(chunks)}")
            found += llm.analyze_chunk(label, ch)
    except llm.LLMError as e:
        _set_doc(doc_id, ai_status=f"fehler: {e}"[:500])
        return

    valid_cats = set(rules.CATEGORIES)
    with db.tx() as c:
        c.execute("DELETE FROM findings WHERE document_id = ? AND source = 'ki'", (doc_id,))
        for f in found:
            try:
                claimed = int(f.get("seite")) if f.get("seite") is not None else None
            except (TypeError, ValueError):
                claimed = None
            page, ok = verify_quote(str(f.get("zitat", "")), claimed, norm_pages)
            cat = f.get("kategorie") if f.get("kategorie") in valid_cats else "Offene & vertagte Themen"
            sev = f.get("schwere") if f.get("schwere") in ("hoch", "mittel", "info") else "mittel"
            try:
                amount = float(f["betrag_eur"]) if f.get("betrag_eur") not in (None, "") else None
            except (TypeError, ValueError):
                amount = None
            c.execute(
                """INSERT INTO findings (object_id, document_id, page_no, source, category, severity, title, detail,
                   snippet, amount_eur, verified) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (doc["object_id"], doc_id, page, "ki", cat, sev, str(f.get("titel", ""))[:200],
                 str(f.get("beschreibung", ""))[:1500], str(f.get("zitat", ""))[:600], amount, int(ok)),
            )
    _set_doc(doc_id, ai_status=f"fertig ({len(found)} Befunde)")


# ---------------- Zusammenfassung je Objekt ----------------

REQUIRED = [
    ("protokoll", "Protokolle der Eigentümerversammlungen (mind. 3 Jahre)"),
    ("beschlusssammlung", "Beschlusssammlung"),
    ("wirtschaftsplan", "Aktueller Wirtschaftsplan"),
    ("jahresabrechnung", "Letzte Jahresabrechnung mit Vermögensbericht (Rücklagenstand)"),
    ("teilungserklaerung", "Teilungserklärung / Gemeinschaftsordnung"),
    ("energieausweis", "Energieausweis"),
]


def missing_documents(object_id: int) -> list[str]:
    docs = db.q("SELECT doc_type, doc_year FROM documents WHERE object_id = ?", (object_id,))
    types = Counter(d["doc_type"] for d in docs)
    missing = [label for key, label in REQUIRED if types.get(key, 0) == 0]
    prot_years = {d["doc_year"] for d in docs if d["doc_type"] == "protokoll" and d["doc_year"]}
    if types.get("protokoll") and len(prot_years) < 3:
        missing.append(f"Protokolle aus mindestens 3 Jahren (vorhanden: {', '.join(map(str, sorted(prot_years))) or 'Jahr unbekannt'})")
    return missing


def build_summary_payload(object_id: int) -> str:
    obj = db.q1("SELECT * FROM objects WHERE id = ?", (object_id,))
    docs = {d["id"]: d for d in db.q("SELECT * FROM documents WHERE object_id = ?", (object_id,))}
    lines = [f"# Objekt: {obj['name']}", f"Adresse: {obj['address'] or 'unbekannt'}"]
    for key, label in [("total_area_m2", "Gesamtwohnfläche WEG (m²)"), ("unit_area_m2", "Wohnfläche der Wohnung (m²)"),
                       ("mea_share", "Miteigentumsanteil (Bruch)"), ("price_eur", "Kaufpreis (€)")]:
        if obj.get(key):
            lines.append(f"{label}: {obj[key]}")
    if obj.get("notes"):
        lines.append(f"Notizen des Käufers: {obj['notes']}")

    lines.append("\n# Unterlagen")
    for d in docs.values():
        lines.append(f"- {DOC_TYPES.get(d['doc_type'], d['doc_type'])} {d['doc_year'] or ''}: {d['filename']} ({d['pages']} S.)")
    miss = missing_documents(object_id)
    if miss:
        lines.append("Fehlend: " + "; ".join(miss))

    figs = db.q("SELECT * FROM figures WHERE object_id = ? AND chosen = 1", (object_id,))
    if figs:
        lines.append("\n# Vom Käufer bestätigte Kennzahlen")
        for f in figs:
            lines.append(f"- {f['kind']}: {f['value_eur']:.2f} € ({f['year'] or 'Jahr?'})")

    def dlabel(did):
        d = docs.get(did)
        return f"{DOC_TYPES.get(d['doc_type'], d['doc_type'])} {d['doc_year'] or ''}".strip() if d else "?"

    ki = db.q("""SELECT * FROM findings WHERE object_id = ? AND source = 'ki' AND dismissed = 0
                 ORDER BY CASE severity WHEN 'hoch' THEN 0 WHEN 'mittel' THEN 1 ELSE 2 END""", (object_id,))
    if ki:
        lines.append("\n# KI-Befunde")
        for f in ki:
            amt = f" | Betrag: {f['amount_eur']:.0f} €" if f["amount_eur"] else ""
            ver = "" if f["verified"] else " | ZITAT NICHT IM DOKUMENT GEFUNDEN, mit Vorsicht"
            lines.append(f"- [{f['severity']}] {f['category']}: {f['title']} ({dlabel(f['document_id'])}, S. {f['page_no']}){amt}{ver}\n  {f['detail']}\n  Zitat: \"{f['snippet'][:250]}\"")

    rg = db.q("""SELECT * FROM findings WHERE object_id = ? AND source = 'regel' AND dismissed = 0 AND severity != 'info'
                 ORDER BY category, title""", (object_id,))
    if rg:
        lines.append("\n# Stichwort-Treffer (regelbasiert, gekürzt)")
        grouped: dict[str, list[dict]] = {}
        for f in rg:
            grouped.setdefault(f"{f['category']} / {f['title']}", []).append(f)
        for key, items in grouped.items():
            refs = ", ".join(f"{dlabel(i['document_id'])} S.{i['page_no']}" for i in items[:12])
            amts = [i["amount_eur"] for i in items if i["amount_eur"]]
            amt = f" | größter Betrag in der Nähe: {max(amts):.0f} €" if amts else ""
            lines.append(f"- {key}: {len(items)} Seiten ({refs}){amt}\n  Beispiel: \"{items[0]['snippet'][:300]}\"")
    payload = "\n".join(lines).replace("\x01", "").replace("\x02", "")
    return payload[:150_000]


def run_summary(object_id: int):
    db.ex("""INSERT INTO summaries (object_id, status, text) VALUES (?, 'läuft', '')
             ON CONFLICT(object_id) DO UPDATE SET status = 'läuft'""", (object_id,))
    try:
        text = llm.summarize(build_summary_payload(object_id))
        db.ex("UPDATE summaries SET status = 'fertig', text = ?, model = ?, created_at = datetime('now') WHERE object_id = ?",
              (text, f"{config.LLM_PROVIDER}:{config.default_model()}", object_id))
    except llm.LLMError as e:
        db.ex("UPDATE summaries SET status = ? WHERE object_id = ?", (f"fehler: {e}"[:500], object_id))


# ---------------- Warteschlange ----------------

def enqueue(kind: str, ident: int):
    if kind == "extract":
        _set_doc(ident, status="wartet", progress="In Warteschlange")
    elif kind == "ai_doc":
        _set_doc(ident, ai_status="wartet")
    elif kind == "summary":
        db.ex("""INSERT INTO summaries (object_id, status) VALUES (?, 'wartet')
                 ON CONFLICT(object_id) DO UPDATE SET status = 'wartet'""", (ident,))
    _q.put((kind, ident))


def _worker():
    handlers = {"extract": run_extract, "ai_doc": run_ai_doc, "summary": run_summary}
    while True:
        kind, ident = _q.get()
        try:
            handlers[kind](ident)
        except Exception as e:
            log.error("Job %s %s fehlgeschlagen: %s", kind, ident, traceback.format_exc())
            if kind == "extract":
                _set_doc(ident, status="fehler", error=str(e)[:500], progress="")
            elif kind == "ai_doc":
                _set_doc(ident, ai_status=f"fehler: {e}"[:500])
            elif kind == "summary":
                db.ex("UPDATE summaries SET status = ? WHERE object_id = ?", (f"fehler: {e}"[:500], ident))
        finally:
            _q.task_done()


def start_worker():
    # Nach einem Neustart unterbrochene Jobs wieder einreihen
    for d in db.q("SELECT id FROM documents WHERE status IN ('wartet', 'liest')"):
        _q.put(("extract", d["id"]))
    for d in db.q("SELECT id FROM documents WHERE ai_status = 'wartet' OR ai_status LIKE 'läuft%'"):
        _q.put(("ai_doc", d["id"]))
    for s in db.q("SELECT object_id FROM summaries WHERE status IN ('wartet', 'läuft')"):
        _q.put(("summary", s["object_id"]))
    threading.Thread(target=_worker, daemon=True, name="weglupe-worker").start()
