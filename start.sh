#!/bin/bash
# Lancement en local, sans Docker.
# Usage : bash start.sh (depuis la racine du projet)
#
# Démarre deux serveurs :
#   API Flask  →  http://localhost:8000
#   Frontend   →  http://localhost:3000   (ouvre automatiquement dans le navigateur)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Trouver Python 3.12 ou 3.13 (pas 3.14+) ─────────────────────────────────
PYTHON_BIN=""
for candidate in python3.12 python3.13; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo ""
  echo "ERREUR: Python 3.12 ou 3.13 est requis."
  echo "Votre Python 3.14 n'est pas encore compatible avec certaines"
  echo "dépendances natives (greenlet, pydantic-core, chromadb)."
  echo ""
  echo "Pour installer Python 3.12 via Homebrew:"
  echo "  brew install python@3.12"
  echo ""
  exit 1
fi

echo "Python utilisé : $($PYTHON_BIN --version)"

# ── Backend — setup venv ──────────────────────────────────────────────────────
cd "$SCRIPT_DIR/backend"

# Recréer le venv s'il a été créé avec une version incompatible
if [ -d "venv" ]; then
  VENV_VERSION="$(venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ "$VENV_VERSION" != "3.12" ] && [ "$VENV_VERSION" != "3.13" ]; then
    echo "Environnement virtuel existant ($VENV_VERSION) incompatible, suppression..."
    rm -rf venv
  fi
fi

if [ ! -d "venv" ]; then
  echo "Création de l'environnement virtuel avec $PYTHON_BIN..."
  "$PYTHON_BIN" -m venv venv
fi

source venv/bin/activate

echo "Installation des dépendances..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Playwright Chromium (nécessaire pour les sites JS-rendus)
echo "Vérification du navigateur Playwright..."
playwright install chromium --quiet 2>/dev/null || true

# ── Fichier .env ──────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo ""
  echo "Aucun .env trouvé — copie de .env.example vers backend/.env"
  echo "Pense à renseigner OLLAMA_MODEL et ADMIN_TOKEN !"
  cp "$SCRIPT_DIR/.env.example" .env
fi

set -a
source .env
set +a

# ── Vérification Ollama ───────────────────────────────────────────────────────
if [ "${LLM_PROVIDER:-ollama}" != "anthropic" ]; then
  OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
  OLLAMA_URL="${OLLAMA_URL%% *}"
  if ! curl -s -m 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    echo ""
    echo "⚠️  ATTENTION : Ollama ne répond pas sur $OLLAMA_URL"
    echo "   → Lance 'ollama serve' dans un autre terminal"
    echo "   → Puis 'ollama pull ${OLLAMA_MODEL:-llama3.2}'"
    echo ""
  fi
fi

# ── Démarrer le frontend (serveur HTTP statique) ──────────────────────────────
FRONTEND_PORT=3000
echo "Démarrage du frontend sur http://localhost:$FRONTEND_PORT ..."

"$PYTHON_BIN" -m http.server "$FRONTEND_PORT" \
  --directory "$SCRIPT_DIR/frontend" \
  --bind 127.0.0.1 \
  >"$SCRIPT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

# Ouvrir le navigateur automatiquement (macOS)
sleep 0.5
open "http://localhost:$FRONTEND_PORT" 2>/dev/null || true

# Nettoyer le serveur frontend à la sortie
cleanup() {
  echo ""
  echo "Arrêt du serveur frontend (PID $FRONTEND_PID)..."
  kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── Démarrer l'API Flask ──────────────────────────────────────────────────────
echo ""
echo "ADMIN_TOKEN configuré : ${ADMIN_TOKEN:+oui ✓}"
echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│  Frontend  →  http://localhost:$FRONTEND_PORT          │"
echo "│  API       →  http://localhost:8000         │"
echo "│  API docs  →  http://localhost:8000/docs    │"
echo "└─────────────────────────────────────────────┘"
echo ""
python3 -m app.api_agent
