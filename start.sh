#!/bin/bash
# Lancement en local, sans Docker.
# Usage : ./start.sh

set -e

cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
  echo "Creation de l'environnement virtuel..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "Installation des dependances..."
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "Aucun .env trouve, copie de .env.example -> pense a le remplir !"
  cp ../.env.example .env
fi

echo "Demarrage de l'API sur http://localhost:8000"
python -m app.api_agent
