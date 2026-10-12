"""Déduction du nom lisible du site à partir des pages scrapées."""

import re

from bs4 import BeautifulSoup


def site_name(pages, titles):
    """og:site_name, sinon le segment de titre commun à plusieurs pages."""
    soup = BeautifulSoup(pages[0]["html"], "html.parser")
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content", "").strip():
        return og["content"].strip()
    counts = {}
    for t in titles:
        for seg in re.split(r"\s+[|–—\-:·]\s+", t or ""):
            seg = seg.strip()
            if seg:
                counts[seg] = counts.get(seg, 0) + 1
    common = [s for s, n in counts.items() if n > 1]
    if common:
        return max(common, key=lambda s: counts[s])
    first = titles[0] if titles else ""
    return re.split(r"\s+[|–—\-:·]\s+", first)[0].strip() if first else ""
