"""Regelbasierter Scanner: findet Warnsignale ohne KI, mit Seitenangabe.

Die Regeln sind absichtlich eher empfindlich eingestellt. Lieber ein Treffer
zu viel, den man wegklickt, als eine übersehene Sonderumlage.
"""
import re
from dataclasses import dataclass, field

CATEGORIES = [
    "Sonderumlage",
    "Finanzen & Rücklage",
    "Schäden & Mängel",
    "Große Sanierungen",
    "Energie & Heizung",
    "Offene & vertagte Themen",
    "Rechtsstreit",
    "Verwaltung",
    "Nutzung & Konflikte",
]


@dataclass
class Rule:
    id: str
    category: str
    severity: str  # hoch | mittel | info
    title: str
    pattern: str
    negatable: bool = True
    regex: re.Pattern = field(init=False)

    def __post_init__(self):
        self.regex = re.compile(self.pattern, re.IGNORECASE)


R = Rule
RULES: list[Rule] = [
    # --- Sonderumlage ---
    R("su", "Sonderumlage", "hoch", "Sonderumlage erwähnt", r"sonder\s?umlage\w*"),
    R("su_rate", "Sonderumlage", "hoch", "Ratenweise Umlage / Nachschuss", r"(umlage\w* in \w+ raten|nachschuss\w*|nachzahlung\w* der eigent)"),
    # --- Finanzen ---
    R("rl_entnahme", "Finanzen & Rücklage", "mittel", "Entnahme aus der Rücklage",
      r"entnahme\w* (aus|der) (der )?(erhaltungs|instandhaltungs)?r(ü|ue)cklage|(erhaltungs|instandhaltungs)?r(ü|ue)cklage\w* (wird|werden|wurde) (entnommen|verwendet|aufgebraucht|aufgelöst)"),
    R("rl_niedrig", "Finanzen & Rücklage", "hoch", "Rücklage reicht nicht / aufgebraucht",
      r"r(ü|ue)cklage\w*[^.]{0,80}(reicht nicht|nicht ausreich|unzureichend|aufgebraucht|erschöpft|zu gering)"),
    R("rueckstand", "Finanzen & Rücklage", "hoch", "Hausgeldrückstände",
      r"(hausgeld|wohngeld)r(ü|ue)ckst(ä|ae)nd\w*|zahlungsr(ü|ue)ckst(ä|ae)nd\w*|r(ü|ue)ckst(ä|ae)nd\w* (einzelner|von) eigent\w*|zahlungsunf(ä|ae)hig\w*|insolven\w*"),
    R("mahn", "Finanzen & Rücklage", "mittel", "Mahnverfahren / Zwangsvollstreckung",
      r"mahnverfahren|mahnbescheid|zwangsvollstreck\w*|zwangsversteiger\w*|entziehungs(klage|verfahren)"),
    R("kredit", "Finanzen & Rücklage", "hoch", "Darlehen / Kredit der Gemeinschaft",
      r"(darlehen|kredit|finanzierung)\w*[^.]{0,60}(gemeinschaft|weg\b|aufnehm|aufnahme)|(gemeinschaft|weg)[^.]{0,40}(darlehen|kredit)\w*"),
    R("hg_erh", "Finanzen & Rücklage", "mittel", "Erhöhung Hausgeld / Rücklagenzuführung",
      r"(erh(ö|oe)hung|anhebung|erh(ö|oe)ht)[^.]{0,50}(hausgeld|wohngeld|r(ü|ue)cklage|zuf(ü|ue)hrung)|(hausgeld|wohngeld|zuf(ü|ue)hrung)\w*[^.]{0,40}(erh(ö|oe)ht|angehoben)"),
    R("liqui", "Finanzen & Rücklage", "hoch", "Liquiditätsprobleme", r"liquidit(ä|ae)ts(engpass|problem|l(ü|ue)cke|schwierigkeit)\w*|konto (ist )?(im )?(soll|(ü|ue)berzogen)"),
    # --- Schäden ---
    R("wasser", "Schäden & Mängel", "hoch", "Wasserschaden / Feuchtigkeit",
      r"wasserschad\w*|feuchtigkeit\w*|feuchteschad\w*|durchfeucht\w*|nasse (wand|w(ä|ae)nde|keller)|wassereintritt\w*|undicht\w*|leckage\w*|rohrbruch\w*"),
    R("schimmel", "Schäden & Mängel", "hoch", "Schimmel / Hausschwamm", r"schimmel\w*|hausschwamm\w*"),
    R("schadstoff", "Schäden & Mängel", "hoch", "Schadstoffe", r"asbest\w*|legionell\w*|pcb\b|teer\w*haltig|schadstoff\w*"),
    R("risse", "Schäden & Mängel", "mittel", "Risse / Setzungen / Statik", r"setzungs?ri(ss|ß)\w*|\bri(ss|ß)(e|bildung)\b|\bsetzung(en)?\b|\bstatik\w*\w*|tragf(ä|ae)hig\w*"),
    R("gutachten", "Schäden & Mängel", "mittel", "Gutachten / Sachverständiger", r"gutacht\w*|sachverst(ä|ae)ndig\w*|bauzustands?analyse|instandhaltungsstau|sanierungsstau|investitionsstau"),
    R("maengel", "Schäden & Mängel", "mittel", "Mängel / Gewährleistung", r"m(ä|ae)ngel\w*|gew(ä|ae)hrleistung\w*|baum(ä|ae)ngel\w*"),
    # --- Große Sanierungen ---
    R("dach", "Große Sanierungen", "hoch", "Dach", r"dach(sanierung|erneuerung|eindeckung|undicht|schaden|sch(ä|ae)den|abdichtung|d(ä|ae)mmung)\w*|flachdach\w*"),
    R("fassade", "Große Sanierungen", "hoch", "Fassade", r"fassade\w*|au(ß|ss)enwand\w*|wdvs|w(ä|ae)rmed(ä|ae)mmverbund\w*"),
    R("strang", "Große Sanierungen", "hoch", "Leitungen / Strangsanierung", r"strang\w*sanierung|steigleitung\w*|(wasser|abwasser|trinkwasser|fall)leitung\w*|leitungssanierung|rohrsanierung\w*"),
    R("aufzug", "Große Sanierungen", "mittel", "Aufzug", r"aufzug\w*|fahrstuhl\w*|lift\b"),
    R("balkon", "Große Sanierungen", "mittel", "Balkone / Terrassen", r"balkon\w*sanierung|balkon\w*[^.]{0,40}(schad|sch(ä|ae)d|sanier|abdicht|marode)|loggia\w*"),
    R("tg", "Große Sanierungen", "mittel", "Tiefgarage", r"tiefgarage\w*|parkdeck\w*"),
    R("fenster", "Große Sanierungen", "mittel", "Fenster", r"fenster(austausch|erneuerung|sanierung)\w*|austausch der fenster"),
    R("elektro", "Große Sanierungen", "mittel", "Elektrik", r"elektro(sanierung|anlage|installation)\w*|elektrik\w*|e-check"),
    R("brand", "Große Sanierungen", "mittel", "Brandschutz", r"brandschutz\w*|rettungsweg\w*|feuerwehr\w*|rauchabzug\w*"),
    R("keller", "Große Sanierungen", "mittel", "Keller / Abdichtung", r"keller\w*(abdichtung|sanierung)|horizontalsperre\w*|drainage\w*"),
    R("modern", "Große Sanierungen", "mittel", "Modernisierung / bauliche Veränderung", r"modernisierung\w*|bauliche ver(ä|ae)nderung\w*|kernsanierung\w*|generalsanierung\w*"),
    R("kosten_gross", "Große Sanierungen", "info", "Kostenvoranschlag / Angebote", r"kostenvoranschl(a|ä)g\w*|kostensch(ä|ae)tzung\w*|angebot(e|en)? (eingeholt|vorgelegt|von)|auftrag\w* (erteilt|vergeben)"),
    # --- Energie ---
    R("heizung", "Energie & Heizung", "hoch", "Heizungsanlage", r"heizung\w*(austausch|erneuerung|sanierung|anlage|kessel|ausfall)|heizkessel\w*|heizungstausch\w*|brenner\w*"),
    R("geg", "Energie & Heizung", "mittel", "GEG / Heizungsgesetz / Wärmeplanung", r"\bgeg\b|geb(ä|ae)udeenergiegesetz\w*|heizungsgesetz\w*|w(ä|ae)rmeplanung\w*|65\s?%|austauschpflicht\w*"),
    R("waermepumpe", "Energie & Heizung", "mittel", "Wärmepumpe / Fernwärme / PV", r"w(ä|ae)rmepumpe\w*|fernw(ä|ae)rme\w*|photovoltaik\w*|pv-anlage\w*|solaranlage\w*"),
    R("daemmung", "Energie & Heizung", "mittel", "Dämmung / energetische Sanierung", r"energetisch\w* sanier\w*|d(ä|ae)mmung\w*|sanierungsfahrplan\w*|isfp\b"),
    R("co2", "Energie & Heizung", "info", "CO2-Kosten", r"co2-?(kosten|preis|abgabe)\w*|kohlendioxidkosten\w*"),
    # --- Offen / vertagt ---
    R("vertagt", "Offene & vertagte Themen", "mittel", "Thema vertagt / zurückgestellt",
      r"vertagt|zur(ü|ue)ckgestellt|auf die n(ä|ae)chste (eigent(ü|ue)mer)?versammlung|in der n(ä|ae)chsten versammlung erneut|wird erneut behandelt"),
    R("angebote_fehlen", "Offene & vertagte Themen", "mittel", "Angebote fehlen / Entscheidung offen",
      r"angebote? (liegen|liegt) (noch )?nicht vor|weitere angebote (einholen|einzuholen)|keine angebote|noch nicht entschieden|keine entscheidung|wird (noch )?gepr(ü|ue)ft"),
    R("ursache_unklar", "Offene & vertagte Themen", "mittel", "Ursache unklar", r"ursache\w* (ist |sind )?(noch )?(unklar|unbekannt|nicht (bekannt|gekl(ä|ae)rt|gefunden))"),
    R("beschlussunf", "Offene & vertagte Themen", "mittel", "Versammlung nicht beschlussfähig", r"nicht beschlussf(ä|ae)hig|beschlussunf(ä|ae)hig\w*|wiederholungsversammlung", negatable=False),
    R("abgelehnt", "Offene & vertagte Themen", "info", "Beschlussantrag abgelehnt", r"(antrag|beschlussantrag|beschluss)[^.]{0,40}abgelehnt|mehrheitlich abgelehnt", negatable=False),
    # --- Rechtsstreit ---
    R("anfechtung", "Rechtsstreit", "hoch", "Beschlussanfechtung", r"anfechtung\w*|angefochten|beschlussklage\w*"),
    R("klage", "Rechtsstreit", "hoch", "Klage / Gericht", r"\bklage\w*|\bgericht(e|en|s|lich\w*)?\b|rechtsstreit\w*|verfahren gegen|amtsgericht\w*|landgericht\w*"),
    R("anwalt", "Rechtsstreit", "mittel", "Rechtsanwalt beauftragt", r"rechtsanw(a|ä)lt\w*|anwaltlich\w*|kanzlei\w*|rechtsberat\w*"),
    # --- Verwaltung ---
    R("verwalterwechsel", "Verwaltung", "mittel", "Verwalterwechsel / Abberufung",
      r"verwalterwechsel\w*|abberufung\w*|neuer verwalter|neue(n)? (haus)?verwaltung|verwaltervertrag\w*[^.]{0,40}(gek(ü|ue)ndigt|beendet|nicht verl(ä|ae)ngert)"),
    R("entlastung", "Verwaltung", "mittel", "Entlastung nicht erteilt", r"entlastung[^.]{0,40}(nicht erteilt|verweigert|abgelehnt)", negatable=False),
    R("unterlagen", "Verwaltung", "mittel", "Unterlagen fehlen / Abrechnung verspätet",
      r"(jahresabrechnung|wirtschaftsplan|abrechnung)[^.]{0,50}(fehlt|fehlerhaft|versp(ä|ae)tet|nicht vorgelegt|noch nicht erstellt)"),
    R("beirat", "Verwaltung", "info", "Verwaltungsbeirat", r"verwaltungsbeirat\w*|beirat\w*", negatable=False),
    # --- Nutzung / Konflikte ---
    R("streit", "Nutzung & Konflikte", "mittel", "Streit / Beschwerden", r"beschwerde\w*|\bstreit\w*|konflikt\w*|l(ä|ae)rmbel(ä|ae)stig\w*|abmahnung\w*|hausfrieden\w*"),
    R("kurzzeit", "Nutzung & Konflikte", "info", "Kurzzeitvermietung / Gewerbe", r"ferienwohnung\w*|kurzzeitvermiet\w*|airbnb|gewerbe\w*einheit|gewerbliche nutzung\w*|zweckentfremd\w*"),
    R("sondernutzung", "Nutzung & Konflikte", "info", "Sondernutzungsrecht / Teilungserklärung ändern",
      r"sondernutzungsrecht\w*|(ä|ae)nderung der teilungserkl(ä|ae)rung|gemeinschaftsordnung\w*[^.]{0,30}(ge(ä|ae)ndert|(ä|ae)nderung)"),
]

