"""Text aus PDFs holen. Seiten ohne Textebene (Scans) werden per Tesseract-OCR gelesen."""
import re
import subprocess
from typing import Callable, Iterator

import pymupdf

from . import settings


def normalize(text: str) -> str:
    """Silbentrennung am Zeilenende auflösen und Leerraum vereinheitlichen."""
    text = text.replace("­", "")  # weiches Trennzeichen
    text = re.sub(r"(\w)-\n\s*([a-zäöüß])", r"\1\2", text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ocr_page(page: pymupdf.Page) -> str:
    pix = page.get_pixmap(dpi=settings.get("ocr_dpi"), colorspace=pymupdf.csGRAY)
    png = pix.tobytes("png")
    res = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", settings.get("ocr_lang"), "--psm", "3"],
        input=png,
        capture_output=True,
        timeout=180,
    )
    if res.returncode != 0:
        raise RuntimeError("OCR fehlgeschlagen: " + res.stderr.decode(errors="ignore")[:300])
    return res.stdout.decode("utf-8", errors="ignore")


def extract_pages(path: str, progress: Callable[[str], None] | None = None) -> Iterator[tuple[int, str, bool]]:
    """Liefert (Seitennummer ab 1, Text, per OCR gelesen?) für jede Seite."""
    with pymupdf.open(path) as doc:
        total = doc.page_count
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            used_ocr = False
            if len(text.strip()) < settings.get("ocr_min_chars"):
                if progress:
                    progress(f"OCR Seite {i + 1}/{total}")
                try:
                    text = ocr_page(page)
                    used_ocr = True
                except Exception as e:  # OCR-Fehler sollen nicht das ganze Dokument abbrechen
                    text = text + f"\n[OCR-Fehler: {e}]"
            elif progress and i % 10 == 0:
                progress(f"Text Seite {i + 1}/{total}")
            yield i + 1, normalize(text), used_ocr


def page_count(path: str) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count
