"""WEG-Lupe: WEG-Unterlagen vor dem Wohnungskauf prüfen."""
import base64
import html
import logging
import re
import secrets
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analyze, config, db, llm, rules, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
STATIC = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(_app):
    db.conn()
    analyze.start_worker()
    yield


app = FastAPI(title="WEG-Lupe", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if request.url.path != "/healthz" and settings.password_set():
        header = request.headers.get("authorization", "")
        ok = False
        if header.lower().startswith("basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(user, settings.auth_user()) and settings.check_password(pw)
            except Exception:
                ok = False
        if not ok:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="WEG-Lupe"'})
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------- Meta ----------------

@app.get("/api/status")
def status():
    return {
        "llm_enabled": settings.llm_enabled(),
        "provider": settings.provider(),
        "model": settings.model(),
        "password_set": settings.password_set(),
        "version": config.VERSION,
        "doc_types": analyze.DOC_TYPES,
        "categories": rules.CATEGORIES,
    }


# ---------------- Objekte ----------------

class ObjectIn(BaseModel):
    name: str
    address: str = ""
    total_area_m2: float | None = None
    unit_area_m2: float | None = None
    mea_share: float | None = None
    price_eur: float | None = None
    notes: str = ""


def _object_or_404(oid: int) -> dict:
    obj = db.q1("SELECT * FROM objects WHERE id = ?", (oid,))
    if not obj:
        raise HTTPException(404, "Objekt nicht gefunden")
    return obj


@app.get("/api/objects")
def list_objects():
    return db.q("""
        SELECT o.*,
          (SELECT COUNT(*) FROM documents d WHERE d.object_id = o.id) AS doc_count,
          (SELECT COUNT(*) FROM findings f WHERE f.object_id = o.id AND f.severity = 'hoch' AND f.dismissed = 0) AS high_count
        FROM objects o ORDER BY o.created_at DESC""")


@app.post("/api/objects")
def create_object(body: ObjectIn):
    oid = db.ex(
        "INSERT INTO objects (name, address, total_area_m2, unit_area_m2, mea_share, price_eur, notes) VALUES (?,?,?,?,?,?,?)",
        (body.name.strip() or "Neues Objekt", body.address, body.total_area_m2, body.unit_area_m2, body.mea_share,
         body.price_eur, body.notes),
    )
    return _object_or_404(oid)


@app.put("/api/objects/{oid}")
def update_object(oid: int, body: ObjectIn):
    _object_or_404(oid)
    db.ex("""UPDATE objects SET name=?, address=?, total_area_m2=?, unit_area_m2=?, mea_share=?, price_eur=?, notes=?
             WHERE id=?""",
          (body.name, body.address, body.total_area_m2, body.unit_area_m2, body.mea_share, body.price_eur, body.notes, oid))
    return _object_or_404(oid)


@app.delete("/api/objects/{oid}")
def delete_object(oid: int):
    _object_or_404(oid)
    shutil.rmtree(config.UPLOAD_DIR / str(oid), ignore_errors=True)
    db.ex("DELETE FROM objects WHERE id = ?", (oid,))
    return {"ok": True}


@app.get("/api/objects/{oid}")
def get_object(oid: int):
    obj = _object_or_404(oid)
    docs = db.q("SELECT * FROM documents WHERE object_id = ? ORDER BY doc_type, doc_year DESC, id", (oid,))
    summary = db.q1("SELECT * FROM summaries WHERE object_id = ?", (oid,))
    figures = db.q("SELECT * FROM figures WHERE object_id = ? ORDER BY kind, chosen DESC, year DESC, value_eur DESC", (oid,))
    counts = db.q("""SELECT severity, source, COUNT(*) AS n FROM findings WHERE object_id = ? AND dismissed = 0
                     GROUP BY severity, source""", (oid,))
    return {
        "object": obj,
        "documents": docs,
        "summary": summary,
        "figures": figures,
        "missing": analyze.missing_documents(oid),
        "counts": counts,
    }


# ---------------- Dokumente ----------------

@app.post("/api/objects/{oid}/documents")
async def upload(oid: int, files: list[UploadFile] = File(...), doc_type: str = Form("auto"), doc_year: str = Form("")):
    _object_or_404(oid)
    if doc_type not in analyze.DOC_TYPES:
        doc_type = "auto"
    year = int(doc_year) if doc_year.strip().isdigit() else None
    target = config.UPLOAD_DIR / str(oid)
    target.mkdir(parents=True, exist_ok=True)
    created = []
    for f in files:
        name = Path(f.filename or "dokument.pdf").name
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, f"{name}: nur PDF-Dateien werden unterstützt")
        dest = target / f"{uuid.uuid4().hex}.pdf"
        size = 0
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > settings.get("max_upload_mb") * 1024 * 1024:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"{name} ist größer als {settings.get('max_upload_mb')} MB")
                out.write(chunk)
        with dest.open("rb") as fh:
            if fh.read(5) != b"%PDF-":
                dest.unlink(missing_ok=True)
                raise HTTPException(400, f"{name} ist keine gültige PDF-Datei")
        did = db.ex("INSERT INTO documents (object_id, filename, doc_type, doc_year, path) VALUES (?,?,?,?,?)",
                    (oid, name, doc_type, year, str(dest)))
        analyze.enqueue("extract", did)
        created.append(did)
    return {"created": created}


