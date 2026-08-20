"""Extracteurs : transforment une source brute en documents indexables.

Chaque fonction renvoie une `list[dict]` au même format, quelle que soit
l'origine des données (HTML, JSON, CSV, PDF, WordPress, Shopify, RSS...) :

    {"source_url", "title", "content", "external_id", "source_type", "site_id"}

C'est ce format unique qui permet à `ingestion.upsert_documents()` puis au
pipeline RAG (chunking -> Chroma -> Claude) de traiter toutes les
plateformes exactement de la même manière.
"""
import csv
import hashlib
import io
import json
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests

from . import source_detector as sd
from .config import Config

# Clés/colonnes sans valeur informative pour le chatbot : on ne les indexe pas.
IGNORED_KEYS = {
    "id",
    "uuid",
    "created_at",
    "updated_at",
    "inserted_at",
    "deleted_at",
    "password",
    "password_hash",
    "token",
    "api_key",
    "secret",
    "_links",
}

# Clés dans lesquelles chercher un titre lisible, par ordre de préférence.
TITLE_KEYS = ("title", "name", "label", "heading", "subject", "question", "slug")


def _headers() -> dict:
    return {"User-Agent": Config.SCRAPER_USER_AGENT}


def _read_bytes(target: str) -> bytes:
    """Lit une cible locale ou distante indifféremment."""
    if target.startswith(("http://", "https://")):
        response = requests.get(target, headers=_headers(), timeout=Config.INGEST_TIMEOUT)
        response.raise_for_status()
        return response.content
    with open(target, "rb") as handle:
        return handle.read()


def read_text(target: str) -> str:
    """Comme `_read_bytes`, décodé en texte : URL ou fichier local, même appel."""
    return _read_bytes(target).decode("utf-8", errors="replace")


def make_doc(site_id: str, source_type: str, source_url: str, title: str, content: str, seed: str = "") -> dict | None:
    """Fabrique un document normalisé, ou None s'il n'y a pas assez de contenu utile."""
    content = " ".join(str(content).split()) if "\n" not in str(content) else str(content).strip()
    if len(content) < Config.MIN_DOC_CHARS:
        return None

    title = str(title or source_url).strip() or source_url
    fingerprint = hashlib.sha256(f"{site_id}|{seed or source_url}".encode()).hexdigest()

    return {
        "source_url": source_url[:500],
        "title": title[:300],
        "content": content[: Config.MAX_DOC_CHARS],
        "external_id": fingerprint,
        "source_type": source_type,
        "site_id": site_id,
    }


# --------------------------------------------------------------------------
# JSON : n'importe quelle forme (liste, objet, imbrications) -> texte plat
# --------------------------------------------------------------------------


def flatten(value, prefix: str = "") -> list[str]:
    """Aplatit récursivement n'importe quelle structure JSON en lignes "clé: valeur"."""
    lines: list[str] = []

    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in IGNORED_KEYS:
                continue
            lines.extend(flatten(nested, f"{prefix}{key}."))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            lines.extend(flatten(nested, f"{prefix}{index}."))
    elif value not in (None, "", [], {}):
        label = prefix.rstrip(".").replace(".", " > ") or "valeur"
        lines.append(f"{label}: {value}")

    return lines


