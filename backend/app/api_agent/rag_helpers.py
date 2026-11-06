"""Helpers de récupération (RAG) et d'historique pour la route /chat."""

import re

from app import config
from app.api_agent import MAX_HISTORY
from app.chroma_client import get_collection

_FORMATION_KEYWORDS = {
    "formation", "formations", "programme", "programmes", "cours",
    "catalogue", "apprendre", "tarif", "prix", "coût", "durée",
    "certification", "istqb", "parcours", "offre", "proposez",
}
# Secondary query that semantically matches the indexed catalogue chunks
_CATALOGUE_PROBE = (
    "Fondamentaux IA ISTQB Product Builder Agentic Claude GenAI "
    "multi-agents RAG ingénierie agentique Cursor Lovable managers"
)


# Questions qui demandent une énumération (« quelles sont les... », « liste »...)
LIST_QUERY_RE = re.compile(
    r"\b(quel(le)?s?\s+(sont|formations?|services?|offres?|produits?|types?|cours)|"
    r"liste|toutes?\s+les|tous\s+les|que\s+propose|qu.est.ce\s+que\s+vous\s+propos|"
    r"catalogue|disponibles?)\b", re.I)


def is_list_query(text):
    return bool(LIST_QUERY_RE.search(text or ""))


def _diverse(hits, k, per_page):
    """Garde au plus `per_page` passages par page, dans l'ordre de pertinence."""
    out, per = [], {}
    for h in hits:
        url = h["meta"].get("url", "")
        if per.get(url, 0) >= per_page:
            continue
        per[url] = per.get(url, 0) + 1
        out.append(h)
        if len(out) >= k:
            break
    return out


def _is_formation_query(query):
    words = set(query.lower().split())
    return bool(words & _FORMATION_KEYWORDS)


def default_platform_name(domain):
    if not domain:
        return "ce site"
    name = domain.split(".")[0].replace("-", " ").replace("_", " ")
    return name.title()


def domain_count(domain):
    res = get_collection().get(where={"source_domain": domain}, include=[], limit=100000)
    return len(res.get("ids", []))


def clean_history(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for m in raw[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = str(m.get("content") or "").strip()[:2000]
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    while out and out[0]["role"] != "user":
        out.pop(0)
    merged = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n" + m["content"]
        else:
            merged.append(m)
    if merged and merged[-1]["role"] == "user":
        merged.pop()
    return merged


def _query(collection, text, domain, n):
    kwargs = {"query_texts": [text], "n_results": n,
              "include": ["documents", "metadatas", "distances"]}
    if domain:
        kwargs["where"] = {"source_domain": domain}
    res = collection.query(**kwargs)
    return [
        {"text": d, "meta": m or {}, "distance": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def retrieve(query, domain, followup_query=None):
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return []
    listing = is_list_query(query)
    k = min(max(config.RAG_TOP_K, 10) if listing else config.RAG_TOP_K, total)
    # On demande plus de candidats puis on garde des passages de pages variées :
    # une question « liste » doit couvrir plusieurs pages, pas une seule.
    pool = _query(collection, query, domain, min(total, k * 3))
    hits = _diverse(pool, k, per_page=2 if listing else 3)
    if followup_query:
        seen = {h["text"] for h in hits}
        extra = [h for h in _query(collection, followup_query, domain, k) if h["text"] not in seen]
        hits = hits[: max(3, k - 2)] + extra[:2]

    # For formation/catalogue queries, inject catalogue chunks that semantic
    # search misses (the catalogue page ranks poorly against "quelles formations").
    if _is_formation_query(query):
        seen_texts = {h["text"] for h in hits}
        catalogue_hits = [
            h for h in _query(collection, _CATALOGUE_PROBE, domain, k)
            if h["text"] not in seen_texts and "catalogue" in h["meta"].get("url", "")
        ]
        if catalogue_hits:
            # Keep top 3 original hits for context, replace rest with catalogue
            hits = hits[:3] + catalogue_hits[:max(3, k - 3)]

    if domain and not any(h["meta"].get("kind") == "site_info" for h in hits):
        info = collection.get(where={"$and": [{"source_domain": domain}, {"kind": "site_info"}]},
                              include=["documents", "metadatas"], limit=1)
        if info.get("ids"):
            hits.append({"text": info["documents"][0], "meta": info["metadatas"][0], "distance": None})
    return hits