class DocPatch(BaseModel):
    doc_type: str | None = None
    doc_year: int | None = None


def _doc_or_404(did: int) -> dict:
    d = db.q1("SELECT * FROM documents WHERE id = ?", (did,))
    if not d:
        raise HTTPException(404, "Dokument nicht gefunden")
    return d


@app.patch("/api/documents/{did}")
def patch_doc(did: int, body: DocPatch):
    _doc_or_404(did)
    if body.doc_type and body.doc_type in analyze.DOC_TYPES and body.doc_type != "auto":
        db.ex("UPDATE documents SET doc_type = ? WHERE id = ?", (body.doc_type, did))
    if body.doc_year is not None:
        db.ex("UPDATE documents SET doc_year = ? WHERE id = ?", (body.doc_year or None, did))
    return _doc_or_404(did)


@app.delete("/api/documents/{did}")
def delete_doc(did: int):
    d = _doc_or_404(did)
    Path(d["path"]).unlink(missing_ok=True)
    db.ex("DELETE FROM documents WHERE id = ?", (did,))
    return {"ok": True}


@app.post("/api/documents/{did}/reprocess")
def reprocess(did: int):
    _doc_or_404(did)
    analyze.enqueue("extract", did)
    return {"ok": True}


@app.get("/api/documents/{did}/file")
def doc_file(did: int):
    d = _doc_or_404(did)
    return FileResponse(d["path"], media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{d["filename"]}"'})


@app.get("/api/documents/{did}/pages/{page_no}")
def doc_page(did: int, page_no: int):
    p = db.q1("SELECT * FROM pages WHERE document_id = ? AND page_no = ?", (did, page_no))
    if not p:
        raise HTTPException(404, "Seite nicht gefunden")
    return p


# ---------------- Befunde, Kennzahlen, Suche ----------------

@app.get("/api/objects/{oid}/findings")
def findings(oid: int, include_dismissed: bool = False):
    sql = """SELECT f.*, d.filename, d.doc_type, d.doc_year FROM findings f JOIN documents d ON d.id = f.document_id
             WHERE f.object_id = ?"""
    if not include_dismissed:
        sql += " AND f.dismissed = 0"
    sql += """ ORDER BY CASE f.severity WHEN 'hoch' THEN 0 WHEN 'mittel' THEN 1 ELSE 2 END,
               f.source DESC, d.doc_year DESC, f.page_no"""
    return db.q(sql, (oid,))


class FindingPatch(BaseModel):
    dismissed: bool


@app.patch("/api/findings/{fid}")
def patch_finding(fid: int, body: FindingPatch):
    db.ex("UPDATE findings SET dismissed = ? WHERE id = ?", (int(body.dismissed), fid))
    return {"ok": True}


class FigurePatch(BaseModel):
    chosen: bool


@app.patch("/api/figures/{fid}")
def patch_figure(fid: int, body: FigurePatch):
    fig = db.q1("SELECT * FROM figures WHERE id = ?", (fid,))
    if not fig:
        raise HTTPException(404)
    with db.tx() as c:
        if body.chosen:  # je Art und Jahr nur ein bestätigter Wert
            c.execute("UPDATE figures SET chosen = 0 WHERE object_id = ? AND kind = ? AND IFNULL(year, 0) = IFNULL(?, 0)",
                      (fig["object_id"], fig["kind"], fig["year"]))
        c.execute("UPDATE figures SET chosen = ? WHERE id = ?", (int(body.chosen), fid))
    return {"ok": True}


@app.get("/api/objects/{oid}/search")
def search(oid: int, q: str):
    q = q.strip()
    if len(q) < 2:
        return []
    rows = db.q("""SELECT p.document_id, p.page_no, p.text, d.filename, d.doc_type, d.doc_year
                   FROM pages p JOIN documents d ON d.id = p.document_id
                   WHERE d.object_id = ? AND p.text LIKE ? ORDER BY d.doc_year DESC, p.page_no LIMIT 200""",
                (oid, f"%{q}%"))
    out = []
    rx = re.compile(re.escape(q), re.IGNORECASE)
    for r in rows:
        flat = rules.one_line(r.pop("text"))
        m = rx.search(flat)
        r["snippet"] = rules.snippet_around(flat, m.start(), m.end(), 160) if m else ""
        out.append(r)
    return out


# ---------------- KI ----------------

def _require_llm():
    if not settings.llm_enabled():
        raise HTTPException(400, "Keine KI eingerichtet. Bitte unter Einstellungen einen KI-Anbieter wählen.")


@app.post("/api/objects/{oid}/ai")
def run_ai(oid: int, only_new: bool = True):
    _object_or_404(oid)
    _require_llm()
    docs = db.q("SELECT * FROM documents WHERE object_id = ? AND status = 'fertig'", (oid,))
    queued = 0
    for d in docs:
        if only_new and (d["ai_status"] or "").startswith("fertig"):
            continue
        analyze.enqueue("ai_doc", d["id"])
        queued += 1
    analyze.enqueue("summary", oid)
    return {"queued_docs": queued}


@app.post("/api/objects/{oid}/summary")
def run_summary(oid: int):
    _object_or_404(oid)
    _require_llm()
    analyze.enqueue("summary", oid)
    return {"ok": True}


# ---------------- Einstellungen ----------------

def _ocr_langs() -> list[str]:
    try:
        out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10).stdout
        return [ln.strip() for ln in out.splitlines()[1:] if ln.strip() and ln.strip() != "osd"]
    except Exception:
        return []


