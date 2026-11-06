"""Prompt système du chat + liens « En savoir plus » réellement cités par le LLM."""

import re
from collections import Counter

from app.api_agent.site_map import is_home, is_legal, norm_url
from scraper.pipeline.titles import path_label

_URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+")
MAX_LINKS = 2


def build_system_prompt(platform_name, source_domain, context):
    domain_hint = f" ({source_domain})" if source_domain else ""
    return (
        f"Tu es l'assistant virtuel officiel du site {platform_name}{domain_hint}.\n\n"
        "Règles absolues :\n"
        "- Réponds dans la langue du visiteur (français par défaut), de façon claire et "
        "professionnelle.\n"
        "- Utilise UNIQUEMENT les informations du CONTEXTE ci-dessous (extraits du site, "
        "plan du site, actions).\n"
        "- Réponds TOUJOURS d'abord avec le contenu concret : noms, durées, prix, dates, "
        "formats, étapes... Un lien vient seulement EN COMPLÉMENT, jamais à la place "
        "de la réponse.\n"
        "- Pour une question qui demande une liste (formations, services, produits...), "
        "énumère les éléments avec une liste à puces « - **Nom** – détails ». Appuie-toi "
        "aussi sur le PLAN DU SITE : les titres des pages indiquent ce qui existe.\n"
        "- N'écris pas les informations inconnues (pas de « non précisé ») : omets-les.\n"
        "- Quand tu cites une page, donne son URL complète exacte, telle qu'elle apparaît "
        "dans le contexte.\n"
        f"- Si la réponse n'est vraiment pas dans le contexte, dis-le honnêtement et invite "
        f"le visiteur à contacter {platform_name}.\n"
        f"- Si la question ne concerne pas {platform_name}, recentre poliment la conversation.\n"
        "- N'invente jamais de prix, de date, de nom ou de coordonnées.\n"
        "- Pas de tableau.\n\n"
        f"CONTEXTE :\n{context}"
    )


def cited_links(reply, pages, exclude_urls=()):
    """Pages du site dont l'URL apparaît dans la réponse (hors accueil, pages
    légales et URLs déjà affichées en bouton d'action). Max MAX_LINKS."""
    known = {norm_url(p["url"]): p for p in pages}
    shared = Counter(p["title"] for p in pages)
    skip = {norm_url(u) for u in exclude_urls}
    out, seen = [], set()
    for raw in _URL_RE.findall(reply or ""):
        url = norm_url(raw.rstrip(".,;:!?»"))
        page = known.get(url)
        if not page or url in seen or url in skip or is_home(url) or is_legal(url):
            continue
        seen.add(url)
        # Titre commun à plusieurs pages (ex. nom du site partout) : libellé tiré de l'URL
        title = page["title"]
        if shared[title] > 1 or any(o["title"] == title for o in out):
            title = path_label(page["url"]) or title
        out.append({"title": title, "url": page["url"]})
        if len(out) >= MAX_LINKS:
            break
    return out
