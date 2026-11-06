"""Nettoyage automatique : ne garde que le dernier site indexé dans ChromaDB.

Activé uniquement si SCRAPE_KEEP_ONLY_LAST=true.
Les domaines listés dans SCRAPE_KEEP_DOMAINS ne sont jamais supprimés.
"""

from app import config
from app.chroma_client import get_collection
from app.metadata import delete_site
from scraper.ingest import delete_domain


def _keep_domains() -> set:
    """Renvoie l'ensemble des domaines protégés (SCRAPE_KEEP_DOMAINS)."""
    raw = config.SCRAPE_KEEP_DOMAINS or ""
    out = set()
    for d in raw.split(","):
        d = d.strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if d:
            out.add(d)
    return out


def delete_other_sites(current_domain: str) -> int:
    """Supprime de ChromaDB et de SQLite tous les domaines qui ne sont ni
    *current_domain* ni dans SCRAPE_KEEP_DOMAINS.

    Renvoie le nombre de domaines supprimés."""
    protected = _keep_domains() | {current_domain.lower()}

    res = get_collection().get(include=["metadatas"])
    metas = res.get("metadatas") or []
    all_domains = {m["source_domain"] for m in metas if m and m.get("source_domain")}

    to_delete = {d for d in all_domains if d.lower() not in protected}
    for domain in to_delete:
        delete_domain(domain)
        delete_site(domain)
        print(f"[cleanup] domaine supprimé : {domain}")

    return len(to_delete)


def maybe_delete_others(current_domain: str) -> None:
    """Appelle delete_other_sites uniquement si SCRAPE_KEEP_ONLY_LAST=true."""
    if not config.SCRAPE_KEEP_ONLY_LAST:
        return
    n = delete_other_sites(current_domain)
    if n:
        print(f"[cleanup] {n} domaine(s) supprimé(s), seul '{current_domain}' conservé.")
