"""KI-Anbindung: Anthropic-API oder jede OpenAI-kompatible API (Ollama, LM Studio, vLLM, OpenAI).

Nur httpx, keine SDKs, damit die Abhängigkeiten klein bleiben.
"""
import json
import re

import httpx

from . import config

CHUNK_SYSTEM = """Du bist ein erfahrener Prüfer für Wohnungseigentümergemeinschaften (WEG) in Deutschland.
Ein Kaufinteressent einer Eigentumswohnung lässt Unterlagen der WEG prüfen (Versammlungsprotokolle, Wirtschaftspläne, Jahresabrechnungen, Beschlusssammlungen, Teilungserklärung).
Deine Aufgabe: Finde alles, was für einen Käufer finanziell oder rechtlich relevant ist. Vor allem:
- beschlossene, geplante oder absehbare Sonderumlagen und ihre Höhe
- anstehende oder aufgeschobene Sanierungen (Dach, Fassade, Leitungen, Heizung, Balkone, Tiefgarage, Aufzug usw.)
- Schäden (Feuchtigkeit, Wasserschäden, Schimmel, Risse), Gutachten, Sanierungsstau
- Zustand und Entwicklung der Erhaltungsrücklage, Hausgelderhöhungen, Darlehen der Gemeinschaft
- Hausgeldrückstände einzelner Eigentümer, Liquiditätsprobleme
- Rechtsstreitigkeiten, Beschlussanfechtungen, Verwalterwechsel, Streit unter Eigentümern
- Themen, die immer wieder vertagt werden
- Besonderheiten zur Nutzung (Kurzzeitvermietung, Gewerbe, Sondernutzungsrechte)

Regeln:
- Erfinde nichts. Jeder Befund braucht ein wörtliches Zitat aus dem Text (maximal 200 Zeichen, exakt so wie im Text).
- Gib die Seitennummer an. Seiten sind mit "=== Seite N ===" markiert.
- Routine ohne Risiko (Begrüßung, Feststellung der Beschlussfähigkeit, normale Genehmigung einer unauffälligen Abrechnung) ist kein Befund.
- schwere: "hoch" = kann den Käufer viel Geld kosten oder ist ein ernstes Warnsignal; "mittel" = sollte man nachfragen; "info" = gut zu wissen.
- Beträge in Euro als Zahl ohne Tausenderpunkte (z. B. 185000.0), sonst null.

Antworte ausschließlich mit JSON in dieser Form:
{"befunde": [{"kategorie": "...", "schwere": "hoch|mittel|info", "titel": "kurz, max 80 Zeichen", "beschreibung": "1-3 Sätze, was das für den Käufer bedeutet", "seite": 3, "betrag_eur": null, "zitat": "..."}]}
Kategorien (nimm genau eine davon): Sonderumlage, Finanzen & Rücklage, Schäden & Mängel, Große Sanierungen, Energie & Heizung, Offene & vertagte Themen, Rechtsstreit, Verwaltung, Nutzung & Konflikte.
Wenn nichts Relevantes vorkommt: {"befunde": []}"""

SUMMARY_SYSTEM = """Du berätst einen Privatanleger, der eine vermietete oder selbst genutzte Eigentumswohnung kaufen möchte.
Du bekommst die Stammdaten, Kennzahlen und alle Befunde aus der Prüfung der WEG-Unterlagen.
Schreibe eine ehrliche, knappe Einschätzung auf Deutsch in Markdown mit genau diesen Abschnitten:

## Gesamteindruck
2-4 Sätze. Nenne das größte Risiko zuerst. Keine Beschönigung.

## Die größten Kostenrisiken
Aufzählung, sortiert nach möglicher Höhe. Wenn möglich mit Betrag, und wenn Miteigentumsanteil oder Wohnfläche bekannt sind, mit grob geschätztem Anteil für diese Wohnung (als Schätzung kennzeichnen). Seitenangaben in der Form (Dokument, S. N).

## Warnsignale zur Gemeinschaft und Verwaltung
Aufzählung, nur wenn es welche gibt.

## Fragen an Verkäufer oder Verwaltung vor dem Notartermin
5-10 konkrete Fragen, die sich aus den Befunden ergeben.

## Was in den Unterlagen fehlt
Welche Unterlagen oder Jahre fehlen für eine vollständige Prüfung.

Regeln: Stütze dich nur auf die gelieferten Befunde und Daten. Wenn etwas unklar ist, sag es. Du ersetzt keine Rechts- oder Steuerberatung, erwähne das in einem Satz am Ende."""


class LLMError(RuntimeError):
    pass


def _anthropic(system: str, user: str, max_tokens: int) -> str:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": config.default_model(),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=config.LLM_TIMEOUT,
    )
    if r.status_code != 200:
        raise LLMError(f"Anthropic-API {r.status_code}: {r.text[:400]}")
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _openai(system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    body = {
        "model": config.default_model(),
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(
        f"{config.OPENAI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        json=body,
        timeout=config.LLM_TIMEOUT,
    )
    if r.status_code != 200:
        raise LLMError(f"KI-API {r.status_code}: {r.text[:400]}")
    return r.json()["choices"][0]["message"]["content"] or ""


def complete(system: str, user: str, max_tokens: int = 4000, json_mode: bool = False) -> str:
    if not config.llm_enabled():
        raise LLMError("Keine KI konfiguriert (LLM_PROVIDER / API-Key prüfen).")
    try:
        if config.LLM_PROVIDER == "anthropic":
            return _anthropic(system, user, max_tokens)
        return _openai(system, user, max_tokens, json_mode)
    except httpx.HTTPError as e:
        raise LLMError(f"Verbindung zur KI fehlgeschlagen: {e}") from e


def parse_json_object(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise LLMError("KI-Antwort war kein gültiges JSON: " + text[:200])


def analyze_chunk(doc_label: str, chunk_text: str) -> list[dict]:
    user = f"Dokument: {doc_label}\n\n{chunk_text}"
    raw = complete(CHUNK_SYSTEM, user, max_tokens=6000, json_mode=True)
    data = parse_json_object(raw)
    items = data.get("befunde", []) if isinstance(data, dict) else []
    return [i for i in items if isinstance(i, dict)]


def summarize(payload: str) -> str:
    return complete(SUMMARY_SYSTEM, payload, max_tokens=4000)
