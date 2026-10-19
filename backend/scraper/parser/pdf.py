"""Détection et extraction de texte depuis les PDF (PyMuPDF)."""

from urllib.parse import urlparse

from app import config as _config
from scraper.parser.html_clean import clean_lines

PDF_MAX_MB = _config.env_int("SCRAPER_PDF_MAX_MB", 10)


def is_pdf(url: str, content_type: str) -> bool:
    """Vrai si la réponse est un PDF (Content-Type ou extension .pdf)."""
    if "application/pdf" in (content_type or "").lower():
        return True
    return urlparse(url).path.lower().endswith(".pdf")


def extract_pdf_text(data: bytes, url: str) -> tuple[str, str]:
    """Lit un PDF et retourne (titre, texte). Retourne ("", "") en cas d'échec."""
    if len(data) > PDF_MAX_MB * 1024 * 1024:
        print(f"[parser] PDF ignoré (trop grand > {PDF_MAX_MB} Mo) : {url}")
        return "", ""

    try:
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                print(f"[parser] PDF ignoré (chiffré) : {url}")
                return "", ""

            title = (doc.metadata.get("title") or "").strip()
            if not title:
                path = urlparse(url).path
                title = (path.rstrip("/").rsplit("/", 1)[-1]
                         .replace(".pdf", "").replace("-", " ").replace("_", " "))

            raw = "\n\n".join(page.get_text() for page in doc[:50])
            text = clean_lines(raw)

        if not text:
            print(f"[parser] PDF ignoré (aucun texte, peut-être scanné) : {url}")
            return "", ""

        return title, text

    except Exception as exc:
        print(f"[parser] PDF ignoré (erreur lecture) : {url} — {exc}")
        return "", ""
