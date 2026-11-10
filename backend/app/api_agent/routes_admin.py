"""Routes admin : /api/feedback, /api/click, /api/stats, /api/sites."""

from flask import jsonify, request

from app import metadata
from app.api_agent import app
from app.api_agent.admin_guard import check_admin
from app.chat_stats import get_stats

_VALID_VOTES = {"up", "down"}
_MAX_ACTION = 100


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data = request.get_json(silent=True) or {}
    domain = str(data.get("domain") or "").strip()
    vote = str(data.get("vote") or "").strip()
    if not domain or vote not in _VALID_VOTES:
        return jsonify({"error": "domain requis, vote doit être 'up' ou 'down'"}), 400
    metadata.add_feedback(domain, vote)
    return jsonify({"ok": True})


@app.route("/api/click", methods=["POST"])
def api_click():
    data = request.get_json(silent=True) or {}
    domain = str(data.get("domain") or "").strip()
    action = str(data.get("action") or "").strip()[:_MAX_ACTION]
    if not domain or not action:
        return jsonify({"error": "domain et action requis"}), 400
    metadata.add_click(domain, action)
    return jsonify({"ok": True})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    denied = check_admin()
    if denied:
        return denied
    domain = request.args.get("domain", "")
    try:
        days = max(1, min(365, int(request.args.get("days", 7))))
    except ValueError:
        days = 7
    return jsonify(get_stats(domain, days))


@app.route("/api/sites", methods=["GET"])
def api_admin_sites():
    denied = check_admin()
    if denied:
        return denied
    return jsonify(metadata.get_admin_sites())
