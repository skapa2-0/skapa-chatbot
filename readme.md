# Skapa Chatbot

Chatbot intégrable sur n'importe quel site. On saisit l'adresse d'un site, le
backend le **scrape**, découpe le contenu en **chunks**, les stocke dans
**ChromaDB**, et la bulle de chat répond aux questions **uniquement à partir
du contenu de ce site** (RAG).

## Architecture

```
 Page de démo / widget                      Backend Flask (backend/)
┌──────────────────────┐  POST /api/scrape/run  ┌──────────────────────────────────────┐
│ « Analyser et adapter » ───────────────────▶ │ tâche de fond :                      │
│   (suit la progression)◀── /api/scrape/status │  spider  -> requests / Playwright    │
│                      │                        │  parser  -> trafilatura + chunks     │
│ Bulle de chat        │  POST /chat            │  ingest  -> ChromaDB (par domaine)   │
│   site_url + history ───────────────────────▶ │ recherche Chroma (filtre domaine)    │
│                      │◀── réponse + sources ──│  -> LLM : Ollama (ou Claude)         │
└──────────────────────┘                        └──────────────────────────────────────┘
```

- **Scraping** : `requests` pour les sites statiques ; **Playwright** (Chromium)
  automatiquement pour les sites React/Vue/Next rendus en JavaScript. Suit les
  redirections (`site.fr` → `www.site.fr`), lit `sitemap.xml`, respecte
  `robots.txt`, ignore PDF/images et paramètres de tracking.
- **Extraction** : **trafilatura** (meilleur extracteur open source de contenu
  principal) + nettoyage BeautifulSoup (menus, bandeaux cookies, tableaux mis à
  plat « cellule | cellule »). Les coordonnées du pied de page (téléphone,
  email, adresse) sont indexées à part, une seule fois par site.
- **Chunking** : découpe récursive (paragraphes → lignes → phrases → mots),
  1000 caractères avec 150 de chevauchement, titre de la page en tête de chaque
  chunk.
- **ChromaDB** embarqué (`PersistentClient`, dossier `backend/chroma_db`).
  Re-scraper un site **remplace** ses anciens chunks (pas de contenu périmé).
- **Embeddings** : modèle multilingue **bge-m3** via Ollama s'il est installé
  (bien meilleur en français), sinon modèle par défaut de Chroma.
- **LLM** : Ollama en local (`llama3.2` par défaut) ou Claude via l'API
  Anthropic (`LLM_PROVIDER=anthropic`, utile en production).

## Démarrage rapide (local)

Prérequis : Python 3.12 (ou 3.13) et [Ollama](https://ollama.com).

```bash
# 1. Modèles Ollama
ollama pull llama3.2      # génération des réponses
ollama pull bge-m3        # embeddings multilingues (recommandé)
ollama serve              # si Ollama ne tourne pas déjà

# 2. Configuration
cp .env.example backend/.env
# -> choisir un ADMIN_TOKEN

# 3. API (http://localhost:8000)
./start.sh

# 4. Page de démo (autre terminal) -> http://localhost:8080
cd frontend && python3 -m http.server 8080
```

Sur la page : saisir l'adresse du site → **Analyser et adapter** (le token
admin est demandé une fois) → la bulle s'ouvre et répond sur ce site.
Le site analysé est mémorisé dans le navigateur.

> En local uniquement, `SCRAPE_PUBLIC=true` dans `backend/.env` supprime la
> demande de token.

## Avec Docker

```bash
cp .env.example backend/.env    # puis le remplir
docker compose up -d --build
```

API : `http://localhost:8000` — démo : `http://localhost:8080`. Le conteneur
joint l'Ollama de la machine hôte via `host.docker.internal`.

## Lancer un scraping sans l'interface

```bash
# en ligne de commande
cd backend && python -m scraper.pipeline https://mon-site.fr

# via l'API (asynchrone : renvoie un job_id)
curl -X POST http://localhost:8000/api/scrape/run \
  -H "Authorization: Bearer TON_ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://mon-site.fr"}'
curl http://localhost:8000/api/scrape/status/<job_id>

# via l'API en attendant la fin (cron, scripts)
curl -X POST http://localhost:8000/api/scrape/run \
  -H "Authorization: Bearer TON_ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "https://mon-site.fr", "wait": true}'
```

Rafraîchissement automatique : un cron qui appelle l'endpoint ci-dessus
(recommandé), ou `python -m scraper.scheduler` (jamais en même temps que l'API
sur le même dossier Chroma).

Documentation interactive : `http://localhost:8000/docs`.

## Intégrer le widget sur un site

```html
<script
  src="https://ton-domaine.com/skapa-widget.js"
  data-api-url="https://ton-api.com"
  data-site-url="https://mon-site.fr"
  data-title="Assistant"
  data-color="#5b3fd4"
></script>
```

`data-site-url` limite les réponses au contenu de ce site (il doit avoir été
analysé). Un seul fichier JS, sans dépendance.

## Déploiement (Railway)

- La commande de démarrage utilise `backend/gunicorn.conf.py` : **1 worker +
  8 threads**, timeout 300 s. Garder 1 worker (Chroma en mode fichier = un seul
  processus écrivain ; suivi des scrapings en mémoire).
- Railway ne fait pas tourner Ollama : utiliser `LLM_PROVIDER=anthropic` avec
  `ANTHROPIC_API_KEY`, ou pointer `OLLAMA_BASE_URL` vers un serveur Ollama.
- Monter un volume persistant et y placer `CHROMA_DIR` / `METADATA_DB`.

## Tests

```bash
cd backend && python -m pytest -q
```

Les tests tournent hors ligne (embeddings et LLM simulés, Chroma réel).

## Variables d'environnement

Voir `.env.example` (toutes les options sont commentées).

## Sécurité

- Ne jamais commiter `.env` (dans `.gitignore`).
- `/api/scrape/run` est protégé par `ADMIN_TOKEN` et refuse les adresses
  internes (protection SSRF).
- `ALLOWED_ORIGINS` accepte plusieurs domaines séparés par des virgules.
- Les réponses du bot sont affichées sans `innerHTML` (pas de XSS).

## Limites connues

- Changer de modèle d'embedding crée une nouvelle collection : relancer
  l'analyse des sites.
- Les pages derrière une connexion (espace membre) ne sont pas accessibles.
- Les sites protégés par un anti-bot agressif (Cloudflare « challenge »)
  peuvent bloquer le scraping.