@app.get("/api/settings")
def get_settings():
    out = {}
    for key in settings.SPEC:
        val = settings.get(key)
        if key in settings.SECRETS:
            out[key] = ""
            out[key + "_set"] = bool(val)
            out[key + "_masked"] = settings.mask(val)
        else:
            out[key] = val
    out["model_effective"] = settings.model()
    out["password_set"] = settings.password_set()
    out["auth_user"] = settings.auth_user()
    out["ocr_langs"] = _ocr_langs()
    out["data_dir"] = str(config.DATA_DIR)
    out["version"] = config.VERSION
    return out


@app.put("/api/settings")
def put_settings(body: dict):
    values = {k: v for k, v in body.items() if k in settings.SPEC}
    for key in settings.SECRETS:  # leeres Feld = gespeicherten Schlüssel behalten
        if key in values and not str(values[key]).strip() and not body.get(key + "_clear"):
            del values[key]
        if body.get(key + "_clear"):
            values[key] = ""
    try:
        settings.set_many(values)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return get_settings()


@app.post("/api/settings/test")
def test_settings():
    if not settings.llm_enabled():
        raise HTTPException(400, "Kein KI-Anbieter eingerichtet.")
    try:
        reply = llm.test_connection()
    except llm.LLMError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "reply": reply, "model": settings.model()}


@app.get("/api/settings/models")
def models():
    try:
        return {"models": llm.list_models()}
    except llm.LLMError as e:
        raise HTTPException(400, str(e))


class PasswordIn(BaseModel):
    password: str = ""
    user: str = ""


@app.put("/api/settings/password")
def put_password(body: PasswordIn):
    pw = body.password
    if pw and len(pw) < 8:
        raise HTTPException(400, "Das Passwort muss mindestens 8 Zeichen haben.")
    if body.user.strip():
        db.ex("INSERT INTO settings (key, value) VALUES ('auth_user', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
              (body.user.strip(),))
    settings.set_password(pw or None)
    settings._invalidate()
    return {"password_set": settings.password_set()}


# ---------------- Bericht ----------------