RULE_BY_ID = {r.id: r for r in RULES}

NEG_BEFORE = re.compile(r"\b(kein\w*|nicht|ohne|weder)\b[^.;:,]{0,25}$", re.IGNORECASE)
NEG_AFTER = re.compile(r"^[^.;:]{0,40}\b(nicht (erforderlich|notwendig|geplant|vorgesehen|n(ö|oe)tig)|entf(ä|ae)llt|ausgeschlossen)\b", re.IGNORECASE)

AMOUNT_RE = re.compile(
    r"(?:(?:€|EUR|Euro)\s*(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?))"
    r"|(?:(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|EUR\b|Euro\b|T€|TEUR\b|Mio\.?\s*(?:€|EUR|Euro)))",
    re.IGNORECASE,
)


def parse_amount(raw: str) -> float | None:
    s = raw.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def amounts_in(text: str) -> list[float]:
    out = []
    for m in AMOUNT_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        val = parse_amount(raw)
        if val is None:
            continue
        tail = text[m.end() - 8 : m.end()].lower()
        if "mio" in tail:
            val *= 1_000_000
        elif "t€" in tail or "teur" in tail:
            val *= 1000
        if val >= 1:
            out.append(val)
    return out


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def snippet_around(flat: str, start: int, end: int, width: int = 220) -> str:
    a = max(0, start - width)
    b = min(len(flat), end + width)
    # an Wortgrenzen schneiden
    if a > 0:
        sp = flat.find(" ", a)
        a = sp + 1 if 0 <= sp < start else a
    if b < len(flat):
        sp = flat.rfind(" ", end, b)
        b = sp if sp > end else b
    s = flat[a:b]
    return ("… " if a > 0 else "") + s + (" …" if b < len(flat) else "")


