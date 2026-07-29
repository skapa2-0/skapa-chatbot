# Scapa Academy Scraper

Module de scraping utilisé pour extraire les données du site **Scapa Academy** (formations, catégories, descriptions) et alimenter la base PostgreSQL utilisée par le chatbot RAG.

## Objectif

Ce scraper récupère les données réelles et à jour du catalogue Scapa Academy afin de :

- Peupler la table `formations` en base PostgreSQL
- Générer les embeddings utilisés par le chatbot pour répondre aux questions des utilisateurs
- Garder les données synchronisées via un rafraîchissement périodique

## Stack

- **Python 3.11+**
- **BeautifulSoup4** — parsing HTML statique
- **Playwright** — pages avec contenu chargé en JS (si applicable)
- **SQLAlchemy** — écriture en base PostgreSQL
- **APScheduler / Celery** *(à confirmer selon la volumétrie)* — planification du rafraîchissement

## Structure

```
scraper/
├── __init__.py
├── spider.py       # navigation et récupération des pages HTML
├── parser.py        # extraction et nettoyage des données
├── scheduler.py      # rafraîchissement périodique
└── tests/
    └── test_scraper.py
```

## Prérequis

```bash
pip install -r requirements.txt
playwright install     # uniquement si Playwright est utilisé
```

Variables d'environnement nécessaires (voir `.env.example`) :

```
SCRAPER_TARGET_URL=https://scapa-academy.example.com
DATABASE_URL=postgresql://user:password@localhost:5432/scapa_chatbot
SCRAPER_INTERVAL_HOURS=24
SCRAPER_USER_AGENT=ScapaChatbotBot/1.0
```

## Utilisation

### Lancer un scraping manuel

```bash
python -m scraper.spider --once
```

### Lancer le scraping planifié

```bash
python -m scraper.scheduler
```

### Déclencher via l'API (endpoint admin protégé)

```
POST /api/scrape/run
Authorization: Bearer <admin_token>
```

## Fonctionnement

1. **`spider.py`** parcourt les pages du catalogue Scapa Academy (liste de formations + pages de détail).
2. **`parser.py`** extrait les champs utiles (titre, description, catégorie, durée, niveau, prix, URL source) et nettoie le HTML/texte parasite.
3. Les données sont écrites ou mises à jour (`upsert`) dans la table `formations` via SQLAlchemy, en évitant les doublons grâce à un `external_id` stable.
4. Un job séparé (`embedding_service`) génère ensuite les embeddings sur les nouvelles/mises à jour de formations, stockés dans `formation_embeddings` (pgvector).

## Bonnes pratiques suivies

- **Respect du rythme de crawl** : délai entre les requêtes pour ne pas surcharger le serveur Scapa Academy.
- **Idempotence** : chaque exécution peut être relancée sans dupliquer les données (upsert sur `external_id`).
- **Logs structurés** : chaque run de scraping logue le nombre de pages visitées, d'éléments extraits, et les erreurs rencontrées.
- **Dépendances pinnées** : versions figées dans `requirements.txt`, vérifiées avec `pip-audit` avant toute mise à jour (cf. politique sécurité du projet).
- **Isolation** : le scraper tourne dans le même environnement serveur dédié que le reste du backend, pas en local.

## Limitations connues

- Si Scapa Academy change la structure de ses pages, les sélecteurs dans `parser.py` doivent être mis à jour.
- Le scraping ne remplace pas une API interne si Scapa Academy en expose une — à vérifier avant d'étendre ce module.

## Tests

```bash
pytest scraper/tests/
```

## Roadmap

- [ ] Ajouter la gestion des erreurs réseau avec retry/backoff
- [ ] Ajouter un mode `--dry-run` pour prévisualiser les données sans écrire en base
- [ ] Historiser les changements de prix/contenu (table `formations_history`)