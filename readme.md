# Skapa Chatbot

Chatbot embarquable sur n'importe quel site. On lui donne une cible — une
URL, une API, un fichier, une table — **il détecte tout seul de quel type de
plateforme il s'agit**, en extrait le contenu, l'indexe dans une vraie base
vectorielle, puis répond aux questions des visiteurs par RAG
(Retrieval-Augmented Generation). Backend **Flask**, RAG avec
**LangChain + ChromaDB + tiktoken**, génération via **Claude**, widget
**React** livré en un seul fichier `.js` à coller sur n'importe quelle page.

```bash
# Une seule commande, quelle que soit la plateforme :
curl -X POST http://127.0.0.1:5000/api/ingest \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "https://le-site-du-client.com", "site_id": "client-1"}'
```

## Sources reconnues automatiquement

| Cible donnée                        | Détecté comme | Ce qui est fait                                        |
|-------------------------------------|---------------|--------------------------------------------------------|
| `https://site.com`                  | `html`        | sitemap.xml si présent, sinon crawl des liens internes |
| `https://spa-react.com`             | `html` + JS   | rendu dans Chromium (Playwright) avant extraction      |
| `https://blog.com` (WordPress)      | `wordpress`   | API REST `/wp-json/wp/v2/` : pages + articles          |
| `https://boutique.com` (Shopify)    | `shopify`     | `/products.json` : titres, descriptions, prix, variantes |
| `https://api.site.com/v1/items`     | `json`        | 1 enregistrement = 1 document, structure quelconque    |
| `https://site.com/sitemap.xml`      | `sitemap`     | toutes les pages listées (suit les sitemapindex)       |
| `https://site.com/feed.xml`         | `feed`        | RSS ou Atom : 1 entrée = 1 document                    |
| `export.csv` / URL de CSV           | `csv`         | 1 ligne = 1 document, l'en-tête nomme les champs       |
| `cgv.pdf` / URL de PDF              | `pdf`         | 1 page = 1 document (texte extrait via pypdf)          |
| `notes.md`, `.txt`                  | `text`        | lu tel quel                                            |
| `supabase://` ou `supabase://table` | `supabase`    | API REST Supabase, n'importe quel schéma de table      |

La détection est en cascade, du signal le plus fiable au plus faible
(`app/source_detector.py`) : schéma d'URL explicite → fichier local →
en-tête `Content-Type` → sniffing des premiers octets du corps (quand le
serveur annonce un type faux) → sonde des API de plateforme (`/wp-json`,
`/products.json`) → HTML statique ou SPA à rendre en JS. Chaque branche est
un `if` explicite, donc facile à étendre : ajouter une plateforme = une
sonde dans `source_detector.py` + un extracteur dans `extractors.py`.

Quel que soit le type détecté, l'extracteur produit **le même format de
document** (`source_url`, `title`, `content`, `external_id`, `source_type`,
`site_id`). Tout le reste du pipeline — chunking, indexation Chroma,
recherche, génération Claude — est donc rigoureusement identique d'une
plateforme à l'autre.

## Multi-sites

Chaque document porte un `site_id`. Le widget envoie le sien via
`data-site-id`, et la recherche vectorielle est filtrée dessus : une seule
API peut donc servir plusieurs sites clients sans jamais mélanger leurs
contenus. Sans `site_id`, la recherche porte sur tout l'index.

## Structure

```
skapa-chatbot/
├── backend/
│   ├── app/
│   │   ├── __init__.py      # création de l'app Flask (CORS, DB)
│   │   ├── config.py        # variables d'environnement
│   │   ├── models.py        # Document, ChatLog (SQLAlchemy)
│   │   ├── api_agent.py     # pipeline RAG : recherche Chroma + génération Claude
│   │   ├── chunking.py      # découpage en chunks (LangChain + tokenizer tiktoken)
│   │   ├── vectorstore.py   # indexation/recherche vectorielle (ChromaDB), filtrée par site_id
│   │   ├── source_detector.py   # détecte le type de plateforme (la cascade de if/else)
│   │   ├── extractors.py        # un extracteur par type de données -> format unique
│   │   ├── universal_ingest.py  # aiguillage détection -> extraction -> indexation
│   │   ├── ingestion.py     # upsert SQL + (ré)indexation, partagé par toutes les sources
│   │   ├── supabase_source.py  # lecture directe des tables Supabase
│   │   └── routes.py        # /api/chat, /api/ingest, /api/detect, /api/health...
│   ├── scraper/
│   │   ├── spider.py        # crawl du site cible (+ rendu JS via Playwright)
│   │   ├── parser.py        # extraction/nettoyage du HTML + données structurées JSON-LD
│   │   └── scheduler.py     # rafraîchissement périodique
│   ├── run.py                # point d'entrée Flask
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.jsx          # auto-montage du widget
│   │   ├── ChatWidget.jsx    # bulle + fenêtre de chat
│   │   └── widget.css
│   ├── embed-example.html    # exemple d'intégration sur un site tiers
│   └── package.json
├── start.sh
└── requirements.txt
```

