"""Embeddings via l'API HTTP d'Ollama + détection de modèle disponible."""

import requests

from app import config


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


def ollama_has_model(model):
    try:
        resp = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        return any(n == model or n.split(":")[0] == model for n in names)
    except (requests.RequestException, ValueError):
        return False
