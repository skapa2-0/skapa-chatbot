#!/usr/bin/env bash
# Lance le backend Flask et build le widget React.
set -e

cd "$(dirname "$0")"

echo "==> Backend"
cd backend
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt --quiet
[ -f .env ] || cp .env.example .env
export FLASK_APP=run.py
python run.py &
BACKEND_PID=$!
cd ..

echo "==> Widget (frontend)"
cd frontend
npm install --silent
npm run build
cd ..

echo ""
echo "Backend en cours d'exécution sur http://localhost:5000 (PID $BACKEND_PID)"
echo "Widget buildé : frontend/dist/skapa-widget.js"
echo "Ctrl+C pour arrêter."

wait $BACKEND_PID
