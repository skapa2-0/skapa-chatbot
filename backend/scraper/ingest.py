"""
Ingestion : prend les chunks produits par parser.py et les écrit dans
Chroma DB. C'est ici que ta base "s'ouvre / se met à jour
automatiquement" : collection.upsert() crée la base si elle n'existe
pas encore, et met à jour les chunks existants sinon (pas de doublons).
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.chroma_client import get_collection  # noqa: E402


def ingest_chunks(chunks):
    """chunks : liste de {"id", "text", "metadata"} (voir parser.parse_page)."""
    if not chunks:
        return 0

    collection = get_collection()

    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )

    return len(chunks)
