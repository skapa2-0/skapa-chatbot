"""
Accès partagé à la base Chroma (mode embarqué / PersistentClient).

Points importants :
- La collection est liée au modèle d'embedding utilisé (son nom contient
  le modèle). Mélanger deux modèles d'embedding dans la même collection
  rendrait la recherche incohérente : si tu changes de modèle, il suffit
  de relancer « Analyser » sur le site.
- Embeddings multilingues via Ollama (bge-m3 par défaut) quand c'est
  disponible : le modèle par défaut de Chroma (all-MiniLM-L6-v2) est
  entraîné surtout en anglais et retrouve mal le contenu des sites français.
"""

import re
import threading

import chromadb
from chromadb.config import Settings
import requests

from app import config

_lock = threading.Lock()
_client = None
_collection = None
_embedding_info = None


class OllamaEmbeddingFunction:
    """Embeddings via l'API HTTP d'Ollama (/api/embed, batch)."""

    def __init__(self, base_url, model, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def __call__(self, input):  # signature attendue par Chroma
        texts = list(input)
        embeddings = []
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            try:
                resp = requests.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": batch},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                embeddings.extend(resp.json()["embeddings"])
            except requests.exceptions.ConnectionError:
                raise RuntimeError(
                    f"Impossible de joindre Ollama sur {self.base_url} pour les embeddings. "
                    "Vérifiez qu'Ollama est démarré (`ollama serve`)."
                )
            except requests.exceptions.HTTPError as exc:
                if resp.status_code == 404:
                    raise RuntimeError(
                        f"Modèle d'embedding Ollama '{self.model}' introuvable. "
                        f"Lancez : ollama pull {self.model}"
                    )
                raise RuntimeError(f"Erreur Ollama embedding HTTP {resp.status_code}: {exc}")
        return embeddings


def _ollama_has_model(model):
    try:
        resp = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        return any(n == model or n.split(":")[0] == model for n in names)
    except (requests.RequestException, ValueError):
        return False


def _resolve_embedding():
    provider = config.EMBEDDING_PROVIDER
    if provider == "ollama" or (provider == "auto" and _ollama_has_model(config.OLLAMA_EMBED_MODEL)):
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
    name = f"{config.COLLECTION_BASE}-{slug}"
    return name[:63]


def get_client():
    global _client
    with _lock:
        if _client is None:
            import os
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
                # distance cosinus : adaptée aux embeddings de phrases
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