SENT_END = re.compile(r"(?<=[a-zäöüß)€\d])[.!?]\s+(?=[A-ZÄÖÜ])|\bTOP\s?\d", re.UNICODE)


def sentence_window(flat: str, start: int, end: int, extra: int = 1) -> str:
    """Der Satz mit dem Treffer plus `extra` folgende Sätze (Beträge stehen oft im Folgesatz)."""
    a = 0
    for m in SENT_END.finditer(flat, max(0, start - 400), start):
        a = m.end() if not m.group(0).upper().startswith("TOP") else m.start()
    b = end
    for _ in range(extra + 1):
        m = SENT_END.search(flat, b + 1)
        if not m:
            b = len(flat)
            break
        if m.group(0).upper().startswith("TOP"):
            b = m.start()
            break
        b = m.end()
    a = max(a, start - 150)
    return flat[a:min(b, end + 250)], start - a


def nearest_amount(flat: str, start: int, end: int) -> float | None:
    """Erster Betrag nach dem Treffer im selben/folgenden Satz, sonst der nächstgelegene davor."""
    win, offset = sentence_window(flat, start, end)
    after = amounts_in(win[offset:])
    if after:
        return after[0]
    before = amounts_in(win[:offset])
    return before[-1] if before else None


def is_negated(flat: str, start: int, end: int) -> bool:
    return bool(NEG_BEFORE.search(flat[max(0, start - 60) : start]) or NEG_AFTER.search(flat[end : end + 60]))


