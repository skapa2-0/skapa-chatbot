# Déploiement — Skapa Chatbot

Guide opérationnel pour l'instance en production sur le serveur OVH.

## URL publique

- **Page de démo + API** : https://chat.skapa.design
- IP du serveur : `51.255.215.75`

Les deux services sont servis sous la même origine HTTPS via le reverse proxy Caddy :
- `GET /` → frontend (page de démo + widget)
- `POST /chat` → backend API
- `GET /api/*` → backend API

## Architecture déployée

```
             Internet
                │
                ▼
    [chat.skapa.design :443]  (DNS A -> 51.255.215.75)
                │
                ▼
    ┌───────────────────────┐
    │  Caddy (Docker)       │  TLS auto (Let's Encrypt), HTTP/2, gzip/zstd
    │  reseau Docker: web   │  reverse_proxy -> 172.18.0.1 (host)
    └──────────┬────────────┘
               │
    ┌──────────┴────────────────────────────┐
    │                                       │
    ▼ /chat* et /api/*                      ▼ autres chemins
┌─────────────────────┐             ┌───────────────────────┐
│ Flask + gunicorn    │             │ python -m http.server │
│ port 8000           │             │ port 8765 (statique)  │
│ /opt/chatbot/backend│             │ /opt/chatbot/frontend │
└──────────┬──────────┘             └───────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│ ChromaDB (embarque, dossier backend/chroma_db)│
│ Ollama local (:11434, modele llama3.2:1b)    │
└──────────────────────────────────────────────┘
```

## Services

| Composant | Chemin / port | Processus |
|---|---|---|
| Backend Flask | `/opt/chatbot/backend` — port 8000 | `./venv/bin/python -m app.api_agent` |
| Frontend statique | `/opt/chatbot/frontend` — port 8765 | `python3 -m http.server 8765 --bind 0.0.0.0` |
| Reverse proxy Caddy | Container Docker `caddy` — ports 80/443 | reseau Docker `web` |
| Ollama | `127.0.0.1:11434` | `ollama serve` (systemd) |
| ChromaDB | fichier `backend/chroma_db/` | embarque dans le backend |

Caddyfile : `/home/ubuntu/projects/caddy/Caddyfile`

## Prerequis serveur

- Ubuntu 24.04 ou equivalent, Python 3.12, Docker
- Ollama installe (`/usr/local/bin/ollama`) avec le modele `llama3.2:1b` telecharge
- Chromium installe via Playwright (`~/.cache/ms-playwright/chromium-*`) pour le scraping des sites SPA
- Caddy en container Docker, deja monte sur le reseau `web`

## Configuration (secrets)

Fichier `/opt/chatbot/backend/.env` (jamais commite — present dans `.gitignore`) :

```bash
# Clefs API LLM
ANTHROPIC_API_KEY=<votre_cle>

# Auth des endpoints admin (/api/scrape/run)
ADMIN_TOKEN=<token_aleatoire>   # genere avec: openssl rand -hex 24
JWT_SECRET=<secret_aleatoire>   # genere avec: openssl rand -hex 32

# LLM local
OLLAMA_MODEL=llama3.2:1b
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Scraper
SCRAPER_TARGET_URL=https://skapa-academy.fr
SCRAPER_INTERVAL_HOURS=24
SCRAPER_USER_AGENT=SkapaChatbotBot/1.0
```

Un fichier `.env.example` est versionne a la racine avec les champs attendus (avec placeholders uniquement).

## Lancement / redemarrage des services

### Backend

```bash
cd /opt/chatbot/backend
./venv/bin/python -m app.api_agent > /tmp/backend.log 2>&1 &
```

Pour arreter : `pkill -f 'app.api_agent'`

Logs : `tail -f /tmp/backend.log`

### Frontend statique

```bash
cd /opt/chatbot/frontend
python3 -m http.server 8765 --bind 0.0.0.0 > /tmp/frontend.log 2>&1 &
```

Pour arreter : `pkill -f 'http.server 8765'`

### Caddy

```bash
# Rechargement a chaud (0 downtime) apres edition du Caddyfile :
sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile

# Si le bind-mount du Caddyfile est "stale" (inode different), redemarrer :
sudo docker restart caddy
```

Logs : `sudo docker logs caddy --tail=50 -f`

## DNS

Entree DNS actuelle (geree chez OVH sur le domaine `skapa.design`) :

```
chat.skapa.design.  IN A  51.255.215.75
```

Verification de la propagation :
```bash
dig +short chat.skapa.design A @1.1.1.1
```

## Caddyfile — bloc `chat.skapa.design`

