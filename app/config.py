"""Konfiguration über Umgebungsvariablen (siehe .env.example)."""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "weglupe.db"

# KI-Anbieter: "anthropic", "openai" (jede OpenAI-kompatible API, z. B. Ollama) oder "none"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama").strip()
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))
# Zeichen pro KI-Abschnitt. Lokale Modelle mit kleinem Kontext: kleiner wählen (z. B. 8000).
LLM_CHUNK_CHARS = int(os.getenv("LLM_CHUNK_CHARS", "24000"))

OCR_LANG = os.getenv("OCR_LANG", "deu")
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
# Seiten mit weniger Zeichen als diesem Wert gelten als Scan und werden per OCR gelesen.
OCR_MIN_CHARS = int(os.getenv("OCR_MIN_CHARS", "40"))

# Optionaler Passwortschutz (HTTP Basic Auth). Leer = kein Schutz.
APP_USER = os.getenv("APP_USER", "weg")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))


def default_model() -> str:
    if LLM_MODEL:
        return LLM_MODEL
    if LLM_PROVIDER == "anthropic":
        return "claude-sonnet-5"
    if LLM_PROVIDER == "openai":
        return "qwen2.5:14b"
    return ""


def llm_enabled() -> bool:
    if LLM_PROVIDER == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    return LLM_PROVIDER == "openai"


DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
