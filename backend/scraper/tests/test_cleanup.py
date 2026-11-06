"""Tests pour scraper/cleanup.py (sans réseau, sans service externe)."""
import pytest
from unittest.mock import MagicMock, patch, call


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_collection(domains: list[str]):
    """Renvoie un mock de collection ChromaDB contenant les domaines donnés."""
    metas = [{"source_domain": d} for d in domains]
    col = MagicMock()
    col.get.return_value = {"metadatas": metas}
    return col


# ── delete_other_sites ────────────────────────────────────────────────────────

def test_other_site_deleted(tmp_path):
    """Site A indexé, puis site B indexé → A est supprimé de Chroma et SQLite."""
    col = _make_collection(["site-a.fr", "site-b.fr"])
    with (
        patch("scraper.cleanup.get_collection", return_value=col),
        patch("scraper.cleanup.delete_domain") as mock_del_chroma,
        patch("scraper.cleanup.delete_site") as mock_del_sql,
        patch("scraper.cleanup._keep_domains", return_value=set()),
    ):
        from scraper.cleanup import delete_other_sites
        n = delete_other_sites("site-b.fr")

    assert n == 1
    mock_del_chroma.assert_called_once_with("site-a.fr")
    mock_del_sql.assert_called_once_with("site-a.fr")


def test_protected_domain_kept(tmp_path):
    """Un domaine protégé (SCRAPE_KEEP_DOMAINS) n'est jamais supprimé."""
    col = _make_collection(["protected.fr", "site-b.fr"])
    with (
        patch("scraper.cleanup.get_collection", return_value=col),
        patch("scraper.cleanup.delete_domain") as mock_del_chroma,
        patch("scraper.cleanup.delete_site") as mock_del_sql,
        patch("scraper.cleanup._keep_domains", return_value={"protected.fr"}),
    ):
        from scraper.cleanup import delete_other_sites
        n = delete_other_sites("site-b.fr")

    assert n == 0
    mock_del_chroma.assert_not_called()
    mock_del_sql.assert_not_called()


def test_current_domain_never_deleted():
    """Le domaine courant n'est jamais supprimé, même s'il est dans Chroma."""
    col = _make_collection(["site-b.fr"])
    with (
        patch("scraper.cleanup.get_collection", return_value=col),
        patch("scraper.cleanup.delete_domain") as mock_del_chroma,
        patch("scraper.cleanup.delete_site") as mock_del_sql,
        patch("scraper.cleanup._keep_domains", return_value=set()),
    ):
        from scraper.cleanup import delete_other_sites
        n = delete_other_sites("site-b.fr")

    assert n == 0
    mock_del_chroma.assert_not_called()


# ── maybe_delete_others ───────────────────────────────────────────────────────

def test_flag_disabled_nothing_deleted():
    """Quand SCRAPE_KEEP_ONLY_LAST=false, nothing is deleted."""
    with (
        patch("scraper.cleanup.config") as mock_cfg,
        patch("scraper.cleanup.delete_other_sites") as mock_delete,
    ):
        mock_cfg.SCRAPE_KEEP_ONLY_LAST = False
        from scraper.cleanup import maybe_delete_others
        maybe_delete_others("any-site.fr")

    mock_delete.assert_not_called()


def test_flag_enabled_calls_delete():
    """Quand SCRAPE_KEEP_ONLY_LAST=true, delete_other_sites est appelé."""
    with (
        patch("scraper.cleanup.config") as mock_cfg,
        patch("scraper.cleanup.delete_other_sites", return_value=1) as mock_delete,
    ):
        mock_cfg.SCRAPE_KEEP_ONLY_LAST = True
        from scraper.cleanup import maybe_delete_others
        maybe_delete_others("site-b.fr")

    mock_delete.assert_called_once_with("site-b.fr")