def find_records(payload) -> list:
    """Trouve la collection d'enregistrements dans une réponse JSON de forme inconnue.

    Gère les trois formes courantes : une liste racine, un objet contenant une
    liste (`{"products": [...]}`, `{"data": [...]}`), ou un objet unique.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # On privilégie les clés d'enveloppe habituelles, puis n'importe quelle liste d'objets.
        for key in ("data", "results", "items", "records", "products", "rows"):
            candidate = payload.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
        for candidate in payload.values():
            if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
                return candidate
        return [payload]
    return []


def guess_title(record: dict, fallback: str) -> str:
    for key in TITLE_KEYS:
        for actual_key, value in record.items():
            if actual_key.lower() == key and isinstance(value, (str, int, float)) and str(value).strip():
                return str(value)
    return fallback


def _record_id(record: dict, index: int) -> str:
    for key in ("id", "uuid", "slug", "handle", "permalink", "url"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return str(index)


def from_json(url: str, site_id: str, payload=None, source_type: str = sd.JSON) -> list[dict]:
    """Une API JSON quelconque : chaque enregistrement devient un document."""
    if payload is None:
        payload = json.loads(read_text(url))

    documents = []
    for index, record in enumerate(find_records(payload)):
        if not isinstance(record, dict):
            record = {"valeur": record}

        title = guess_title(record, f"{urlparse(url).path.strip('/') or 'json'} #{index + 1}")
        body = "\n".join([str(title), *flatten(record)])
        doc = make_doc(site_id, source_type, url, title, body, seed=f"{url}#{_record_id(record, index)}")
        if doc:
            documents.append(doc)

    return documents


# --------------------------------------------------------------------------
# HTML : site statique, SPA rendue en JS, sitemap
# --------------------------------------------------------------------------


def from_html(url: str, site_id: str, render: bool = False, max_pages: int | None = None) -> list[dict]:
    """Crawl du site puis extraction du texte de chaque page."""
    from scraper.parser import parse_page
    from scraper.spider import fetch_pages

    pages = fetch_pages(url, max_pages=max_pages or Config.SCRAPER_MAX_PAGES, render=render)
    return [doc for page_url, html in pages if (doc := parse_page(page_url, html, site_id=site_id))]


def _sitemap_urls(xml_text: str, base_url: str, depth: int = 0) -> list[str]:
    """Extrait les <loc> d'un sitemap, en suivant les sitemapindex imbriqués."""
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8", errors="replace"))
    except ElementTree.ParseError:
        return []

    locations = [element.text.strip() for element in root.iter() if element.tag.endswith("loc") and element.text]

    # Un sitemapindex pointe vers d'autres sitemaps : on descend d'un niveau.
    if root.tag.endswith("sitemapindex") and depth < 1:
        nested: list[str] = []
        for sitemap_url in locations[: Config.SITEMAP_MAX_CHILDREN]:
            try:
                response = requests.get(sitemap_url, headers=_headers(), timeout=Config.INGEST_TIMEOUT)
                response.raise_for_status()
                nested.extend(_sitemap_urls(response.text, base_url, depth + 1))
            except requests.RequestException:
                continue
        return nested

    return [urljoin(base_url, location) for location in locations]


def from_sitemap(url: str, site_id: str, xml_text: str | None = None, max_pages: int | None = None) -> list[dict]:
    """Un sitemap.xml donne la liste exhaustive des pages : bien mieux qu'un crawl à l'aveugle."""
    from scraper.parser import parse_page
    from scraper.spider import fetch_one

    if xml_text is None:
        xml_text = read_text(url)

    limit = max_pages or Config.SCRAPER_MAX_PAGES
    page_urls = _sitemap_urls(xml_text, url)[:limit]

    documents = []
    for page_url in page_urls:
        html = fetch_one(page_url)
        if not html:
            continue
        doc = parse_page(page_url, html, site_id=site_id, source_type=sd.SITEMAP)
        if doc:
            documents.append(doc)

    return documents


# --------------------------------------------------------------------------
# Flux RSS / Atom
# --------------------------------------------------------------------------


def _tag_text(item, *names: str) -> str:
    for child in item:
        tag = child.tag.split("}")[-1].lower()
        if tag in names:
            if child.text and child.text.strip():
                return child.text.strip()
            if tag == "link" and child.get("href"):
                return child.get("href")
    return ""


def from_feed(url: str, site_id: str, xml_text: str | None = None) -> list[dict]:
    """RSS ou Atom : chaque entrée devient un document."""
    if xml_text is None:
        xml_text = read_text(url)

    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8", errors="replace"))
    except ElementTree.ParseError:
        return []

    from scraper.parser import html_to_text

    documents = []
    for item in root.iter():
        if item.tag.split("}")[-1].lower() not in ("item", "entry"):
            continue

        title = _tag_text(item, "title") or "Article"
        link = _tag_text(item, "link", "id") or url
        body = _tag_text(item, "description", "summary", "content", "encoded")
        doc = make_doc(site_id, sd.FEED, link, title, f"{title}\n{html_to_text(body)}", seed=link)
        if doc:
            documents.append(doc)

    return documents


# --------------------------------------------------------------------------
# Fichiers : CSV, PDF, texte
# --------------------------------------------------------------------------


