"""Crawler BFS : crawl() (requests, statique) et crawl_with_playwright() (SPA)."""

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from scraper.parser.pdf import extract_pdf_text, is_pdf
from scraper.spider.const import (
    DELAY_SECONDS, MAX_DEPTH, MAX_PAGES, MAX_WORKERS,
    REQUEST_TIMEOUT, USE_SITEMAP, USER_AGENT,
)
from scraper.spider.http_utils import fetch as _fetch, make_session as _make_session
from scraper.spider.playwright_engine import crawl_with_playwright
from scraper.spider.robots import Robots, discover_sitemap_urls
from scraper.spider.urls import (
    domain_key, extract_links, is_crawlable, normalize_url, same_domain,
)


def _seed_queue(start_url, robots):
    queue = deque([(start_url, 0)])
    sitemap_urls = set()
    if USE_SITEMAP:
        sitemap_urls = discover_sitemap_urls(start_url, getattr(robots, "sitemaps", []))
        queue.extend((u, 1) for u in sorted(sitemap_urls) if u != start_url)
    return queue, sitemap_urls


def crawl(start_url, max_pages=MAX_PAGES, max_depth=MAX_DEPTH, progress=None):
    """BFS concurrent (MAX_WORKERS threads). Retourne (pages, failed, urls_found)."""
    session = _make_session()
    start_url = normalize_url(start_url)
    try:
        start_url = normalize_url(_fetch(session, start_url).url)
    except requests.RequestException:
        pass

    robots = Robots(start_url)
    queue, sitemap_urls = _seed_queue(start_url, robots)
    lock, visited, pages, failed_count = threading.Lock(), set(), [], [0]
    all_urls_found = set(sitemap_urls)

    def fetch_one(url, depth):
        try:
            response = _fetch(session, url)
        except requests.RequestException as exc:
            print(f"[spider] echec {url}: {exc}")
            return None, None, depth, True
        final_url = normalize_url(response.url)
        if not same_domain(start_url, final_url):
            return None, None, depth, False
        content_type = response.headers.get("Content-Type", "text/html")
        if is_pdf(final_url, content_type):
            pdf_title, pdf_text = extract_pdf_text(response.content, final_url)
            if not pdf_text:
                return None, None, depth, False
            page = {"url": final_url, "depth": depth, "format": "pdf",
                    "title": pdf_title, "text": pdf_text}
            return final_url, page, depth, False
        if "html" not in content_type:
            return None, None, depth, False
        return final_url, response.text, depth, False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}

        def submit_pending():
            while queue and (len(pages) + len(futures)) < max_pages:
                url, depth = queue.popleft()
                with lock:
                    if url in visited or depth > max_depth or not robots.allowed(url):
                        continue
                    visited.add(url)
                futures[executor.submit(fetch_one, url, depth)] = (url, depth)

        submit_pending()
        while futures:
            for fut in list(as_completed(futures, timeout=REQUEST_TIMEOUT + 2)):
                orig_url, _ = futures.pop(fut)
                try:
                    final_url, html, depth, is_err = fut.result()
                except Exception as exc:
                    print(f"[spider] exception {orig_url}: {exc}")
                    failed_count[0] += 1
                    submit_pending()
                    continue
                if is_err or final_url is None:
                    failed_count[0] += 1 if is_err else 0
                    submit_pending()
                    continue
                with lock:
                    if final_url in visited and final_url != orig_url:
                        submit_pending()
                        continue
                    visited.add(final_url)
                if isinstance(html, dict):
                    # résultat PDF : déjà structuré, pas d'extraction de liens
                    pages.append(html)
                else:
                    pages.append({"url": final_url, "html": html, "depth": depth})
                print(f"[spider] depth={depth} ok ({len(pages)}/{max_pages}): {final_url}")
                if progress:
                    progress(len(pages), final_url)
                if depth < max_depth and isinstance(html, str):
                    new_links = extract_links(html, final_url)
                    with lock:
                        all_urls_found.update(new_links)
                        for link in new_links:
                            if link not in visited:
                                queue.append((link, depth + 1))
                if DELAY_SECONDS > 0:
                    time.sleep(DELAY_SECONDS)
                submit_pending()
    print(f"[spider] {len(pages)} pages, {failed_count[0]} echecs, {len(all_urls_found)} URLs")
    return pages, failed_count[0], len(all_urls_found)
