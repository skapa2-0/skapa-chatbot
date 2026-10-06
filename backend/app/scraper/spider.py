"""
Crawler web générique : BFS depuis start_url, reste sur le même site,
respecte MAX_PAGES / MAX_DEPTH. Deux moteurs :
  - crawl()                 : requests + BeautifulSoup (rapide, sites statiques)
  - crawl_with_playwright() : navigateur Chromium (sites React/Vue/Next…)

Corrections importantes par rapport à la version précédente :
  - suit les redirections (skapa-academy.fr -> www.skapa-academy.fr) : avant,
    tous les liens étaient rejetés comme "autre domaine" et une seule page
    était indexée ;
  - "www." est ignoré pour comparer les domaines ;
  - lit le sitemap.xml (trouve les pages non liées dans le menu) ;
  - ignore PDF / images / fichiers et paramètres de tracking (utm_…) ;
  - respecte robots.txt ;
  - réessaie avec un User-Agent navigateur si le site bloque les bots (403).
"""

import time
import xml.etree.ElementTree as ET
from collections import deque
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from app import config

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (compatible; SkapaChatbot/1.0)"
)
USER_AGENT = config.env("SCRAPER_USER_AGENT", BROWSER_UA)
MAX_PAGES = config.env_int("SCRAPER_MAX_PAGES", 100)
MAX_DEPTH = config.env_int("SCRAPER_MAX_DEPTH", 5)
DELAY_SECONDS = config.env_float("SCRAPER_DELAY_SECONDS", 0.3)
REQUEST_TIMEOUT = config.env_float("SCRAPER_REQUEST_TIMEOUT", 20)
PLAYWRIGHT_TIMEOUT = config.env_int("SCRAPER_PLAYWRIGHT_TIMEOUT", 30000)
RESPECT_ROBOTS = config.env_bool("SCRAPER_RESPECT_ROBOTS", True)
USE_SITEMAP = config.env_bool("SCRAPER_USE_SITEMAP", True)

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".zip", ".rar", ".7z", ".gz", ".tar", ".mp4", ".mp3", ".avi", ".mov", ".webm",
    ".wav", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".json",
    ".xml", ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".dmg", ".exe",
)
SKIP_PATH_PARTS = ("/wp-admin", "/wp-login", "/wp-json", "/cart", "/panier",
                   "/checkout", "/login", "/logout", "/feed", "/xmlrpc")
TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_", "_ga", "ref", "replytocom")


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
        if not any(k.lower().startswith(p) for p in TRACKING_PARAMS)
    ))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def same_domain(base_url, candidate_url):
    return domain_key(base_url) == domain_key(candidate_url)


def is_crawlable(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
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


class Robots:
    def __init__(self, start_url):
        self.parser = None
        self.sitemaps = []  # instance attribute, not shared class-level mutable default
        if not RESPECT_ROBOTS:
            return
        p = urlparse(start_url)
        try:
            resp = requests.get(f"{p.scheme}://{p.netloc}/robots.txt",
                                headers={"User-Agent": USER_AGENT}, timeout=10)
            if resp.ok and "text" in resp.headers.get("Content-Type", "text"):
                rp = robotparser.RobotFileParser()
                rp.parse(resp.text.splitlines())
                self.parser = rp
                self.sitemaps = rp.site_maps() or []
        except requests.RequestException:
            pass

    def allowed(self, url):
        if self.parser is None:
            return True
        return self.parser.can_fetch(USER_AGENT, url)


def discover_sitemap_urls(start_url, extra_sitemaps=(), limit=2000):
    """URLs listées dans sitemap.xml (+ sitemaps d'index, + ceux de robots.txt)."""
    p = urlparse(start_url)
    base = f"{p.scheme}://{p.netloc}"
    todo = deque(dict.fromkeys([*extra_sitemaps, f"{base}/sitemap.xml",
                                f"{base}/sitemap_index.xml"]))
    seen, urls = set(), set()
    while todo and len(seen) < 20 and len(urls) < limit:
        sm = todo.popleft()
        if sm in seen:
            continue
        seen.add(sm)
        try:
            resp = requests.get(sm, headers={"User-Agent": USER_AGENT}, timeout=10)
            if not resp.ok or not resp.content.lstrip().startswith(b"<"):
                continue
            root = ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError):
            continue
        is_index = root.tag.lower().endswith("sitemapindex")
        for loc in root.iter():
            if not (loc.tag.lower().endswith("loc") and loc.text):
                continue
            u = loc.text.strip()
            if is_index:
                todo.append(u)
            else:
                u = normalize_url(u)
                if same_domain(start_url, u) and is_crawlable(u):
                    urls.add(u)
    return urls


def _fetch(session, url):
    resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if resp.status_code in (403, 406, 429) and session.headers.get("User-Agent") != BROWSER_UA:
        # Certains pare-feux bloquent les User-Agent "bot" : on réessaie en navigateur
        session.headers["User-Agent"] = BROWSER_UA
        resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp


