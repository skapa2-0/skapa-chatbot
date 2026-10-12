"""Permet d'invoquer le pipeline via `python -m scraper.pipeline <url>`."""

import sys

from scraper.pipeline import run_pipeline

if __name__ == "__main__":
    run_pipeline(sys.argv[1] if len(sys.argv) > 1 else None)
