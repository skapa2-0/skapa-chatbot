# Skapa Chatbot

Chatbot intégrable sur n'importe quel site ou plateforme web. Il scrape le
site cible, découpe le contenu en morceaux ("chunks"), les stocke dans une
base vectorielle **Chroma DB** (locale, embarquée), et répond aux questions
des visiteurs en s'appuyant uniquement sur ces informations (RAG).

## Architecture

```
┌─────────────┐   scrape    ┌──────────────┐   embeddings   ┌───────────┐
│   Site à     │ ─────────▶ │ scraper/     │ ──────────────▶│ Chroma DB │
│   indexer    │            │ spider+parser│                │ (fichiers)│
└─────────────┘            └──────────────┘                 └─────┬─────┘
                                                                    │
┌─────────────┐   question  ┌──────────────┐   recherche          │
│ Widget JS    │ ─────────▶ │ Flask API    │◀─────────────────────┘
│ (sur ton     │◀───────────│ /chat        │──▶ Claude (Anthropic)
│  site)       │  réponse   └──────────────┘
└─────────────┘
```

- **Chroma DB** tourne en mode "embarqué" (`PersistentClient`) : pas de
  serveur à gérer, tout vit dans un dossier (`CHROMA_DIR`). Chaque
  `collection.upsert(...)` écrit directement dedans — c'est ce qui donne le
  comportement "la base se met à jour automatiquement dès qu'il y a une
  nouvelle info".
- Les embeddings sont générés **localement par Chroma** (modèle
  `all-MiniLM-L6-v2`), pas besoin de clé API pour ça.
- Seule la génération de la réponse finale passe par **Claude** (clé
  `ANTHROPIC_API_KEY` obligatoire pour `/chat`).

## Structure du projet

```
skapa-chatbot/
├── backend/
│   ├── app/
│   │   ├── api_agent.py      # API Flask : /, /chat, /api/scrape/run
│   │   └── chroma_client.py  # accès partagé à la base Chroma
│   ├── scraper/
│   │   ├── spider.py         # parcourt le site (requests+BS4, ou Playwright)
│   │   ├── parser.py         # nettoie le HTML + découpe en chunks
│   │   ├── ingest.py         # écrit les chunks dans Chroma
│   │   ├── pipeline.py       # enchaîne spider -> parser -> ingest
│   │   ├── scheduler.py      # relance le pipeline périodiquement
│   │   └── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── skapa-widget.js       # widget de chat à coller sur ton site
│   ├── index.html            # page de démo pour tester le widget
│   └── Dockerfile
├── .env.example
├── docker-compose.yml
├── Procfile / railway.json   # déploiement Railway
└── start.sh                  # lancement local sans Docker
```

## Démarrage rapide (local, sans Docker)

```bash
cp .env.example .env
# remplis ANTHROPIC_API_KEY et ADMIN_TOKEN dans .env

./start.sh
```

L'API tourne sur `http://localhost:8000`.

Dans un autre terminal, ouvre `frontend/index.html` dans un navigateur (ou
`python -m http.server 8080` dans le dossier `frontend/`) pour voir le
widget.

## Démarrage avec Docker

```bash
cp .env.example backend/.env
# remplis backend/.env

docker compose up -d --build
```

- API : `http://localhost:8000`
- Widget : `http://localhost:8080/skapa-widget.js`

## Lancer le scraping

**Manuellement, en local :**
```bash
cd backend
python -m scraper.pipeline
```

**Via l'API (endpoint protégé) :**
```bash
curl -X POST http://localhost:8000/api/scrape/run \
  -H "Authorization: Bearer TON_ADMIN_TOKEN"
```

**Automatiquement, en tâche de fond :**
```bash
cd backend
python -m scraper.scheduler
```
Relance le pipeline toutes les `SCRAPER_INTERVAL_HOURS` heures (24 par
défaut). À ne PAS lancer en même temps que l'API dans le même
`docker compose up` (voir le commentaire dans `docker-compose.yml`) : deux
processus ne peuvent pas écrire dans le même dossier Chroma persistant en
même temps. Préfère un cron qui appelle `/api/scrape/run`.

## Intégrer le widget sur ton site

Colle simplement cette balise avant `</body>` :

```html
<script
  src="https://ton-domaine.com/skapa-widget.js"
  data-api-url="https://ton-api.com/chat"
  data-title="Assistant"
  data-color="#1f6feb"
></script>
```

Aucune dépendance, un seul fichier JS.

## Consulter / modifier ta base Chroma

```python
from app.chroma_client import get_collection

collection = get_collection()
print(collection.count())          # nombre de chunks stockés
collection.get(limit=5)             # voir quelques entrées
collection.delete(where={"url": "https://exemple.com/page"})  # supprimer une page
```

Le dossier `CHROMA_DIR` (par défaut `./chroma_db`) contient toute la base :
tu peux le sauvegarder, le copier, ou le supprimer pour repartir de zéro.

## Variables d'environnement

Voir `.env.example` pour la liste complète et les valeurs par défaut.

## Sécurité

- Ne jamais commiter `.env` (déjà dans `.gitignore`).
- `ANTHROPIC_API_KEY` et `ADMIN_TOKEN` doivent rester secrets.
- `ALLOWED_ORIGINS` : Flask-CORS ne gère qu'**une seule** origine ici — une
  liste séparée par des virgules ne fonctionnera pas telle quelle.

## Limites connues

- Si le site cible change sa structure HTML, les sélecteurs de
  `parser.py`/`spider.py` peuvent avoir besoin d'ajustements.
- Le scraper Playwright (`SCRAPER_USE_PLAYWRIGHT=true`) est plus lent mais
  nécessaire pour les sites qui chargent leur contenu en JavaScript.
- Pas de gestion de l'historique de conversation pour l'instant : chaque
  message envoyé à `/chat` est traité indépendamment.
