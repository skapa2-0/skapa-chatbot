"""Helpers HTTP partagés : création de session et fetch avec repli UA."""

from urllib.parse import urljoin

import requests

from scraper.spider.const import BROWSER_UA, MAX_WORKERS, REQUEST_TIMEOUT, USER_AGENT
from scraper.spider.safe_url import is_safe_url

_MAX_REDIRECTS = 5


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    adapter = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS * 2)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def fetch(session, url):
    """GET avec suivi manuel des redirections (5 max) + vérification SSRF à chaque saut."""
    if not is_safe_url(url):
        raise ValueError(f"URL refusée (SSRF) : {url}")

    current_url = url
    for _ in range(_MAX_REDIRECTS):
        resp = session.get(current_url, timeout=REQUEST_TIMEOUT, allow_redirects=False)
        if resp.status_code in (403, 406, 429) and session.headers.get("User-Agent") != BROWSER_UA:
            session.headers["User-Agent"] = BROWSER_UA
            resp = session.get(current_url, timeout=REQUEST_TIMEOUT, allow_redirects=False)

        if resp.is_redirect:
            location = resp.headers.get("Location", "")
            next_url = urljoin(current_url, location)
            if not is_safe_url(next_url):
                raise ValueError(f"Redirection SSRF bloquée vers : {next_url}")
            current_url = next_url
            continue

        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp

    raise requests.TooManyRedirects(f"Trop de redirections pour {url}")
