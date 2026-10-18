"""Helpers HTTP partagés : création de session et fetch avec repli UA."""

import requests

from scraper.spider.const import BROWSER_UA, MAX_WORKERS, REQUEST_TIMEOUT, USER_AGENT


def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    adapter = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS * 2)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def fetch(session, url):
    """GET avec repli automatique sur UA navigateur si le site bloque les bots."""
    resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if resp.status_code in (403, 406, 429) and session.headers.get("User-Agent") != BROWSER_UA:
        session.headers["User-Agent"] = BROWSER_UA
        resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp
