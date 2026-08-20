"""Base vectorielle Chroma : indexation des chunks + recherche par similarité.

L'embedding utilise le modèle par défaut intégré à ChromaDB
(all-MiniLM-L6-v2, format ONNX) : aucune clé API requise. Le modèle est
téléchargé automatiquement (une seule fois, mis en cache) au premier
appel qui nécessite un embedding.

Chaque chunk porte en métadonnées son `document_id`, son `site_id` et son
`source_type`, ce qui permet de réindexer proprement un document et de
cloisonner la recherche par site client.
"""
import chromadb

from .chunking import chunk_text
from .config import Config

_client = chromadb.PersistentClient(path=Config.CHROMA_DIR)
_collection = _client.get_or_create_collection("skapa_documents")


def index_document(
    doc_id: int,
    source_url: str,
    title: str,
    content: str,
    site_id: str | None = None,
    source_type: str = "html",
) -> None:
    """(Ré)indexe un document : supprime ses anciens chunks puis ajoute les nouveaux."""
    delete_document(doc_id)

    chunks = chunk_text(content)
    if not chunks:
        return

    ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
    metadata = {
        "document_id": doc_id,
        "source_url": source_url,
        "title": title,
        "site_id": site_id or Config.DEFAULT_SITE_ID,
        "source_type": source_type,
    }
    _collection.add(ids=ids, documents=chunks, metadatas=[dict(metadata) for _ in chunks])


def delete_document(doc_id: int) -> None:
    """Supprime tous les chunks d'un document (avant réindexation ou suppression)."""
    existing = _collection.get(where={"document_id": doc_id})
    if existing["ids"]:
        _collection.delete(ids=existing["ids"])


def search(query: str, top_k: int = 4, site_id: str | None = None) -> list[dict]:
    """Retourne les chunks les plus proches de la question.

    Si `site_id` est fourni, la recherche est limitée aux documents de ce site
    (une même API peut servir plusieurs sites clients sans mélanger leurs
    contenus). Sans `site_id`, on cherche dans tout l'index.
    """
    count = _collection.count()
    if count == 0:
        return []

    results = _collection.query(
        query_texts=[query],
        n_results=min(top_k, count),
        where={"site_id": site_id} if site_id else None,
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    hits = []
    for text, meta in zip(results["documents"][0], results["metadatas"][0]):
        hits.append(
            {
                "text": text,
                "source_url": meta.get("source_url", ""),
                "title": meta.get("title", ""),
                "source_type": meta.get("source_type", ""),
            }
        )
    return hits


def stats() -> dict:
    """Nombre de chunks indexés (diagnostic via /api/health)."""
    return {"chunks": _collection.count()}