## Comment ça marche (pipeline RAG)

1. **Détection + collecte** : `app/source_detector.py` identifie le type de
   la cible, `app/extractors.py` en extrait le contenu. Onze types de
   sources, un seul format de sortie. Les documents sont stockés dans la
   table SQL `documents` (upsert sur une empreinte `site_id` + URL/ligne,
   donc pas de doublons, même si une page est atteinte par deux chemins).
   Pour le HTML, on récupère aussi les **données structurées JSON-LD** que
   publient la plupart des plateformes pour le SEO : elles contiennent
   souvent l'info la plus propre de la page (prix, dates, horaires).
2. **Chunking** (`app/chunking.py`) : chaque document est découpé en
   chunks d'environ 300 tokens (recouvrement de 40) avec le
   `RecursiveCharacterTextSplitter` de **LangChain**, mesuré avec le vrai
   tokenizer **tiktoken** (`cl100k_base`) plutôt qu'un simple compte de
   caractères.
3. **Indexation vectorielle** (`app/vectorstore.py`) : les chunks sont
   embeddés et stockés dans **ChromaDB** (persisté sur disque dans
   `backend/chroma_db/`). Chaque chunk garde en métadonnées son
   `document_id`, son `source_url` et son `title`, ce qui permet de
   supprimer/réindexer proprement un document sans dupliquer.
4. **Recherche + génération** (`app/api_agent.py`) : à chaque question,
   Chroma renvoie les chunks les plus proches sémantiquement (pas juste
   des mots en commun), restreints au `site_id` du widget appelant, qui
   servent de contexte à **Claude** pour rédiger la réponse finale.
5. **Widget** : composant React buildé en un seul fichier
   `skapa-widget.js`. Un site tiers l'intègre avec une simple balise
   `<script>`, sans rien installer.

> **Embeddings** : ChromaDB utilise son modèle par défaut intégré
> (`all-MiniLM-L6-v2`, format ONNX), téléchargé automatiquement (une
> seule fois, mis en cache) au premier lancement — aucune clé API
> supplémentaire nécessaire. Il faut juste un accès internet la première
> fois.

## Démarrage rapide

```bash
./start.sh
```

Ou manuellement :

### Backend

```bash
cd backend
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # une fois, pour les sites en JavaScript (SPA)
cp .env.example .env          # puis renseigner ANTHROPIC_API_KEY...
python run.py                 # http://127.0.0.1:5000
```

> **Python 3.12 recommandé.** Sur 3.14, plusieurs dépendances épinglées
> (`pydantic-core`, `psycopg2-binary`, `greenlet`) n'ont pas de wheel et
> échouent à la compilation.
>
> **Sur macOS, utiliser `127.0.0.1:5000` et non `localhost:5000`** : le
> Récepteur AirPlay écoute aussi sur le port 5000 et répond `403` sur l'IPv6
> `::1`. Sinon, désactiver *Réglages Système → Général → AirDrop et Handoff →
> Récepteur AirPlay*.

### Ingérer une source (n'importe laquelle)

```bash
# Le type est détecté automatiquement : site, SPA, API, WordPress, Shopify,
# sitemap, RSS, CSV, PDF, fichier local, Supabase...
curl -X POST http://127.0.0.1:5000/api/ingest \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "https://exemple.com", "site_id": "client-1", "max_pages": 50}'

# Savoir ce qui serait détecté, sans rien indexer :
curl -X POST http://127.0.0.1:5000/api/detect \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "https://exemple.com"}'

# Sans "source", on retombe sur SCRAPER_TARGET_URL puis SUPABASE_* du .env :
curl -X POST http://127.0.0.1:5000/api/ingest -H "Authorization: Bearer $ADMIN_TOKEN"

# En planifié (toutes les SCRAPER_INTERVAL_HOURS heures) :
cd backend && python -m scraper.scheduler
```

