"""
Ingestion : écrit les chunks produits par parser.py dans Chroma DB.

replace_domain_chunks() remplace le contenu d'un site de façon atomique :
  1. Upsert des nouveaux chunks
  2. Supprime UNIQUEMENT les anciens IDs qui ne sont plus présents
→ Si le scraping échoue à mi-chemin, les données précédentes restent intactes.
"""

from app.chroma_client import get_collection

BATCH_SIZE = 256


def ingest_chunks(chunks):
    """Ajoute / met à jour des chunks {"id", "text", "metadata"}."""
    if not chunks:
        return 0
    collection = get_collection()
    unique = list({c["id"]: c for c in chunks}.values())
    for i in range(0, len(unique), BATCH_SIZE):
        batch = unique[i:i + BATCH_SIZE]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
    return len(unique)


def delete_domain(source_domain):
    collection = get_collection()
    existing = collection.get(where={"source_domain": source_domain}, include=[])
    ids = existing.get("ids", [])
    for i in range(0, len(ids), 5000):
        collection.delete(ids=ids[i:i + 5000])
    return len(ids)


def replace_domain_chunks(source_domain, chunks):
    """
    Met à jour les chunks d'un domaine sans jamais vider la base d'abord.

    Ordre des opérations (safe) :
      1. Upsert des nouveaux chunks  → données toujours disponibles
      2. Supprime les IDs obsolètes  → nettoyage sans risque de perte
    """
    if not chunks:
        # Rien à indexer : on ne touche pas à la base existante
        print(f"[ingest] {source_domain}: aucun chunk fourni, base inchangée")
        return 0

    collection = get_collection()

    # 1. Récupère les IDs actuellement en base pour ce domaine
    existing = collection.get(where={"source_domain": source_domain}, include=[])
    old_ids = set(existing.get("ids", []))

    # 2. Upsert des nouveaux chunks (données toujours dispo après cette étape)
    new_chunks = list({c["id"]: c for c in chunks}.values())
    new_ids = {c["id"] for c in new_chunks}

    for i in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[i:i + BATCH_SIZE]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )

    # 3. Supprime uniquement les IDs qui ne sont plus dans le nouveau set
    stale_ids = list(old_ids - new_ids)
    for i in range(0, len(stale_ids), 5000):
        collection.delete(ids=stale_ids[i:i + 5000])

    print(
        f"[ingest] {source_domain}: "
        f"{len(new_chunks)} chunks upsertés, "
        f"{len(stale_ids)} anciens supprimés"
    )
    return len(new_chunks)


def count_domain(source_domain):
    res = get_collection().get(where={"source_domain": source_domain}, include=[])
    return len(res.get("ids", []))