def scan_page(text: str) -> list[dict]:
    """Findet Regeltreffer auf einer Seite. Ein Treffer je Regel und Seite (mit Zähler)."""
    flat = one_line(text)
    results: dict[str, dict] = {}
    for rule in RULES:
        for m in rule.regex.finditer(flat):
            negated = rule.negatable and is_negated(flat, m.start(), m.end())
            key = rule.id + ("_neg" if negated else "")
            marked = flat[: m.start()] + "\x01" + m.group(0) + "\x02" + flat[m.end() :]
            snip = snippet_around(marked, m.start(), m.end() + 2)
            amt = None if negated else nearest_amount(flat, m.start(), m.end())
            if key in results:
                results[key]["hits"] += 1
                if amt:
                    results[key]["amount_eur"] = max(results[key]["amount_eur"] or 0, amt)
                continue
            results[key] = {
                "rule_id": rule.id,
                "category": rule.category,
                "severity": "info" if negated else rule.severity,
                "title": rule.title + (" (verneint)" if negated else ""),
                "snippet": snip,
                "match": m.group(0),
                "amount_eur": amt,
                "hits": 1,
            }
    return list(results.values())


# ---------- Kennzahlen ----------

RL_RE = re.compile(r"(erhaltungs|instandhaltungs|instandsetzungs)?r(ü|ue)cklage", re.IGNORECASE)
STAND_RE = re.compile(r"\b(stand|bestand|endbestand|saldo|guthaben|verm(ö|oe)gen|kontostand|per|zum|am)\b", re.IGNORECASE)
ZUF_RE = re.compile(r"zuf(ü|ue)hrung|einzahlung|zuweisung|dotierung", re.IGNORECASE)
ENT_RE = re.compile(r"entnahme|verwendung|ausgabe|auszahlung|aufl(ö|oe)sung", re.IGNORECASE)
HG_RE = re.compile(r"\b(hausgeld|wohngeld)\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(20[0-4]\d)\b")