Réponse type :

```json
{
  "ok": true,
  "source_type": "wordpress",
  "detected_by": "API wordpress détectée sur le domaine",
  "target": "https://exemple.com",
  "site_id": "client-1",
  "documents": 42, "created": 42, "updated": 0
}
```

> **Sites en JavaScript** : si la cible est une SPA (React/Vue/Angular), le
> HTML servi est vide et le contenu n'existe qu'après exécution du JS. C'est
> détecté automatiquement et la page est alors rendue dans Chromium. Cela
> suppose `playwright install chromium` (une fois). Forçable avec
> `SCRAPER_RENDER_JS=always|never`.

### Frontend (widget)

```bash
cd frontend
npm install
npm run dev      # démo locale sur http://localhost:5173
npm run build    # génère dist/skapa-widget.js à déployer
```

## Intégrer le widget sur un site

Une fois `dist/skapa-widget.js` déployé (CDN, serveur statique...), il
suffit d'ajouter cette balise sur n'importe quelle page :

```html
<script
  src="https://votre-domaine.com/skapa-widget.js"
  data-api-url="https://votre-api.com/api"
  data-site-id="site-client-1"
  data-title="Besoin d'aide ?"
  data-color="#4f46e5"
></script>
```

Voir `frontend/embed-example.html` pour un exemple complet.

## API

| Méthode | Route                | Description                                                              |
|---------|----------------------|--------------------------------------------------------------------------|
| GET     | `/api/health`        | État de l'API + inventaire indexé par type de source et par site         |
| POST    | `/api/chat`          | `{ "question": "...", "site_id": "..." }` — la recherche est scopée au site |
| POST    | `/api/ingest`        | **Admin** : ingère n'importe quelle source, type détecté automatiquement  |
| POST    | `/api/detect`        | **Admin** : dit quel type serait détecté, sans rien indexer              |
| POST    | `/api/scrape/run`    | **Admin** : crawl HTML explicite, sans détection (legacy, préférer `/api/ingest`) |
| POST    | `/api/sync/supabase` | **Admin** : synchronise `SUPABASE_TABLES` (ou `{"table": "..."}`)        |

Les routes **Admin** exigent l'en-tête `Authorization: Bearer <ADMIN_TOKEN>`.

## Utiliser Supabase comme source de données (au lieu du scraping HTML)

Si tes données sont déjà dans Supabase (ex: `trainings`, `training_sessions`,
`site_pages`), pas besoin de scraper : `backend/app/supabase_source.py` lit
directement ces tables via l'API REST de Supabase (PostgREST) et les
transforme en documents indexables, exactement comme le ferait le scraper.

1. Dans `backend/.env`, renseigne :
   ```
   SUPABASE_URL=https://xxxx.supabase.co/
   SUPABASE_ANON_KEY=eyJ...
   SUPABASE_TABLES=trainings,training_sessions,site_pages
   ```
2. Lance la synchro :
   ```bash
   curl -X POST http://localhost:5000/api/sync/supabase \
     -H "Authorization: Bearer change-me"
   ```
3. Chaque ligne de chaque table devient un document (`titre` = colonne
   `title`/`name` si présente, sinon `<table> #<id>` ; le reste des colonnes
   est concaténé comme contenu). Le chatbot peut ensuite y répondre comme
   pour du contenu scrapé.

> La clé `SUPABASE_ANON_KEY` respecte les règles RLS (Row Level Security)
> de ton projet Supabase : seules les lignes/tables que l'anon key a le
> droit de lire seront synchronisées. Ne mets jamais la `service_role`
> key ici (elle contourne RLS) — l'anon key est faite pour être utilisée
> côté serveur/client de cette façon.

## Variables d'environnement (`backend/.env`)

Voir `backend/.env.example` — en particulier `ANTHROPIC_API_KEY`,
`SCRAPER_TARGET_URL`, `ADMIN_TOKEN`, `ALLOWED_ORIGINS`.

Les variables spécifiques à l'ingestion universelle :