```caddy
chat.skapa.design {
    encode zstd gzip
    # Backend Flask (chat + endpoints admin) tourne sur l'hote, port 8000
    handle /chat* {
        reverse_proxy 172.18.0.1:8000
    }
    handle /api/* {
        reverse_proxy 172.18.0.1:8000
    }
    # Frontend statique sur l'hote, port 8765
    handle {
        reverse_proxy 172.18.0.1:8765
    }
}
```

L'IP `172.18.0.1` est la passerelle du reseau Docker `web` depuis le container Caddy — elle pointe vers l'hote.

## Mise a jour / redeploiement

```bash
cd /opt/chatbot
git pull origin main

# si le backend a change :
pkill -f 'app.api_agent'
cd backend && ./venv/bin/python -m app.api_agent > /tmp/backend.log 2>&1 &

# si le frontend a change : le serveur statique relit les fichiers a chaque requete,
# aucun redemarrage necessaire -- hard refresh suffit cote navigateur

# si Caddyfile a change :
sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## Operations courantes

### Tester la stack

```bash
# Backend direct
curl -s http://localhost:8000/

# Frontend direct
curl -sI http://localhost:8765/

# Via Caddy / HTTPS
curl -sI https://chat.skapa.design/

# Qui ecoute sur quels ports ?
sudo ss -tlnp | grep -E ':(80|443|8000|8765|11434)\b'
```

### Verifier le modele Ollama

```bash
ollama list                                      # liste des modeles installes
curl -s http://localhost:11434/api/tags | head  # via l'API
```

### Lancer un crawl manuel (sans l'UI)

```bash
curl -X POST https://chat.skapa.design/api/scrape/run \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://exemple.com"}'
```

## Depannage

### Le crawl ne recupere qu'une seule page

Le site est probablement une SPA (React/Vue/Next) et Playwright/Chromium est manquant ou corrompu.

```bash
# Reinstaller Chromium pour Playwright
/opt/chatbot/backend/venv/bin/playwright install chromium

# Tester
/opt/chatbot/backend/venv/bin/python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    print('OK')
    b.close()
"
```

### Erreur ChromaDB « ef or M too small »

La collection vectorielle n'a pas assez de points (ex. seulement 1 chunk a cause d'un crawl rate). Re-lancer un crawl complet du site : la fonction `replace_domain_chunks` reconstruit l'index.

### Caddy ne voit pas la nouvelle config

Le bind-mount du Caddyfile a un inode different (editeur qui replace le fichier au lieu d'editer en place). Solution :
```bash
sudo docker restart caddy
```

### Certificat Let's Encrypt n'est pas emis

```bash
sudo docker logs caddy --tail=100 | grep -iE 'error|challenge'
```
Verifier que :
- Le DNS pointe bien vers l'IP du serveur (`dig +short chat.skapa.design A`)
- Le port 80 est accessible publiquement (challenge HTTP-01)
- Aucun autre service n'ecoute sur 80/443

### Erreur « Impossible de joindre l'API »

Depuis la page HTTPS, le JS appelle une URL relative (meme origine). Si l'erreur apparait :
- Verifier que Caddy proxy bien `/chat*` et `/api/*` vers `172.18.0.1:8000`
- Verifier que le backend tourne : `curl http://localhost:8000/`

## Securite — points d'attention

- `backend/.env` contient les secrets ; il n'est **pas** commite (verifie dans `.gitignore`).
- **Rotation des secrets** : si le fichier `.env` a ete expose (ex. commit historique), regenerer immediatement :
  - Cle Anthropic sur https://console.anthropic.com/settings/keys
  - `ADMIN_TOKEN` : `openssl rand -hex 24`
  - `JWT_SECRET` : `openssl rand -hex 32`
- Le token admin peut etre pre-rempli dans `frontend/index.html` (variable `window.SKAPA_ADMIN_TOKEN`) pour une demo privee — **visible dans la source de la page**, a retirer pour toute diffusion plus large.
- Les anciens commits du depot peuvent contenir des secrets exposes ; un nettoyage via `git filter-repo` + force-push est necessaire pour les purger definitivement.

## Fichiers cles

- `/opt/chatbot/backend/.env` — secrets de production
- `/opt/chatbot/backend/app/config.py` — lecture des variables d'env
- `/opt/chatbot/backend/app/api_agent.py` — serveur Flask
- `/opt/chatbot/backend/scraper/pipeline.py` — pipeline de scraping
- `/opt/chatbot/frontend/index.html` — page de demo
- `/opt/chatbot/frontend/app.js` — logique chat + cartes d'action
- `/home/ubuntu/projects/caddy/Caddyfile` — config du reverse proxy