def md_to_html(md: str) -> str:
    out, in_list = [], False
    for raw in md.splitlines():
        line = html.escape(raw.rstrip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        if re.match(r"^\s*[-*] ", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + re.sub(r"^\s*[-*] ", "", line) + "</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if m := re.match(r"^(#{1,4}) (.*)", line):
            lvl = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
        elif re.match(r"^\s*\d+\. ", line):
            out.append(f"<p>{line}</p>")
        elif line.strip():
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def eur(v) -> str:
    return "–" if v is None else f"{v:,.0f} €".replace(",", ".")


@app.get("/api/objects/{oid}/report", response_class=HTMLResponse)
def report(oid: int):
    data = get_object(oid)
    obj = data["object"]
    fs = findings(oid)
    doc_label = {d["id"]: f"{analyze.DOC_TYPES.get(d['doc_type'], d['doc_type'])} {d['doc_year'] or ''}".strip()
                 for d in data["documents"]}
    e = html.escape
    parts = [f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WEG-Prüfbericht {e(obj['name'])}</title><style>
body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1a1a1a}}
h1{{font-size:22px;margin-bottom:0}} h2{{font-size:17px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}} h3{{font-size:15px}}
table{{border-collapse:collapse;width:100%}} td,th{{text-align:left;padding:4px 8px;border-bottom:1px solid #eee;vertical-align:top}}
.hoch{{color:#b42318;font-weight:600}} .mittel{{color:#b54708}} .info{{color:#555}} .muted{{color:#666;font-size:12px}}
blockquote{{margin:4px 0;color:#444;font-size:12.5px;border-left:3px solid #ddd;padding-left:8px}}
@media print{{a{{color:inherit;text-decoration:none}}}}</style></head><body>
<h1>WEG-Prüfbericht: {e(obj['name'])}</h1><div class="muted">{e(obj['address'] or '')}</div>
<p class="muted">Automatisch erstellt mit WEG-Lupe. Ersetzt keine Rechts-, Steuer- oder Bausachverständigen-Beratung. KI-Befunde können falsch sein; Seitenangaben prüfen.</p>"""]
    s = data["summary"]
    if s and s.get("text"):
        parts.append("<h2>Einschätzung</h2>" + md_to_html(s["text"]) + f"<p class='muted'>Modell: {e(s.get('model') or '')}, {e(s.get('created_at') or '')}</p>")
    if data["missing"]:
        parts.append("<h2>Fehlende Unterlagen</h2><ul>" + "".join(f"<li>{e(m)}</li>" for m in data["missing"]) + "</ul>")
    chosen = [f for f in data["figures"] if f["chosen"]]
    if chosen:
        parts.append("<h2>Bestätigte Kennzahlen</h2><table><tr><th>Art</th><th>Jahr</th><th>Wert</th><th>Quelle</th></tr>")
        for f in chosen:
            parts.append(f"<tr><td>{e(f['kind'])}</td><td>{f['year'] or ''}</td><td>{eur(f['value_eur'])}</td><td>{e(doc_label.get(f['document_id'], ''))}, S. {f['page_no']}</td></tr>")
        parts.append("</table>")
    for sev, label in [("hoch", "Hohe Relevanz"), ("mittel", "Nachfragen"), ("info", "Zur Information")]:
        items = [f for f in fs if f["severity"] == sev]
        if not items:
            continue
        parts.append(f"<h2>{label} ({len(items)})</h2><table><tr><th>Thema</th><th>Quelle</th><th>Betrag</th></tr>")
        for f in items:
            src = "KI" if f["source"] == "ki" else "Stichwort"
            warn = "" if f["verified"] else " ⚠ Zitat nicht gefunden"
            detail = f"<div>{e(f['detail'])}</div>" if f["detail"] else ""
            parts.append(
                f"<tr><td><span class='{sev}'>{e(f['category'])}: {e(f['title'])}</span> <span class='muted'>({src}{warn})</span>"
                f"{detail}<blockquote>{e(f['snippet'][:400]).replace(chr(1), '<mark>').replace(chr(2), '</mark>')}</blockquote></td>"
                f"<td>{e(doc_label.get(f['document_id'], ''))}<br>S. {f['page_no']}</td><td>{eur(f['amount_eur'])}</td></tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logging.exception("Fehler bei %s", request.url.path)
    return JSONResponse({"detail": f"Interner Fehler: {exc}"}, status_code=500)
