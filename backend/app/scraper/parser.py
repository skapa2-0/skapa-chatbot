"""
Parser générique :
  1. clean_html()       -> titre + texte principal (trafilatura, repli BeautifulSoup)
  2. extract_site_info()-> coordonnées du pied de page (contact, adresse, horaires…)
  3. chunk_text()       -> découpe récursive (paragraphes > lignes > phrases > mots)
  4. parse_page()       -> chunks + métadonnées prêts à indexer

Pourquoi trafilatura : c'est l'extracteur de contenu principal le plus
fiable en open source (benchmarks ScrapingHub/trafilatura) ; il retire
menus, bannières cookies et blocs répétés bien mieux qu'une liste fixe
de balises. Si la page est atypique et qu'il renvoie trop peu de texte,
on retombe sur BeautifulSoup.

Avant : découpe tous les 800 caractères au milieu des mots, et le
footer (souvent le seul endroit avec téléphone / adresse / email) était
supprimé -> « Comment vous contacter ? » n'avait jamais de réponse.
"""

import hashlib
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app import config
from scraper.spider import domain_key

CHUNK_SIZE = config.env_int("SCRAPER_CHUNK_SIZE", 1000)
CHUNK_OVERLAP = config.env_int("SCRAPER_CHUNK_OVERLAP", 150)
MIN_MAIN_TEXT = 200

try:
    import trafilatura
except ImportError:  # dépendance optionnelle
    trafilatura = None


def _title(soup):
    # og:title est préféré : il est souvent plus lisible que le <title> (sans le nom de site répété)
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content", "").strip():
        return og["content"].strip()
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    h1 = soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else ""


def _description(soup):
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _clean_lines(text):
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
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


NOISE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "svg",
              "form", "iframe", "template", "aside", "button", "dialog"]
NOISE_SELECTORS = (
    '[role="navigation"], [role="banner"], [role="contentinfo"], [role="dialog"], '
    '[aria-hidden="true"], [class*="cookie" i], [id*="cookie" i], [class*="consent" i], '
    '[id*="consent" i], [class*="gdpr" i], [class*="rgpd" i], [class*="newsletter" i], '
    '[class*="breadcrumb" i], [class*="skip-link" i]'
)


def _preclean(html):
    """Retire menus, bandeaux cookies, scripts… et aplatit les tableaux en
    lignes « cellule | cellule » (sinon prix et intitulés sont séparés)."""
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


def _bs4_text(soup):
    """Repli : texte brut de la page (déjà nettoyée par _preclean)."""
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    for level in range(1, 7):
        for h in root.find_all(f"h{level}"):
            h.replace_with(f"\n\n{'#' * level} {h.get_text(' ', strip=True)}\n\n")
    for br in root.find_all("br"):
        br.replace_with("\n")
    for block in root.find_all(["p", "li", "tr", "div", "section", "article", "dd", "dt"]):
        block.insert_after("\n")
    return _clean_lines(root.get_text(separator="\n"))


def clean_html(html, url=None):
    """Retourne (titre, texte) avec la hiérarchie des titres en markdown (#, ##…)."""
    title = _title(BeautifulSoup(html or "", "html.parser"))
    cleaned = _preclean(html)

    text = ""
    if trafilatura is not None and html:
        try:
            text = trafilatura.extract(
                str(cleaned), url=url, output_format="markdown", include_tables=True,
                include_links=False, include_images=False, include_comments=False,
                favor_recall=True, deduplicate=True,
            ) or ""
        except Exception as exc:  # trafilatura ne doit jamais casser le pipeline
            print(f"[parser] trafilatura a échoué sur {url}: {exc}")
            text = ""

    # trafilatura est parfois trop strict (pages courtes, mises en page atypiques)
    fallback = _bs4_text(cleaned)
    if len(text) < MIN_MAIN_TEXT or len(fallback) > 2 * len(text) + 200:
        if len(fallback) > len(text):
            text = fallback

    return title, _clean_lines(text)


_CONTACT_RE = re.compile(
    r"(@|\+?\d[\d .-]{7,}\d|contact|adresse|address|horaires|t[ée]l|email|mail|"
    r"rue|avenue|boulevard|siret|copyright|©|\b\d{5}\b)", re.I)


def extract_site_info(html):
    """
    Texte du pied de page / bloc contact (téléphone, email, adresse…).
    Indexé une seule fois par site (sinon répété sur chaque page).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    parts = []
    for el in soup.find_all(["footer", "address"]) + soup.select('[class*="contact"], [id*="contact"]'):
        txt = _clean_lines(el.get_text("\n"))
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


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Découpe récursive : essaie de couper sur les paragraphes, puis les
    lignes, les phrases, les mots. Les morceaux se chevauchent de
    `overlap` caractères pour ne pas perdre le contexte aux frontières.
    """
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be strictly less than chunk_size ({chunk_size})"
        )
    separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

    def split(t, seps):
        if len(t) <= chunk_size:
            return [t]
        sep = next((s for s in seps if s == "" or s in t), "")
        if sep == "":
            step = chunk_size - overlap
            return [t[i:i + chunk_size] for i in range(0, len(t), step)]
        parts = t.split(sep)
        pieces = [p + sep for p in parts[:-1]] + [parts[-1]]
        out = []
        rest = seps[seps.index(sep) + 1:]
        for p in pieces:
            out.extend(split(p, rest) if len(p) > chunk_size else [p])
        return out

    pieces = [p for p in split(text, separators) if p.strip()]

    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) > chunk_size:
            chunks.append(current.strip())
            # chevauchement : on reprend la fin du chunk précédent, sur une frontière de mot
            tail = current[-overlap:] if overlap else ""
            if " " in tail:
                tail = tail[tail.index(" ") + 1:]
            current = tail if len(tail) + len(piece) <= chunk_size else ""
        current += piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _chunk_id(url, i):
    return hashlib.sha1(f"{url}#{i}".encode()).hexdigest()[:24] + f"-{i}"


def parse_page(url, html, depth=0):
    """Chunks prêts à indexer. Chaque chunk commence par le titre de la page :
    l'embedding « sait » de quelle page il vient, ce qui améliore la recherche."""
    title, text = clean_html(html, url=url)
    description = _description(BeautifulSoup(html or "", "html.parser"))
    if description and description[:60] not in text:
        text = f"{description}\n\n{text}" if text else description

    source_domain = domain_key(url)
    scraped_at = datetime.now(timezone.utc).isoformat()
    header = f"Page : {title}\n" if title else ""

    return [
        {
            "id": _chunk_id(url, i),
            "text": f"{header}{chunk}",
            "metadata": {
                "url": url,
                "title": title,
                "source_domain": source_domain,
                "scraped_at": scraped_at,
                "depth": depth,
                "chunk_index": i,
                "kind": "page",
            },
        }
        for i, chunk in enumerate(chunk_text(text))
    ]


def site_info_chunks(url, info_text, site_name=""):
    """Chunks « informations de contact » du site (issus du footer)."""
    if not info_text:
        return []
    domain = domain_key(url)
    scraped_at = datetime.now(timezone.utc).isoformat()
    header = f"Informations de contact et coordonnées{(' – ' + site_name) if site_name else ''}\n"
    return [
        {
            "id": _chunk_id(f"site-info:{domain}", i),
            "text": header + chunk,
            "metadata": {
                "url": url,
                "title": "Coordonnées / contact",
                "source_domain": domain,
                "scraped_at": scraped_at,
                "depth": 0,
                "chunk_index": i,
                "kind": "site_info",
            },
        }
        for i, chunk in enumerate(chunk_text(info_text))
    ]
