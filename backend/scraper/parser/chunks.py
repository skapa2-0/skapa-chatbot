"""Découpe récursive en chunks (paragraphes > lignes > phrases > mots)."""

import hashlib

from app import config

CHUNK_SIZE = config.env_int("SCRAPER_CHUNK_SIZE", 1000)
CHUNK_OVERLAP = config.env_int("SCRAPER_CHUNK_OVERLAP", 150)


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Les morceaux se chevauchent de `overlap` caractères pour ne pas perdre
    le contexte aux frontières."""
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be strictly less than chunk_size ({chunk_size})"
        )
    separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

    def split(t, seps):
        if len(t) <= chunk_size:
            return [t]
        sep = next((s for s in seps if s == "" or s in t), "")
        if sep == "":
            step = chunk_size - overlap
            return [t[i:i + chunk_size] for i in range(0, len(t), step)]
        parts = t.split(sep)
        pieces = [p + sep for p in parts[:-1]] + [parts[-1]]
        out = []
        rest = seps[seps.index(sep) + 1:]
        for p in pieces:
            out.extend(split(p, rest) if len(p) > chunk_size else [p])
        return out

    pieces = [p for p in split(text, separators) if p.strip()]

    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) > chunk_size:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            if " " in tail:
                tail = tail[tail.index(" ") + 1:]
            current = tail if len(tail) + len(piece) <= chunk_size else ""
        current += piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_id(url, i):
    return hashlib.sha1(f"{url}#{i}".encode()).hexdigest()[:24] + f"-{i}"
