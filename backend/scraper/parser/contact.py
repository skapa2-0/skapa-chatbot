"""Extraction du bloc contact / coordonnées depuis le pied de page."""

import re

from bs4 import BeautifulSoup

from scraper.parser.html_clean import clean_lines

_CONTACT_RE = re.compile(
    r"(@|\+?\d[\d .-]{7,}\d|contact|adresse|address|horaires|t[ée]l|email|mail|"
    r"rue|avenue|boulevard|siret|copyright|©|\b\d{5}\b)", re.I)


def extract_site_info(html):
    """Texte du pied de page / bloc contact (téléphone, email, adresse…).
    Indexé une seule fois par site (sinon répété sur chaque page)."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    parts = []
    for el in soup.find_all(["footer", "address"]) + soup.select('[class*="contact"], [id*="contact"]'):
        txt = clean_lines(el.get_text("\n"))
        if txt and _CONTACT_RE.search(txt) and txt not in parts:
            parts.append(txt)
    for a in soup.select('a[href^="mailto:"], a[href^="tel:"]'):
        val = a["href"].split(":", 1)[1].split("?")[0].strip()
        label = "Email" if a["href"].startswith("mailto") else "Téléphone"
        line = f"{label} : {val}"
        if val and line not in parts:
            parts.append(line)
    text = "\n".join(parts)
    return text[:4000]
