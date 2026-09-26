import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402

from app import db, settings  # noqa: E402


def setup_module():
    db.conn()


def test_defaults_und_speichern():
    settings.set_many({"llm_provider": "openai", "openai_base_url": "http://x:11434/v1/", "llm_chunk_chars": "8000"})
    settings._invalidate()
    assert settings.provider() == "openai"
    assert settings.get("openai_base_url") == "http://x:11434/v1"
    assert settings.get("llm_chunk_chars") == 8000
    assert settings.model() == "qwen2.5:14b"


def test_validierung():
    with pytest.raises(ValueError):
        settings.set_many({"llm_provider": "irgendwas"})
    with pytest.raises(ValueError):
        settings.set_many({"ocr_dpi": 5})
    with pytest.raises(ValueError):
        settings.set_many({"openai_base_url": "ftp://x"})


def test_passwort():
    settings.set_password("richtig-geheim")
    assert settings.password_set()
    assert settings.check_password("richtig-geheim")
    assert not settings.check_password("falsch")
    settings.set_password(None)
    assert not settings.password_set()


def test_maskierung():
    assert settings.mask("sk-ant-abcdefgh1234") == "•••• 1234"
    assert settings.mask("") == ""