def scan_figures(text: str) -> list[dict]:
    """Sucht Zahlenkandidaten für Rücklage und Hausgeld. Der Nutzer wählt den richtigen Wert aus."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    out = []
    seen = set()
    for i, ln in enumerate(lines):
        ctx = ln if amounts_in(ln) else " ".join(lines[i : i + 2])
        if len(ctx) > 400:
            ctx = ctx[:400]
        kind = None
        amount_src = ctx
        rl = RL_RE.search(ctx)
        if rl and RL_RE.search(ln):
            amount_src = ctx[rl.start():]
            if ENT_RE.search(ctx):
                kind = "ruecklage_entnahme"
            elif ZUF_RE.search(ctx):
                kind = "ruecklage_zufuehrung"
            elif STAND_RE.search(ctx):
                kind = "ruecklage_stand"
        elif HG_RE.search(ln) and amounts_in(ctx):
            kind = "hausgeld"
        if not kind:
            continue
        for val in amounts_in(amount_src)[:3]:
            if val < 10:
                continue
            key = (kind, round(val, 2))
            if key in seen:
                continue
            seen.add(key)
            year = YEAR_RE.findall(ctx)
            out.append({"kind": kind, "value_eur": val, "context": ctx, "year": int(year[-1]) if year else None})
    return out
