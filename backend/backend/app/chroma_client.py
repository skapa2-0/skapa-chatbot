"""
Petit module qui ouvre (ou crée) la base Chroma une seule fois et la
partage avec le reste de l'app (api_agent.py et scraper/ingest.py).

Chroma DB est "embarqué" : pas de serveur à lancer, tout vit dans un
dossier sur le disque (CHROMA_DIR). A chaque nouvelle info ajoutée
(collection.add / .upsert), Chroma écrit directement dans ce dossier
-> c'est le comportement "s'ouvre / se met à jour automatiquement"
que tu voulais.
"""

import os
import chromadb

CHROMA_DIR = os.environ.get("CHROMA_DIR", "./chroma_db")
COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "web_knowledge")

_client = None
_collection = None


def get_client():
    """Retourne le client Chroma persistant (créé une seule fois)."""
    global _client
    if _client is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
    return _client


def get_collection():
    """Retourne la collection utilisée pour stocker les chunks scrapés."""
    global _collection
    if _collection is None:
        client = get_client()
        # get_or_create_collection : si elle n'existe pas encore, elle est
        # créée automatiquement. Chroma génère lui-même les embeddings
        # (modèle local all-MiniLM-L6-v2, pas besoin de clé API pour ça).
        _collection = client.get_or_create_collection(name=COLLECTION_NAME)
    return _collection