def _seed_queue(start_url, robots):
    queue = deque([(start_url, 0)])
    sitemap_urls = set()
    if USE_SITEMAP:
        sitemap_urls = discover_sitemap_urls(start_url, getattr(robots, "sitemaps", []))
        queue.extend((u, 1) for u in sorted(sitemap_urls) if u != start_url)
    return queue, sitemap_urls


def crawl(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH, progress=None):
    """
    BFS (requests + BeautifulSoup).
    Retourne (pages, pages_failed, urls_found_count)
    pages = [{"url", "html", "depth"}]
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT,
                            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})

    start_url = normalize_url(start_url)
    # Résout la redirection initiale (http->https, domaine nu -> www…)
    try:
        start_url = normalize_url(_fetch(session, start_url).url)
    except requests.RequestException:
        pass

    robots = Robots(start_url)
    queue, sitemap_urls = _seed_queue(start_url, robots)
    visited, pages, failed = set(), [], 0
    all_urls_found = set(sitemap_urls)

    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth:
            continue
        visited.add(url)
        if not robots.allowed(url):
            continue

        try:
            response = _fetch(session, url)
        except requests.RequestException as exc:
            print(f"[spider] echec {url}: {exc}")
            failed += 1
            continue

        final_url = normalize_url(response.url)
        if not same_domain(start_url, final_url):
            continue  # redirection vers un autre site
        if final_url != url:
            if final_url in visited:
                continue
            visited.add(final_url)
        if "html" not in response.headers.get("Content-Type", "text/html"):
            continue

        html = response.text
        pages.append({"url": final_url, "html": html, "depth": depth})
        print(f"[spider] depth={depth} ok: {final_url}")
        if progress:
            progress(len(pages), final_url)

        if depth < max_depth:
            new_links = extract_links(html, final_url)
            all_urls_found.update(new_links)
            for link in new_links:
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(DELAY_SECONDS)

    print(f"[spider] {len(pages)} pages, {failed} echecs, {len(all_urls_found)} URLs trouvees")
    return pages, failed, len(all_urls_found)


def _launch_chromium(p):
    try:
        return p.chromium.launch()
    except Exception as first_exc:
        # Navigateur installé ailleurs (ex. image Docker / CI)
        import glob
        import os
        candidates = [os.environ.get("PLAYWRIGHT_CHROMIUM_PATH", "")]
        candidates += glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
        candidates += glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"))
        for path in filter(None, candidates):
            if os.path.exists(path):
                return p.chromium.launch(executable_path=path)
        raise RuntimeError(
            "Chromium introuvable pour Playwright. Lance : playwright install chromium"
        ) from first_exc


def crawl_with_playwright(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH, progress=None):
    """Variante navigateur pour les sites qui génèrent leur contenu en JavaScript."""
    from playwright.sync_api import sync_playwright

    start_url = normalize_url(start_url)
    robots = Robots(start_url)
    queue, sitemap_urls = _seed_queue(start_url, robots)
    visited, pages, failed = set(), [], 0
    all_urls_found = set(sitemap_urls)

    with sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            context = browser.new_context(user_agent=BROWSER_UA, locale="fr-FR")
            # Pas besoin des images / polices / vidéos pour lire le texte
            context.route("**/*", lambda route: route.abort()
                          if route.request.resource_type in ("image", "media", "font")
                          else route.continue_())
            page = context.new_page()

            while queue and len(pages) < max_pages:
                url, depth = queue.popleft()
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)
                if not robots.allowed(url):
                    continue

                try:
                    resp = page.goto(url, timeout=PLAYWRIGHT_TIMEOUT, wait_until="domcontentloaded")
                    if resp is not None and resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status}")
                    if resp is not None and "html" not in (resp.headers.get("content-type") or "text/html"):
                        continue
                    try:
                        # networkidle peut ne jamais arriver (analytics, chat…) : on borne l'attente
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                except Exception as exc:
                    print(f"[spider-js] echec {url}: {exc}")
                    failed += 1
                    continue

                final_url = normalize_url(page.url)
                if not same_domain(start_url, final_url):
                    continue
                if final_url != url:
                    if final_url in visited:
                        continue
                    visited.add(final_url)

                html = page.content()
                pages.append({"url": final_url, "html": html, "depth": depth})
                print(f"[spider-js] depth={depth} ok: {final_url}")
                if progress:
                    progress(len(pages), final_url)

                if depth < max_depth:
                    new_links = extract_links(html, final_url)
                    all_urls_found.update(new_links)
                    for link in new_links:
                        if link not in visited:
                            queue.append((link, depth + 1))
        finally:
            browser.close()

    print(f"[spider-js] {len(pages)} pages, {failed} echecs, {len(all_urls_found)} URLs")
    return pages, failed, len(all_urls_found)


if __name__ == "__main__":
    target = config.env("SCRAPER_TARGET_URL", "https://example.com")
    results, _, _ = crawl(target, max_pages=10, max_depth=2)
    print(f"{len(results)} pages recuperees")
