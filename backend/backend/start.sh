#!/bin/bash
# Lancement en local, sans Docker.
# Usage : ./start.sh

set -e

cd "$(dirname "$0")/backend"

# Le projet est cible sur Python 3.12 localement (comme runtime.txt).
# Python 3.14 n'est pas encore compatible avec certaines dependances
# natives utilisees par ChromaDB/Pydantic/greenlet dans les versions pinnees.
PYTHON_BIN=""
for candidate in python3.12 python3.13; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "ERREUR: Python 3.12 (recommande) ou 3.13 est requis." >&2
  echo "Sur macOS/Homebrew: brew install python@3.12" >&2
  exit 1
fi

# Recrée le venv s'il a été créé avec une version incompatible (ex: Python 3.14).
if [ -d "venv" ]; then
  VENV_VERSION="$(venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ "$VENV_VERSION" != "3.12" ] && [ "$VENV_VERSION" != "3.13" ]; then
    echo "Environnement virtuel incompatible ($VENV_VERSION), recreation..."
    rm -rf venv
  fi
fi

if [ ! -d "venv" ]; then
  echo "Creation de l'environnement virtuel avec $PYTHON_BIN..."
  "$PYTHON_BIN" -m venv venv
fi

source venv/bin/activate

echo "Installation des dependances..."
pip install -q -r requirements.txt

# Le moteur Playwright nécessite un navigateur installé en local.
echo "Verification du navigateur Playwright..."
if ! playwright install chromium >/dev/null 2>&1; then
  echo "ERREUR: impossible d'installer Chromium pour Playwright." >&2
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "Aucun .env trouve, copie de .env.example -> pense a le remplir !"
  cp ../.env.example .env
fi

# Charger les variables du fichier .env
set -a
source .env
set +a

echo "ADMIN_TOKEN charge : ${ADMIN_TOKEN:+oui}"

echo "Demarrage de l'API sur http://localhost:8000"
python -m app.api_agent