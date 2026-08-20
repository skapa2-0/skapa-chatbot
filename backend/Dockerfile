# syntax=docker/dockerfile:1

# =====================================================================
#  Étape 1 : dépendances Python dans un venv isolé.
#  build-essential ne sert qu'à compiler les rares paquets sans wheel ;
#  il reste dans cette étape et n'alourdit pas l'image finale.
# =====================================================================
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


# =====================================================================
#  Étape 2 : image d'exécution
# =====================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/home/skapa \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TIKTOKEN_CACHE_DIR=/opt/cache/tiktoken \
    ANONYMIZED_TELEMETRY=False

COPY --from=builder /opt/venv /opt/venv

# Chromium + ses librairies système : rendu des sites en SPA (React/Vue/
# Angular), cf. SCRAPER_RENDER_JS. C'est le gros de l'image (~450 Mo) :
# supprimable si l'ingestion ne cible que du HTML statique / des APIs.
RUN apt-get update \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /home/skapa --uid 10001 skapa

# Les deux modèles normalement téléchargés au premier appel sont préchargés
# ici, à la construction : le conteneur démarre donc sans accès réseau et
# la première question ne paie pas 80 Mo de download.
#   - tiktoken cl100k_base      -> chunking (app/chunking.py, à l'import)
#   - all-MiniLM-L6-v2 (ONNX)   -> embeddings Chroma (app/vectorstore.py)
RUN mkdir -p "$TIKTOKEN_CACHE_DIR" \
 && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
 && python -c "import chromadb; c = chromadb.EphemeralClient().get_or_create_collection('warmup'); c.add(ids=['1'], documents=['warmup'])" \
 && chown -R skapa:skapa /home/skapa "$TIKTOKEN_CACHE_DIR"

WORKDIR /app
COPY --chown=skapa:skapa . .

# /data porte l'index Chroma et la base SQLite : c'est le SEUL dossier à
# persister (volume). Tout le reste de l'image est jetable.
RUN mkdir -p /data && chown -R skapa:skapa /data

USER skapa
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# UN SEUL worker, volontairement : ChromaDB en mode persistant sur disque
# ne supporte pas plusieurs processus sur le même dossier (risque de
# corruption). La concurrence est absorbée par les threads, ce qui suffit
# largement ici puisque le temps de réponse est dominé par l'appel à Claude.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", \
     "--workers", "1", "--worker-class", "gthread", "--threads", "8", \
     "--timeout", "180", "--access-logfile", "-", "run:app"]
