"""Garde-fous de /api/scrape/start (endpoint public appelé par le front, sans token).

Tout est en mémoire : c'est cohérent avec gunicorn à 1 worker (voir gunicorn.conf.py).
"""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from app import config, jobs
from app.chroma_client import get_collection
from app.metadata import get_site

MAX_PAGES = config.env_int("SCRAPE_PUBLIC_MAX_PAGES", 30)
MAX_DEPTH = config.env_int("SCRAPE_PUBLIC_MAX_DEPTH", 3)
RATE_PER_HOUR = config.env_int("SCRAPE_PUBLIC_RATE", 3)
MAX_JOBS = config.env_int("SCRAPE_PUBLIC_MAX_JOBS", 2)
COOLDOWN_HOURS = config.env_float("SCRAPE_PUBLIC_COOLDOWN_HOURS", 24)

_hits = defaultdict(deque)
_lock = threading.Lock()


def allowed_domains():
    """SCRAPE_ALLOWED_DOMAINS=site1.fr,site2.com -> {"site1.fr", "site2.com"} (vide = tous)."""
    raw = config.env("SCRAPE_ALLOWED_DOMAINS", "") or ""
    out = set()
    for d in raw.split(","):
        d = d.strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if d:
            out.add(d)
    return out


def client_ip(req):
    """IP du visiteur. Derrière un proxy (Railway, nginx), l'entrée la plus à
    droite de X-Forwarded-For est celle ajoutée par le proxy : les entrées de
    gauche peuvent être inventées par le client."""
    xff = req.headers.get("X-Forwarded-For", "")
    if xff.strip():
        return xff.split(",")[-1].strip()
    return req.remote_addr or "unknown"


def hit_rate_limit(ip):
    """Enregistre un lancement. False si l'IP a dépassé RATE_PER_HOUR."""
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and q[0] < now - 3600:
            q.popleft()
        if len(q) >= RATE_PER_HOUR:
            return False
        q.append(now)
        # évite que le dict grossisse indéfiniment
        if len(_hits) > 10000:
            for k in [k for k, v in _hits.items() if not v]:
                del _hits[k]
        return True


def running_public_jobs():
    return jobs.running_count()


def recent_index(domain):
    """Si le domaine a été indexé il y a moins de COOLDOWN_HOURS, renvoie un
    résultat au format attendu par le front (sans relancer de scraping)."""
    if COOLDOWN_HOURS <= 0:
        return None
    res = get_collection().get(where={"source_domain": domain},
                               include=["metadatas", "documents"], limit=20000)
    metas = res.get("metadatas") or []
    if not metas:
        return None
    try:
        last = max(datetime.fromisoformat(m["scraped_at"]) for m in metas if m.get("scraped_at"))
    except ValueError:
        return None
    age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    if age_h >= COOLDOWN_HOURS:
        return None

    pages = [m for m in metas if m.get("kind", "page") == "page"]
    site_url = min(pages or metas, key=lambda m: m.get("depth", 0)).get("url")
    site_info = get_site(domain) or {}
    return {
        "status": "success", "cached": True, "site_url": site_url,
        "source_domain": domain, "site_title": site_info.get("site_title", ""),
        "pages_scraped": len({m.get("url") for m in pages}),
        "chunks_created": len(metas), "indexed_at": last.isoformat(),
        "brand_color": site_info.get("brand_color"),
    }


def reset_for_tests():
    with _lock:
        _hits.clear()
