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
_degraded_reason = None


def _set_degraded(reason):
    global _degraded_reason
    _degraded_reason = reason


def get_health_status():
    """Retourne ('ok'|'degraded', reason_or_None)."""
    return ("degraded", _degraded_reason) if _degraded_reason else ("ok", None)


def _collection_name(embedding_label):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", embedding_label).strip("-").lower()
    return f"{config.COLLECTION_BASE}-{slug}"[:63]


def _resolve_embedding():
    provider = config.EMBEDDING_PROVIDER
    has_model = ollama_has_model(config.OLLAMA_EMBED_MODEL)
    ollama_label = f"ollama:{config.OLLAMA_EMBED_MODEL}"

    if provider == "ollama":
        if not has_model:
            msg = (
                f"⚠️  EMBEDDING_PROVIDER=ollama mais Ollama / modèle "
                f"'{config.OLLAMA_EMBED_MODEL}' est INDISPONIBLE. "
                f"Le chatbot ne peut pas répondre. Vérifiez qu'Ollama est démarré."
            )
            print(msg, flush=True)
            _set_degraded(f"Ollama indisponible (modèle : {config.OLLAMA_EMBED_MODEL})")
        fn = OllamaEmbeddingFunction(config.OLLAMA_BASE_URL, config.OLLAMA_EMBED_MODEL)
        return fn, ollama_label

    if provider == "auto":
        if has_model:
            fn = OllamaEmbeddingFunction(config.OLLAMA_BASE_URL, config.OLLAMA_EMBED_MODEL)
            return fn, ollama_label
        # Ollama absent : vérifie si un index existant serait abandonné silencieusement
        ollama_coll = _collection_name(ollama_label)
        try:
            # _client est déjà initialisé par get_collection() avant d'appeler _resolve_embedding
            existing = [c.name for c in _client.list_collections()]
        except Exception:
            existing = []
        if ollama_coll in existing:
            print(
                f"⚠️  INDEX VIDE : la collection Ollama '{ollama_coll}' existe (index précédent) "
                f"mais Ollama est INDISPONIBLE → basculement sur index vide. "
                f"Le bot répondra 'pas de contenu'. Redémarrez Ollama : ollama serve",
                flush=True,
            )
            _set_degraded(
                f"Ollama indisponible, index existant '{ollama_coll}' inaccessible"
            )
        else:
            print(
                f"[chroma] modèle Ollama '{config.OLLAMA_EMBED_MODEL}' introuvable "
                f"→ modèle Chroma par défaut. Pour le français : "
                f"ollama pull {config.OLLAMA_EMBED_MODEL}"
            )

    return None, "default:all-MiniLM-L6-v2"


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
    global _client, _collection, _embedding_info, _degraded_reason
    _client = _collection = _embedding_info = _degraded_reason = None
