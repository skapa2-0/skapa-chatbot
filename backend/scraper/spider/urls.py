"""Helpers d'URL : normalisation, comparaison de domaine, extraction de liens."""

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from scraper.spider.const import PDF_ENABLED, SKIP_EXTENSIONS, SKIP_PATH_PARTS, TRACKING_PARAMS


def domain_key(url_or_netloc):
    """'https://WWW.Site.fr:443/x' -> 'site.fr' (sert à comparer et filtrer)."""
    netloc = urlparse(url_or_netloc).netloc if "//" in url_or_netloc else url_or_netloc
    netloc = netloc.lower().split("@")[-1]
    host = netloc.split(":")[0]
    return host[4:] if host.startswith("www.") else host


def normalize_url(url):
    """Retire fragment + paramètres de tracking, normalise host et slash final."""
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PARAMS)
    ))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def same_domain(base_url, candidate_url):
    return domain_key(base_url) == domain_key(candidate_url)


def is_crawlable(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
    if not PDF_ENABLED and path.endswith(".pdf"):
        return False
    if path.endswith(SKIP_EXTENSIONS):
        return False
    return not any(part in path for part in SKIP_PATH_PARTS)


def extract_links(html, base_url):
    """Liens internes (même site) normalisés d'une page."""
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    base = urljoin(base_url, base_tag["href"]) if base_tag else base_url
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        full_url = normalize_url(urljoin(base, href))
        if same_domain(base_url, full_url) and is_crawlable(full_url):
            links.add(full_url)
    return links
