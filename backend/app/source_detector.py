"""Détection automatique du type de source à ingérer.

Le but : pouvoir brancher le chatbot sur n'importe quelle plateforme sans
lui dire à l'avance de quoi il s'agit. On donne une cible (URL, chemin de
fichier, `supabase://table`) et `detect()` sonde pour décider quel
extracteur utiliser : site statique, SPA rendue en JS, API JSON,
WordPress, Shopify, sitemap, flux RSS/Atom, CSV, PDF, texte brut...

La détection se fait en cascade, du signal le plus fiable au plus faible :

1. schéma explicite (`supabase://`)          -> pas d'ambiguïté
2. fichier présent sur le disque             -> extension
3. en-tête `Content-Type` de la réponse HTTP -> type déclaré par le serveur
4. sniffing des premiers octets du corps     -> quand l'en-tête ment
5. sondes d'API de plateforme (wp-json...)   -> quand c'est du HTML
6. HTML statique ou SPA à rendre en JS       -> heuristique sur le DOM
"""
import os
from urllib.parse import urlparse

import requests

from .config import Config

# Types de sources reconnus (valeurs stockées dans Document.source_type).
SUPABASE = "supabase"
WORDPRESS = "wordpress"
SHOPIFY = "shopify"
SITEMAP = "sitemap"
FEED = "feed"
JSON = "json"
CSV = "csv"
PDF = "pdf"
TEXT = "text"
HTML = "html"
HTML_JS = "html_js"  # page dont le contenu n'existe qu'après exécution du JavaScript
UNKNOWN = "unknown"

# Extensions -> type, pour les fichiers locaux et les URLs sans Content-Type fiable.
_EXTENSIONS = {
    ".json": JSON,
    ".csv": CSV,
    ".tsv": CSV,
    ".pdf": PDF,
    ".txt": TEXT,
    ".md": TEXT,
    ".html": HTML,
    ".htm": HTML,
    ".xml": SITEMAP,
}

_PEEK_BYTES = 4096


def _headers() -> dict:
    return {"User-Agent": Config.SCRAPER_USER_AGENT}


