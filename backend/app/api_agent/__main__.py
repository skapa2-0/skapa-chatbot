"""Permet `python -m app.api_agent` en local (dev)."""

import os

from app.api_agent import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True, use_reloader=False)
