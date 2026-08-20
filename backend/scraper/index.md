# Scraper Skapa Chatbot

Module de scraping générique : il peut cibler **n'importe quel site ou
plateforme** (pas seulement Scapa Academy) et alimenter la base utilisée
par le chatbot RAG.

## Objectif

Ce scraper récupère le contenu du site cible (défini via
`SCRAPER_TARGET_URL` ou passé à l'API) afin de :

- Peupler la table `documents` (contenu texte + URL source)
- Servir de base à la recherche par similarité utilisée par le chatbot
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
├── parser.py       # extraction et nettoyage des données
└── scheduler.py    # rafraîchissement périodique
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

Via l'endpoint admin (voir plus bas), ou en Python :

```python
from scraper.spider import fetch_pages
from scraper.parser import parse_page

pages = fetch_pages("https://exemple.com")
for url, html in pages:
    print(parse_page(url, html))
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

1. **`spider.py`** parcourt les pages du site cible (même domaine que l'URL de départ).
2. **`parser.py`** extrait le titre et le texte utile de chaque page, en nettoyant le HTML parasite (scripts, nav, footer...).
3. Les données sont écrites ou mises à jour (`upsert`) dans la table `documents` via SQLAlchemy, en évitant les doublons grâce à un `external_id` (empreinte de l'URL).
4. Le chatbot (`app/api_agent.py`) cherche ensuite, à chaque question, les documents les plus proches par similarité de mots-clés, puis les envoie comme contexte à Claude pour générer la réponse.

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