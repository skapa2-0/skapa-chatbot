"""Titres de pages distincts.

Beaucoup de sites mettent le même <title> sur toutes les pages (« Skapa Academy »
partout) : impossible alors de distinguer les pages dans le chat. On remplace un
titre partagé par le <h1> de la page, sinon par un libellé tiré de l'URL.
"""

from collections import Counter
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


def h1_of(html):
    h1 = BeautifulSoup(html or "", "html.parser").find("h1")
    text = h1.get_text(" ", strip=True) if h1 else ""
    return " ".join(text.split())[:90]


def path_label(url):
    """/catalogue/genai-managers -> « Genai managers »."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts:
        return ""
    last = unquote(parts[-1]).rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    return last[:1].upper() + last[1:] if last else ""


def distinct_titles(prepared, html_by_url):
    """prepared : {url: (titre, texte)} -> même dict, titres partagés remplacés."""
    counts = Counter(t for t, _ in prepared.values() if t)
    out = {}
    for url, (title, text) in prepared.items():
        if title and counts[title] == 1:
            out[url] = (title, text)
            continue
        if urlparse(url).path in ("", "/"):
            out[url] = (title or "Accueil", text)
            continue
        better = h1_of(html_by_url.get(url)) or path_label(url) or title
        out[url] = (better, text)
    # Deux pages avec le même <h1> : on précise avec le libellé d'URL
    again = Counter(t for t, _ in out.values())
    for url, (title, text) in list(out.items()):
        label = path_label(url)
        if again[title] > 1 and label and label.lower() not in title.lower():
            out[url] = (f"{title} – {label}", text)
    return out
