"""Lecture robots.txt et découverte des URL via sitemap.xml."""

import xml.etree.ElementTree as ET
from collections import deque
from urllib import robotparser
from urllib.parse import urlparse

import requests

from scraper.spider.const import RESPECT_ROBOTS, USER_AGENT
from scraper.spider.urls import is_crawlable, normalize_url, same_domain


class Robots:
    sitemaps = []

    def __init__(self, start_url):
        self.parser = None
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
                return
        except requests.RequestException:
            pass
        self.sitemaps = []

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