| Variable                  | Défaut  | Rôle                                                        |
|---------------------------|---------|-------------------------------------------------------------|
| `SCRAPER_RENDER_JS`       | `auto`  | `auto` décide page par page, `always` force Chromium, `never` le désactive |
| `SCRAPER_PREFER_SITEMAP`  | `true`  | Utiliser `/sitemap.xml` quand il existe plutôt que crawler les liens |
| `SCRAPER_MAX_PAGES`       | `30`    | Plafond de pages/enregistrements par ingestion              |
| `MAX_DOC_CHARS`           | `50000` | Troncature d'un document avant chunking                     |
| `MIN_DOC_CHARS`           | `40`    | En dessous, le document est jugé vide et ignoré              |
| `INGEST_TIMEOUT`          | `15`    | Délai réseau (s) des requêtes d'ingestion                    |
| `DEFAULT_SITE_ID`         | `default` | `site_id` utilisé quand le widget n'en envoie pas          |

## Ce qui a été corrigé/ajouté par rapport à la version initiale

- `backend/app/api-agent.py` → renommé `api_agent.py` (un nom de module
  Python ne peut pas contenir de tiret, l'import échouait).
- `scraper/parser.py` était un simple test (`requests.get(...)`) : il
  contient maintenant la vraie logique d'extraction/nettoyage HTML.
- `spider.py` et `scheduler.py` étaient vides : implémentés.
- Ajout du dossier `frontend/src` (widget React manquant), de
  `run.py`, `.env.example`, `.gitignore`, `start.sh` et de ce README
  (tous vides ou absents dans le projet d'origine).
- Ajout d'une source de données **Supabase** (`app/supabase_source.py`,
  route `/api/sync/supabase`).
- Recherche par mots-clés remplacée par un **vrai pipeline RAG** :
  chunking LangChain + tokenizer tiktoken, indexation/recherche
  vectorielle ChromaDB (`app/chunking.py`, `app/vectorstore.py`,
  `app/ingestion.py`).
- **Ingestion universelle** : le scraper ne gérait que du HTML statique via
  `requests`. Ajout de `app/source_detector.py` (détection du type de
  plateforme), `app/extractors.py` (11 types de sources) et
  `app/universal_ingest.py` (aiguillage), plus les routes `/api/ingest` et
  `/api/detect`.
- **Rendu JavaScript** : `spider.py` sait maintenant passer par Chromium
  (Playwright) quand la page est une SPA — automatiquement détecté.
- **Multi-sites** : `Document` porte un `site_id` et un `source_type`, et la
  recherche vectorielle est filtrée par site (le widget envoyait déjà son
  `data-site-id`, mais il était ignoré côté recherche).
- Le crawl ignore désormais les liens vers des binaires (images, CSS, JS,
  archives) et les documents ne sont plus tronqués à 5 000 caractères
  (`MAX_DOC_CHARS`, 50 000 par défaut).

## Limitations connues

- Le scraper respecte uniquement le même domaine et un délai entre
  requêtes ; **le `robots.txt` n'est pas lu** : vérifiez-le, ainsi que les
  CGU du site cible, avant de scraper.
- La détection de plateforme sonde `/wp-json/wp/v2/types` et
  `/products.json` sur le domaine : deux requêtes supplémentaires par
  ingestion HTML. Un site qui répond `200` à tout (pas de vraie 404) peut
  être mal typé — vérifiez avec `/api/detect` en cas de doute.
- Le rendu JavaScript lance un Chromium par page : compter ~1 à 3 s par
  page, contre quelques dizaines de ms en `requests`. À réserver aux sites
  qui en ont besoin (`SCRAPER_RENDER_JS=never` pour le désactiver).
- Les PDF scannés (image sans couche texte) ressortent vides : il faudrait
  un OCR, non inclus.
- Le premier lancement nécessite un accès internet pour télécharger le
  modèle d'embedding ChromaDB (~90 Mo, mis en cache ensuite) et le
  fichier de vocabulaire tiktoken.
- `backend/chroma_db/` (index vectoriel) doit être régénéré si vous
  changez de machine sans le copier : relancez simplement une ingestion.
- Ajouter une colonne au modèle `Document` ne migre pas une base SQLite
  existante (`db.create_all()` ne fait que créer les tables manquantes) :
  Alembic est installé mais pas encore configuré.
