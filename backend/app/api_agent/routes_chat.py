"""Route /chat : question au chatbot RAG."""
import re

from flask import jsonify, request

from app import llm
from app.api_agent import app
from app.api_agent.rag_helpers import (
    clean_history, default_platform_name, domain_count, retrieve,
)
from app.api_agent.chat_prompt import build_system_prompt, cited_links
from app.api_agent.site_map import format_site_map, site_map
from app.metadata import get_site
from scraper.spider import domain_key

# Mots-clés qui rendent les boutons d'action pertinents pour la réponse.
# Tolère les fautes courantes (condidater, candider…).
_ACTION_QUESTION_RE = re.compile(
    r'contact|candidat|cond[io]dat|postuler|inscri|rencontr|rendez.?vous|\brdv\b|'
    r'tarif|prix|co[uû]t|financ|devis|d[eé]mo|r[eé]serv|apply|signup|'
    r'rejoindre|particip|s.inscri|soumettre|demande',
    re.I,
)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Missing 'message' field"}), 400
    user_message = user_message[:2000]

    site_url = data.get("site_url")
    source_domain = domain_key(site_url) if site_url else None
    platform_name = data.get("platform_name") or default_platform_name(source_domain)
    history = clean_history(data.get("history"))

    if source_domain and domain_count(source_domain) == 0:
        return jsonify({
            "reply": (f"Je n'ai pas encore de contenu pour {source_domain}. "
                      "Lancez d'abord l'analyse du site (« Analyser et adapter »), "
                      "puis reposez votre question."),
            "sources_used": 0, "sources": [],
            "site_filter": source_domain, "platform_name": platform_name,
            "indexed": False, "actions": [], "links": [],
        })

    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    followup = f"{last_user}\n{user_message}" if last_user and len(user_message) < 60 else None

    try:
        hits = retrieve(user_message, source_domain, followup)
    except Exception as exc:
        app.logger.exception("Recherche Chroma échouée : %s", exc)
        return jsonify({"error": f"Recherche dans la base impossible : {exc}"}), 503

    context = ("\n\n---\n\n".join(
        f"[Source : {h['meta'].get('title') or 'page'} — {h['meta'].get('url', 'inconnue')}]"
        f"\n{h['text']}" for h in hits
    ) if hits else "(Aucune information trouvée dans la base pour l'instant.)")

    # Plan du site : titres + liens de toutes les pages (pour les questions « liste »)
    pages = site_map(source_domain, limit=500) if source_domain else []
    if pages:
        context += "\n\n" + format_site_map(pages[:40])

    # Injecte les actions du site dans le contexte pour que le LLM cite les bons liens
    site_info = get_site(source_domain) if source_domain else {}
    raw_actions = (site_info or {}).get('actions') or []
    if raw_actions:
        lines = "\n".join(f"- {a['label']} : {a['url']}" for a in raw_actions)
        context += f"\n\nACTIONS DISPONIBLES SUR CE SITE (liens directs à citer) :\n{lines}"

    system_prompt = build_system_prompt(platform_name, source_domain, context)
    try:
        reply_text = llm.chat(system_prompt, [*history, {"role": "user", "content": user_message}])
    except llm.LLMError as exc:
        return jsonify({"error": str(exc)}), 503

    sources, seen = [], set()
    for h in hits:
        url = h["meta"].get("url")
        if url and url not in seen and h["meta"].get("kind") != "site_info":
            seen.add(url)
            sources.append({"url": url, "title": h["meta"].get("title", "")})

    # N'envoie les boutons d'action que si la question est liée à une action
    actions = raw_actions if _ACTION_QUESTION_RE.search(user_message) else []

    # Boutons « En savoir plus » : seulement les pages que la réponse cite vraiment
    links = cited_links(reply_text, pages, exclude_urls=[a["url"] for a in actions])

    return jsonify({
        "reply": reply_text or "Je n'ai pas pu formuler de réponse.",
        "links": links,
        "sources_used": len(hits),
        "sources": sources[:5],
        "site_filter": source_domain or "all",
        "platform_name": platform_name,
        "indexed": bool(hits),
        "actions": actions,
    })
