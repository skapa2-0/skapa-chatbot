"""
Parser générique : conserve la structure de la page (titres, sections,
lien texte) puis produit des chunks cohérents pour le RAG.
"""

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

CHUNK_SIZE = int(os.environ.get("SCRAPER_CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.environ.get("SCRAPER_CHUNK_OVERLAP", 150))


# Headings that mark "related / recommended" promotional sections.
# Matched against lowercased heading text — generic, not page-specific.
_RELATED_SECTION_KEYWORDS = (
    "pourraient aussi vous intéresser",
    "vous intéresser",
    "formations similaires",
    "related formations",
    "you might also like",
    "voir aussi",
    "recommandations",
)

# Headings that mark institutional boilerplate sections shared verbatim
# across every page.  Keeping them produces duplicate chunks that dominate
# RAG retrieval and drown out page-specific content.
_BOILERPLATE_SECTION_KEYWORDS = (
    "moyens pédagogiques",
    "modalités d'évaluation",
    "accessibilité",
    "handicap",
    "pedagogical",
    "accessibility",
    "your academy coach",
    "academy coach",
)


def clean_html(html):
    """Extrait le texte utile en conservant la hiérarchie des headings."""
    soup = BeautifulSoup(html, "html.parser")

    # ── Step 1 : strip tags that are never documentary content ──────────
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "noscript", "template", "svg"]):
        tag.decompose()

    # ── Step 2 : extract metadata cards BEFORE any structural surgery ───
    # Cards like Durée / Tarif Inter / Tarif Intra / Format / Participants
    # use a <p class="…muted-foreground"> for the label.  We convert each
    # card into a single "Label: value" line and replace the whole card
    # container so the raw card text is not duplicated later.
    for label_el in soup.find_all(
        "p",
        class_=lambda c: c and "muted-foreground" in (
            c if isinstance(c, str) else " ".join(c)
        ),
    ):
        label_text = label_el.get_text(" ", strip=True)
        if not label_text:
            continue
        card = label_el.parent  # the card wrapper div
        if not card:
            continue
        full = card.get_text(" ", strip=True)
        value = full.replace(label_text, "").strip()
        if value:
            card.replace_with(f"\n{label_text}: {value}\n")

    # ── Step 3 : remove "related formations" sections ───────────────────
    for container in soup.find_all(["section", "div", "aside"]):
        heading = container.find(["h2", "h3", "h4"])
        if heading:
            htext = heading.get_text(" ", strip=True).lower()
            if any(kw in htext for kw in _RELATED_SECTION_KEYWORDS):
                container.decompose()
                break

    # ── Step 4 : remove institutional boilerplate sections ──────────────
    # "Moyens pédagogiques", "Accessibilité & Handicap", etc. are identical
    # across every page — keeping them creates duplicate chunks that score
    # higher in retrieval than page-specific content.
    for container in soup.find_all(["section", "div", "aside"]):
        heading = container.find(["h2", "h3", "h4"])
        if heading:
            htext = heading.get_text(" ", strip=True).lower()
            if any(kw in htext for kw in _BOILERPLATE_SECTION_KEYWORDS):
                container.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    # ── Step 5 : convert headings to Markdown markers ───────────────────
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            heading = h.get_text(" ", strip=True)
            h.replace_with(f"\n{'#' * level} {heading}\n" if heading else "\n")

    # ── Step 6 : keep link labels as plain text ──────────────────────────
    for a in soup.find_all("a"):
        label = a.get_text(" ", strip=True)
        if label:
            a.replace_with(f" {label} ")

    # ── Step 7 : collapse whitespace and remove blank lines ─────────────
    text = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return title, text


def _split_large_section(text, chunk_size):
    """Découpe une section longue sur des frontières de mots."""
    words = text.split()
    chunks = []
    current = []
    length = 0
    for word in words:
        # Un token/URL très long ne doit jamais dépasser chunk_size.
        if len(word) > chunk_size:
            if current:
                chunks.append(" ".join(current))
                current, length = [], 0
            chunks.extend(word[i:i + chunk_size] for i in range(0, len(word), chunk_size))
            continue
        extra = len(word) + (1 if current else 0)
        if current and length + extra > chunk_size:
            chunks.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Découpe en sections, en évitant de couper systématiquement un heading."""
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size doit être > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap doit être >= 0 et < chunk_size")

    lines = text.splitlines()
    sections = []
    current = []
    for line in lines:
        if line.startswith("#") and current:
            sections.append("\n".join(current).strip())
            current = []
        current.append(line)
    if current:
        sections.append("\n".join(current).strip())

    raw_chunks = []
    for section in sections:
        if len(section) <= chunk_size:
            raw_chunks.append(section)
        else:
            raw_chunks.extend(_split_large_section(section, chunk_size))

    # Pour les petits morceaux successifs, on les regroupe sans dépasser la taille.
    chunks = []
    for item in raw_chunks:
        if chunks and len(chunks[-1]) + len(item) + 2 <= chunk_size:
            chunks[-1] += "\n" + item
        else:
            chunks.append(item)

    # Overlap léger entre chunks longs, au niveau des derniers mots.
    if overlap:
        result = []
        for i, chunk in enumerate(chunks):
            if i and len(result[-1]) > overlap:
                tail = result[-1][-overlap:]
                chunk = f"{tail}\n{chunk}"
                if len(chunk) > chunk_size:
                    chunk = chunk[-chunk_size:]
            result.append(chunk)
        return result
    return chunks


def parse_page(url, html, depth=0):
    title, text = clean_html(html)
    source_domain = urlparse(url).netloc
    scraped_at = datetime.now(timezone.utc).isoformat()
    chunks = chunk_text(text)

    result = []
    for i, chunk in enumerate(chunks):
        headings = re.findall(r"(?m)^#{1,6}\s+(.+)$", chunk)
        result.append({
            "id": f"{url}#{i}",
            "text": chunk,
            "metadata": {
                "url": url,
                "title": title,
                "heading": headings[-1] if headings else "",
                "source_domain": source_domain,
                "scraped_at": scraped_at,
                "depth": depth,
                "chunk_index": i,
            },
        })
    return result