def from_csv(target: str, site_id: str) -> list[dict]:
    """Chaque ligne du CSV devient un document ; l'en-tête sert de noms de champs."""
    text = read_text(target)

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    documents = []
    for index, row in enumerate(reader):
        clean = {key: value for key, value in row.items() if key and value not in (None, "")}
        if not clean:
            continue
        title = guess_title(clean, f"Ligne {index + 1}")
        body = "\n".join([title, *flatten(clean)])
        doc = make_doc(site_id, sd.CSV, target, title, body, seed=f"{target}#row{index}")
        if doc:
            documents.append(doc)

    return documents


def from_pdf(target: str, site_id: str) -> list[dict]:
    """Un document par page de PDF (le chunking affinera ensuite)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("PDF ignoré : `pip install pypdf` requis.")
        return []

    reader = PdfReader(io.BytesIO(_read_bytes(target)))
    base_title = (reader.metadata.title if reader.metadata else None) or target.rstrip("/").split("/")[-1]

    documents = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # PDF corrompu ou page image-only
            print(f"PDF : page {number} illisible ({exc})")
            continue

        title = f"{base_title} - page {number}"
        doc = make_doc(site_id, sd.PDF, target, title, f"{title}\n{text}", seed=f"{target}#page{number}")
        if doc:
            documents.append(doc)

    return documents


def from_text(target: str, site_id: str) -> list[dict]:
    """Texte brut ou Markdown : un seul document (découpé en chunks à l'indexation)."""
    text = read_text(target)
    title = target.rstrip("/").split("/")[-1] or target
    doc = make_doc(site_id, sd.TEXT, target, title, text, seed=target)
    return [doc] if doc else []


# --------------------------------------------------------------------------
# Plateformes avec API dédiée : WordPress, Shopify
# --------------------------------------------------------------------------


def from_wordpress(url: str, site_id: str, max_pages: int | None = None) -> list[dict]:
    """API REST WordPress : pages + articles, propres et paginés, sans scraping."""
    from scraper.parser import html_to_text

    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    limit = max_pages or Config.SCRAPER_MAX_PAGES
    per_page = min(100, limit)

    documents = []
    for resource in ("pages", "posts"):
        if len(documents) >= limit:
            break
        try:
            response = requests.get(
                f"{origin}/wp-json/wp/v2/{resource}",
                headers=_headers(),
                params={"per_page": per_page, "_fields": "id,link,title,content,excerpt"},
                timeout=Config.INGEST_TIMEOUT,
            )
            response.raise_for_status()
            entries = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"WordPress : /{resource} inaccessible ({exc})")
            continue

        for entry in entries if isinstance(entries, list) else []:
            title = html_to_text((entry.get("title") or {}).get("rendered", "")) or "Sans titre"
            body = html_to_text((entry.get("content") or {}).get("rendered", ""))
            link = entry.get("link") or f"{origin}/?p={entry.get('id')}"
            doc = make_doc(site_id, sd.WORDPRESS, link, title, f"{title}\n{body}", seed=link)
            if doc:
                documents.append(doc)

    return documents[:limit]


def from_shopify(url: str, site_id: str, max_pages: int | None = None) -> list[dict]:
    """Catalogue Shopify via /products.json : titre, description, variantes, prix."""
    from scraper.parser import html_to_text

    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    limit = max_pages or Config.SCRAPER_MAX_PAGES

    try:
        response = requests.get(
            f"{origin}/products.json",
            headers=_headers(),
            params={"limit": min(250, limit)},
            timeout=Config.INGEST_TIMEOUT,
        )
        response.raise_for_status()
        products = response.json().get("products", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"Shopify : /products.json inaccessible ({exc})")
        return []

    documents = []
    for product in products[:limit]:
        title = product.get("title") or "Produit"
        link = f"{origin}/products/{product.get('handle', '')}"
        prices = ", ".join(
            f"{variant.get('title')}: {variant.get('price')}"
            for variant in product.get("variants", [])
            if variant.get("price")
        )
        body = "\n".join(
            part
            for part in [
                title,
                html_to_text(product.get("body_html") or ""),
                f"Type: {product.get('product_type')}" if product.get("product_type") else "",
                f"Tags: {', '.join(product.get('tags', []))}" if product.get("tags") else "",
                f"Prix: {prices}" if prices else "",
            ]
            if part
        )
        doc = make_doc(site_id, sd.SHOPIFY, link, title, body, seed=link)
        if doc:
            documents.append(doc)

    return documents
