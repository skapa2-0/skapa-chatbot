"""Accès partagé à la base Chroma (mode embarqué / PersistentClient).

La collection est liée au modèle d'embedding utilisé (son nom contient
le modèle). Changer de modèle = relancer « Analyser » sur le site.
Embeddings multilingues via Ollama (bge-m3 par défaut) quand c'est
dispo : le modèle par défaut Chroma est surtout entraîné en anglais.
"""

import os
import re
import threading

import chromadb
from chromadb.config import Settings

from app import config
from app.chroma_client.embedding import OllamaEmbeddingFunction, ollama_has_model

_lock = threading.Lock()
_client = None
_collection = None
_embedding_info = None


def _resolve_embedding():
    provider = config.EMBEDDING_PROVIDER
    if provider == "ollama" or (provider == "auto" and ollama_has_model(config.OLLAMA_EMBED_MODEL)):
        fn = OllamaEmbeddingFunction(config.OLLAMA_BASE_URL, config.OLLAMA_EMBED_MODEL)
        return fn, f"ollama:{config.OLLAMA_EMBED_MODEL}"
    if provider == "auto":
        print(
            f"[chroma] modèle d'embedding Ollama '{config.OLLAMA_EMBED_MODEL}' introuvable "
            f"-> modèle Chroma par défaut. Pour de meilleurs résultats en français : "
            f"ollama pull {config.OLLAMA_EMBED_MODEL}"
        )
    return None, "default:all-MiniLM-L6-v2"


def _collection_name(embedding_label):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", embedding_label).strip("-").lower()
    return f"{config.COLLECTION_BASE}-{slug}"[:63]


def get_client():
    global _client
    with _lock:
        if _client is None:
            os.makedirs(config.CHROMA_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(
                path=config.CHROMA_DIR,
                settings=Settings(anonymized_telemetry=False, allow_reset=False),
            )
        return _client


def get_collection():
    """Collection des chunks, créée automatiquement au premier appel."""
    global _collection, _embedding_info
    if _collection is not None:
        return _collection
    client = get_client()
    with _lock:
        if _collection is None:
            fn, label = _resolve_embedding()
            kwargs = {
                "name": _collection_name(label),
                "metadata": {"hnsw:space": "cosine", "embedding": label},
            }
            if fn is not None:
                kwargs["embedding_function"] = fn
            _collection = client.get_or_create_collection(**kwargs)
            _embedding_info = label
            print(f"[chroma] collection '{_collection.name}' ({label}) dans {config.CHROMA_DIR}")
    return _collection


def get_embedding_info():
    get_collection()
    return _embedding_info


def reset_for_tests():
    global _client, _collection, _embedding_info
    _client = _collection = _embedding_info = None
