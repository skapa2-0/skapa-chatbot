"""Route /chat : question au chatbot RAG."""

from flask import jsonify, request

from app import llm
from app.api_agent import app
from app.api_agent.rag_helpers import (
    clean_history, default_platform_name, domain_count, retrieve,
)
from scraper.spider import domain_key


def _build_system_prompt(platform_name, source_domain, context):
    domain_hint = f" ({source_domain})" if source_domain else ""
    return (
        f"Tu es l'assistant virtuel officiel du site {platform_name}{domain_hint}.\n\n"
        "Règles absolues :\n"
        "- Réponds dans la langue du visiteur (français par défaut), de façon courte, claire et professionnelle\n"
        "- Utilise UNIQUEMENT les informations du CONTEXTE ci-dessous (extraits du site)\n"
        "- Quand c'est utile, donne le lien de la page source (URL complète)\n"
        f"- Si la réponse n'est pas dans le contexte, dis honnêtement que tu ne disposes pas "
        f"de cette information et invite le visiteur à contacter {platform_name} directement\n"
        f"- Si la question ne concerne pas {platform_name}, recentre poliment la conversation\n"
        "- N'invente jamais de prix, de date, de nom ou de coordonnées\n"
        "- Réponds en texte simple, jamais de tableau. Pour lister des formations, "
        "utilise une liste à puces : nom en gras, puis durée, tarif et format sur la même ligne.\n\n"
        f"CONTEXTE :\n{context}"
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
            "indexed": False,
        })

    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    followup = f"{last_user}\n{user_message}" if last_user and len(user_message) < 60 else None

    try:
        hits = retrieve(user_message, source_domain, followup)
    except Exception as exc:
        app.logger.exception("Recherche Chroma échouée : %s", exc)
        return jsonify({"error": f"Recherche dans la base impossible : {exc}"}), 503

    context = ("\n\n---\n\n".join(
        f"[Source : {h['meta'].get('url', 'inconnue')}]\n{h['text']}" for h in hits
    ) if hits else "(Aucune information trouvée dans la base pour l'instant.)")

    system_prompt = _build_system_prompt(platform_name, source_domain, context)
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

    return jsonify({
        "reply": reply_text or "Je n'ai pas pu formuler de réponse.",
        "sources_used": len(hits),
        "sources": sources[:3],
        "site_filter": source_domain or "all",
        "platform_name": platform_name,
        "indexed": bool(hits),
    })
