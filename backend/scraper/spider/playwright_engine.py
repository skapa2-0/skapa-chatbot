"""Variante Playwright pour les sites qui génèrent leur contenu en JavaScript."""

from collections import deque

from scraper.spider.const import (
    BROWSER_UA, MAX_DEPTH, MAX_PAGES, PLAYWRIGHT_TIMEOUT, USE_SITEMAP,
)
from scraper.spider.robots import Robots, discover_sitemap_urls
from scraper.spider.urls import extract_links, normalize_url, same_domain


def _seed_queue(start_url, robots):
    queue = deque([(start_url, 0)])
    sitemap_urls = set()
    if USE_SITEMAP:
        sitemap_urls = discover_sitemap_urls(start_url, getattr(robots, "sitemaps", []))
        queue.extend((u, 1) for u in sorted(sitemap_urls) if u != start_url)
    return queue, sitemap_urls


def _launch_chromium(p):
    try:
        return p.chromium.launch()
    except Exception as first_exc:
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
