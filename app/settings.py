"""Einstellungen, die in der App gepflegt werden. Gespeichert in der SQLite-Datenbank.

Umgebungsvariablen (z. B. LLM_PROVIDER) dienen nur noch als Startwert, solange in der
App nichts gespeichert wurde. Das ist praktisch für Docker, aber nicht nötig.
"""
import hashlib
import hmac
import os
import secrets
import threading
import time

from . import db

# key -> (Typ, Standardwert aus Umgebungsvariable)
SPEC: dict[str, tuple[type, str]] = {
    "llm_provider": (str, os.getenv("LLM_PROVIDER", "none")),
    "llm_model": (str, os.getenv("LLM_MODEL", "")),
    "anthropic_api_key": (str, os.getenv("ANTHROPIC_API_KEY", "")),
    "openai_base_url": (str, os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")),
    "openai_api_key": (str, os.getenv("OPENAI_API_KEY", "")),
    "llm_timeout": (int, os.getenv("LLM_TIMEOUT", "300")),
    "llm_chunk_chars": (int, os.getenv("LLM_CHUNK_CHARS", "24000")),
    "ocr_lang": (str, os.getenv("OCR_LANG", "deu")),
    "ocr_dpi": (int, os.getenv("OCR_DPI", "300")),
    "ocr_min_chars": (int, os.getenv("OCR_MIN_CHARS", "40")),
    "max_upload_mb": (int, os.getenv("MAX_UPLOAD_MB", "200")),
}
SECRETS = {"anthropic_api_key", "openai_api_key"}
PROVIDERS = ("none", "anthropic", "openai")
LIMITS = {"llm_timeout": (30, 3600), "llm_chunk_chars": (2000, 200_000), "ocr_dpi": (100, 600),
          "ocr_min_chars": (0, 1000), "max_upload_mb": (1, 2000)}

_cache: dict[str, str] | None = None
_cache_at = 0.0
_lock = threading.Lock()
CACHE_SECONDS = 3  # damit z. B. weglupe-reset-password ohne Neustart wirkt


def _load() -> dict[str, str]:
    global _cache, _cache_at
    with _lock:
        if _cache is None or time.monotonic() - _cache_at > CACHE_SECONDS:
            _cache = {r["key"]: r["value"] for r in db.q("SELECT key, value FROM settings")}
            _cache_at = time.monotonic()
        return _cache


def _invalidate():
    global _cache
    with _lock:
        _cache = None


def get(key: str):
    typ, default = SPEC[key]
    raw = _load().get(key, default)
    try:
        return typ(raw)
    except (TypeError, ValueError):
        return typ(default)


def get_raw(key: str) -> str | None:
    return _load().get(key)


def set_many(values: dict[str, object]):
    """Validiert und speichert. Unbekannte Schlüssel werden ignoriert."""
    clean: dict[str, str] = {}
    for key, val in values.items():
        if key not in SPEC or val is None:
            continue
        typ, _ = SPEC[key]
        if typ is int:
            try:
                ival = int(val)
            except (TypeError, ValueError):
                raise ValueError(f"{key}: keine ganze Zahl")
            lo, hi = LIMITS.get(key, (None, None))
            if lo is not None and not lo <= ival <= hi:
                raise ValueError(f"{key}: erlaubt sind {lo} bis {hi}")
            clean[key] = str(ival)
        else:
            sval = str(val).strip()
            if key == "llm_provider" and sval not in PROVIDERS:
                raise ValueError("Unbekannter KI-Anbieter")
            if key == "openai_base_url":
                sval = sval.rstrip("/")
                if sval and not sval.startswith(("http://", "https://")):
                    raise ValueError("Die Adresse muss mit http:// oder https:// beginnen")
            if key == "ocr_lang" and not all(p.isalnum() or p == "_" for p in sval.replace("+", "")):
                raise ValueError("Ungültige OCR-Sprache")
            clean[key] = sval
    with db.tx() as c:
        for k, v in clean.items():
            c.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                      (k, v))
    _invalidate()


# ---------- abgeleitete Werte ----------

def provider() -> str:
    p = get("llm_provider")
    return p if p in PROVIDERS else "none"


def model() -> str:
    m = get("llm_model")
    if m:
        return m
    return {"anthropic": "claude-sonnet-5", "openai": "qwen2.5:14b"}.get(provider(), "")


def llm_enabled() -> bool:
    p = provider()
    if p == "anthropic":
        return bool(get("anthropic_api_key"))
    if p == "openai":
        return bool(get("openai_base_url"))
    return False


def mask(secret: str) -> str:
    if not secret:
        return ""
    return "•••• " + secret[-4:] if len(secret) > 8 else "••••"


# ---------- Zugangspasswort ----------

def _hash(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return salt.hex() + "$" + dk.hex()


def set_password(password: str | None):
    with db.tx() as c:
        if password:
            c.execute("INSERT INTO settings (key, value) VALUES ('auth_password_hash', ?) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (_hash(password, secrets.token_bytes(16)),))
        else:
            c.execute("DELETE FROM settings WHERE key = 'auth_password_hash'")
    _invalidate()


def password_set() -> bool:
    return bool(_load().get("auth_password_hash") or os.getenv("APP_PASSWORD"))


def check_password(password: str) -> bool:
    stored = _load().get("auth_password_hash")
    if stored:
        salt_hex, _, _ = stored.partition("$")
        return hmac.compare_digest(_hash(password, bytes.fromhex(salt_hex)), stored)
    env_pw = os.getenv("APP_PASSWORD", "")
    return bool(env_pw) and hmac.compare_digest(password, env_pw)


def auth_user() -> str:
    return _load().get("auth_user") or os.getenv("APP_USER", "weg")