def _origin(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def _looks_like_csv(peek: str) -> bool:
    """Un CSV plausible : plusieurs lignes ayant le même nombre de séparateurs."""
    lines = [line for line in peek.splitlines() if line.strip()][:5]
    if len(lines) < 2:
        return False
    counts = [line.count(",") + line.count(";") for line in lines]
    return counts[0] >= 1 and len(set(counts)) == 1


def _sniff_body(peek: str) -> str | None:
    """Devine le type à partir des premiers octets, quand le Content-Type n'aide pas."""
    stripped = peek.lstrip()
    lowered = stripped.lower()

    if stripped.startswith("%PDF"):
        return PDF
    if stripped[:1] in ("{", "["):
        return JSON
    if "<urlset" in lowered or "<sitemapindex" in lowered:
        return SITEMAP
    if "<rss" in lowered or "<feed" in lowered:
        return FEED
    if "<html" in lowered or "<!doctype html" in lowered:
        return HTML
    if stripped.startswith("<?xml"):
        return SITEMAP
    if _looks_like_csv(peek):
        return CSV
    return None


def _from_content_type(content_type: str, peek: str) -> str | None:
    """Traduit l'en-tête Content-Type en type de source."""
    ct = content_type.split(";")[0].strip().lower()
    lowered = peek.lower()

    if ct == "application/pdf":
        return PDF
    if ct.endswith("/json") or ct.endswith("+json"):
        return JSON
    if ct in ("text/csv", "application/csv"):
        return CSV
    if ct in ("application/xml", "text/xml") or ct.endswith("+xml"):
        # Un XML peut être un sitemap, un flux, ou autre : on regarde la racine.
        if "<urlset" in lowered or "<sitemapindex" in lowered:
            return SITEMAP
        if "<rss" in lowered or "<feed" in lowered:
            return FEED
        return SITEMAP  # par défaut on tente la liste d'URLs
    if ct == "text/html":
        return HTML
    if ct.startswith("text/"):
        # text/plain sert de fourre-tout : on sniffe le corps.
        return _sniff_body(peek) or TEXT
    return None


def _probe_platform_api(url: str) -> str | None:
    """Cherche une API de plateforme connue : bien plus fiable que scraper le HTML."""
    origin = _origin(url)

    # WordPress expose une API REST publique sur /wp-json/wp/v2/.
    try:
        response = requests.get(
            f"{origin}/wp-json/wp/v2/types",
            headers=_headers(),
            timeout=Config.INGEST_TIMEOUT,
        )
        if response.ok and "json" in response.headers.get("Content-Type", ""):
            return WORDPRESS
    except requests.RequestException:
        pass

    # Shopify expose le catalogue sur /products.json.
    try:
        response = requests.get(
            f"{origin}/products.json",
            headers=_headers(),
            timeout=Config.INGEST_TIMEOUT,
            params={"limit": 1},
        )
        if response.ok and isinstance(response.json(), dict) and "products" in response.json():
            return SHOPIFY
    except (requests.RequestException, ValueError):
        pass

    return None


def needs_javascript(html: str) -> bool:
    """Détecte une page dont le contenu n'apparaît qu'après exécution du JS.

    Signature typique d'une SPA (React/Vue/Angular) : un conteneur de montage
    vide, beaucoup de <script>, et quasiment pas de texte dans le HTML servi.
    """
    if Config.SCRAPER_RENDER_JS == "always":
        return True
    if Config.SCRAPER_RENDER_JS == "never":
        return False

    lowered = html.lower()

    # Conteneur de montage vide : <div id="root"></div>, <div id="app"></div>...
    for marker in ('id="root"', "id='root'", 'id="app"', "id='app'", 'id="__next"'):
        position = lowered.find(marker)
        if position != -1:
            tail = lowered[position : position + 400]
            if "></div>" in tail.replace(" ", "") or "></div>" in tail:
                return True

    # Peu de texte mais beaucoup de JavaScript -> le contenu est ailleurs.
    from scraper.parser import html_to_text  # import tardif : évite un cycle

    text_length = len(html_to_text(html))
    script_count = lowered.count("<script")
    return text_length < 400 and script_count >= 3


def detect(target: str) -> dict:
    """Renvoie {"kind", "target", "content_type", "peek"} pour la cible donnée.

    `kind` est l'une des constantes de ce module. `peek` contient le début du
    corps déjà téléchargé (évite un aller-retour réseau à l'extracteur).
    """
    target = (target or "").strip()
    result = {"kind": UNKNOWN, "target": target, "content_type": "", "peek": "", "reason": ""}

    # --- 1. Aucune cible : on retombe sur ce qui est configuré dans .env ---
    if not target:
        if Config.SUPABASE_URL and Config.SUPABASE_ANON_KEY and Config.SUPABASE_TABLES:
            return {**result, "kind": SUPABASE, "reason": "SUPABASE_* configuré dans .env"}
        if Config.SCRAPER_TARGET_URL:
            target = Config.SCRAPER_TARGET_URL
            result["target"] = target
        else:
            return {**result, "reason": "Aucune cible : renseigne body.source, SCRAPER_TARGET_URL ou SUPABASE_*."}

    # --- 2. Schéma explicite : supabase://table ---
    if target.startswith("supabase://"):
        return {**result, "kind": SUPABASE, "reason": "schéma supabase:// explicite"}

    # --- 3. Fichier local (upload, export, dump...) ---
    if not target.startswith(("http://", "https://")):
        if os.path.isfile(target):
            with open(target, "rb") as handle:
                peek = handle.read(_PEEK_BYTES).decode("utf-8", errors="replace")
            result["peek"] = peek

            extension = os.path.splitext(target)[1].lower()
            # Le contenu réel prime sur l'extension : un .xml peut être un
            # sitemap comme un flux RSS, un .txt peut contenir du JSON.
            kind = _sniff_body(peek) or _EXTENSIONS.get(extension)
            if kind:
                return {**result, "kind": kind, "reason": f"fichier local ({extension or 'sans extension'}), contenu analysé"}
            return {**result, "kind": TEXT, "reason": "fichier local, type indéterminé -> lu en texte"}

        # Un chemin explicite qui n'existe pas est une erreur, pas un domaine.
        if target.startswith(("/", "./", "../", "~")) or os.sep in target:
            return {**result, "reason": f"Fichier introuvable : {target}"}

        # Ni fichier ni URL : on suppose un domaine tapé sans schéma (ex: "exemple.com").
        if "." in target and " " not in target:
            target = f"https://{target}"
            result["target"] = target
        else:
            return {**result, "reason": f"Cible introuvable : ni fichier local, ni URL ({target})."}

    # --- 4. Requête HTTP : on lit l'en-tête et on jette un oeil au corps ---
    try:
        response = requests.get(
            target, headers=_headers(), timeout=Config.INGEST_TIMEOUT, stream=True, allow_redirects=True
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        raw = next(response.iter_content(_PEEK_BYTES), b"")
        peek = raw.decode(response.encoding or "utf-8", errors="replace")
        response.close()
    except requests.RequestException as exc:
        return {**result, "reason": f"Cible injoignable : {exc}"}

    result.update({"content_type": content_type, "peek": peek})

    kind = _from_content_type(content_type, peek)

    # --- 5. L'en-tête n'est pas concluant : on sniffe le corps ---
    if kind is None:
        kind = _sniff_body(peek)
    if kind is None:
        extension = os.path.splitext(urlparse(target).path)[1].lower()
        kind = _EXTENSIONS.get(extension, UNKNOWN)
    if kind is UNKNOWN:
        return {**result, "reason": f"Type non reconnu (Content-Type: {content_type or 'absent'})."}

    # --- 6. C'est du HTML : API de plateforme ? sinon statique ou SPA ? ---
    if kind == HTML:
        platform = _probe_platform_api(target)
        if platform:
            return {**result, "kind": platform, "reason": f"API {platform} détectée sur le domaine"}
        return {**result, "kind": HTML, "reason": f"HTML (Content-Type: {content_type})"}

    return {**result, "kind": kind, "reason": f"détecté via Content-Type: {content_type or 'sniffing du corps'}"}
