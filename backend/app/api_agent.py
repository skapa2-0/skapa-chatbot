"""Agent RAG (Retrieval-Augmented Generation).

1) `vectorstore.search` retrouve, via ChromaDB, les chunks les plus proches
   sémantiquement de la question (recherche vectorielle, pas juste des
   mots-clés en commun), éventuellement restreints à un `site_id`.
2) Ces chunks servent de contexte à Claude, qui rédige la réponse finale.

Le pipeline est indépendant de la plateforme d'origine des données : que le
contenu vienne d'un crawl HTML, d'une API JSON, de Shopify ou d'un PDF, il
est arrivé dans Chroma sous la même forme.
"""
from anthropic import Anthropic

from .config import Config
from .vectorstore import search

_client = Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None

_SYSTEM_PROMPT = (
    "Tu es l'assistant virtuel intégré à un site web. Réponds aux questions des "
    "visiteurs UNIQUEMENT à partir du contexte fourni ci-dessous. Si la réponse "
    "n'y figure pas, dis-le clairement et invite l'utilisateur à contacter le site. "
    "Reste concis, clair et amical."
)


def answer(question: str, site_id: str | None = None) -> dict:
    """Pipeline complet : retrieve (Chroma) puis generate (Claude). Retourne {answer, sources}."""
    hits = search(question, top_k=Config.TOP_K, site_id=site_id)

    if not hits:
        return {
            "answer": "Je n'ai pas trouvé d'information à ce sujet dans les données indexées pour l'instant.",
            "sources": [],
        }

    context = "\n\n---\n\n".join(f"Source : {hit['source_url']}\n{hit['text']}" for hit in hits)
    sources = sorted({hit["source_url"] for hit in hits})

    if not _client:
        # Pas de clé API configurée : on renvoie le meilleur extrait plutôt que de planter.
        return {"answer": hits[0]["text"], "sources": sources}

    message = _client.messages.create(
        model=Config.ANTHROPIC_MODEL,
        max_tokens=500,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Contexte :\n{context}\n\nQuestion : {question}"}],
    )
    text = "".join(block.text for block in message.content if block.type == "text")

    return {"answer": text, "sources": sources}
