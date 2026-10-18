"""Extraction titre + texte principal (trafilatura, repli BeautifulSoup).
Si trafilatura renvoie trop peu de texte, on retombe sur BeautifulSoup."""

import re
from collections import Counter

from bs4 import BeautifulSoup

MIN_MAIN_TEXT = 200

try:
    import trafilatura
except ImportError:
    trafilatura = None


NOISE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "svg",
              "form", "iframe", "template", "aside", "button", "dialog"]
NOISE_SELECTORS = (
    '[role="navigation"], [role="banner"], [role="contentinfo"], [role="dialog"], '
    '[aria-hidden="true"], [class*="cookie" i], [id*="cookie" i], [class*="consent" i], '
    '[id*="consent" i], [class*="gdpr" i], [class*="rgpd" i], [class*="newsletter" i], '
    '[class*="breadcrumb" i], [class*="skip-link" i]'
)


def title_of(soup):
    og = soup.find("meta", attrs={"property": "og:title"})
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else ""


def description_of(soup):
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def clean_lines(text):
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    out, blank = [], False
    for line in lines:
        if not line:
            if not blank and out:
                out.append("")
            blank = True
            continue
        out.append(line)
        blank = False
    return "\n".join(out).strip()


def preclean(html):
    """Retire menus, scripts, bandeaux cookies ; aplatit les tableaux en lignes."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for el in soup.select(NOISE_SELECTORS):
        if el.name not in ("html", "body", "main"):
            el.decompose()
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(" | ".join(cells))
        new = soup.new_tag("div")
        for r in rows:
            p = soup.new_tag("p")
            p.string = r
            new.append(p)
        table.replace_with(new)
    return soup


def bs4_text(soup):
    """Repli : texte brut de la page (déjà nettoyée par preclean)."""
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    for level in range(1, 7):
        for h in root.find_all(f"h{level}"):
            h.replace_with(f"\n\n{'#' * level} {h.get_text(' ', strip=True)}\n\n")
    for br in root.find_all("br"):
        br.replace_with("\n")
    for block in root.find_all(["p", "li", "tr", "div", "section", "article", "dd", "dt"]):
        block.insert_after("\n")
    return clean_lines(root.get_text(separator="\n"))


def boilerplate_lines(texts, min_pages=3, min_ratio=0.6, min_length=15):
    """Lignes présentes sur ≥ `min_ratio` des pages ET ≥ `min_length` caractères.
    Capture l'en-tête commun du site (ex. tagline répétée sur toutes les pages)
    sans toucher aux labels courts (« Durée », « Format »…), qui portent du sens."""
    if not texts:
        return set()
    counts = Counter()
    for t in texts:
        for line in {ln.strip() for ln in t.splitlines() if ln.strip()}:
            counts[line] += 1
    threshold = max(min_pages, int(min_ratio * len(texts)))
    return {line for line, n in counts.items()
            if n >= threshold and len(line) >= min_length}


def clean_html(html, url=None):
    """Retourne (titre, texte) avec hiérarchie des titres en markdown (#, ##…)."""
    title = title_of(BeautifulSoup(html or "", "html.parser"))
    cleaned = preclean(html)

    text = ""
    if trafilatura is not None and html:
        try:
            text = trafilatura.extract(
                str(cleaned), url=url, output_format="markdown", include_tables=True,
                include_links=False, include_images=False, include_comments=False,
                favor_recall=True, deduplicate=True,
            ) or ""
        except Exception as exc:
            print(f"[parser] trafilatura a échoué sur {url}: {exc}")
            text = ""

    fallback = bs4_text(cleaned)
    if len(text) < MIN_MAIN_TEXT or len(fallback) > 2 * len(text) + 200:
        if len(fallback) > len(text):
            text = fallback

    return title, clean_lines(text)
