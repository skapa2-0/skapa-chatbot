"""
Configuration pytest commune.

Les tests tournent HORS LIGNE : base Chroma temporaire et embeddings
« lexicaux » déterministes (pas de téléchargement de modèle, pas d'Ollama).
"""

import hashlib
import math
import os
import re
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


class FakeEmbedding:
    """Sac de mots haché -> suffisant pour tester la recherche par mots-clés."""

    DIM = 256

    def __call__(self, input):
        out = []
        for text in input:
            t = unicodedata.normalize("NFKD", text.lower())
            t = "".join(c for c in t if not unicodedata.combining(c))
            v = [0.0] * self.DIM
            for w in re.findall(r"[a-z0-9]{3,}", t):
                v[int(hashlib.md5(w[:6].encode()).hexdigest(), 16) % self.DIM] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    """Chroma + SQLite isolés dans un dossier temporaire."""
    from app import chroma_client, config

    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(config, "METADATA_DB", str(tmp_path / "meta.db"))
    monkeypatch.setattr(chroma_client, "_resolve_embedding",
                        lambda: (FakeEmbedding(), "test:fake"))
    chroma_client.reset_for_tests()
    yield tmp_path
    chroma_client.reset_for_tests()
