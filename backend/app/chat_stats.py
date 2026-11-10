"""Calcul des statistiques d'usage à partir de la base SQLite."""

from app.metadata import get_connection


def _w(domain):
    """Retourne (clause WHERE sans date, params_domaine)."""
    if domain:
        return "domain=? AND", (domain,)
    return "", ()


def get_stats(domain: str, days: int, db_path=None) -> dict:
    conn = get_connection(db_path)
    span = f"-{days} days"
    wclause, wparams = _w(domain)

    date_filter = f"substr(date,1,10)>=date('now',?)"

    # Questions par jour
    rows = conn.execute(
        f"SELECT substr(date,1,10) d, count(*) n FROM chat_requests "
        f"WHERE {wclause} {date_filter} GROUP BY d ORDER BY d",
        (*wparams, span),
    ).fetchall()
    questions_per_day = [{"date": r["d"], "count": r["n"]} for r in rows]
    total = sum(r["count"] for r in questions_per_day)

    # Temps de réponse (hors erreurs)
    times = sorted(
        r[0] for r in conn.execute(
            f"SELECT duration_ms FROM chat_requests "
            f"WHERE {wclause} {date_filter} AND is_error=0",
            (*wparams, span),
        ).fetchall()
    )
    avg_ms = round(sum(times) / len(times)) if times else 0
    p95_ms = times[max(0, int(len(times) * 0.95) - 1)] if times else 0

    # Taux d'erreur
    errors = conn.execute(
        f"SELECT count(*) FROM chat_requests "
        f"WHERE {wclause} {date_filter} AND is_error=1",
        (*wparams, span),
    ).fetchone()[0]
    error_rate = round(errors / total, 3) if total else 0

    # Satisfaction (👍 / total votes)
    ups = conn.execute(
        f"SELECT count(*) FROM feedback WHERE {wclause} {date_filter} AND vote='up'",
        (*wparams, span),
    ).fetchone()[0]
    all_votes = conn.execute(
        f"SELECT count(*) FROM feedback WHERE {wclause} {date_filter}",
        (*wparams, span),
    ).fetchone()[0]
    satisfaction = round(ups / all_votes, 3) if all_votes else None

    # Clics par action
    click_rows = conn.execute(
        f"SELECT action, count(*) n FROM clicks "
        f"WHERE {wclause} {date_filter} GROUP BY action ORDER BY n DESC",
        (*wparams, span),
    ).fetchall()
    clicks_by_action = [{"action": r["action"], "count": r["n"]} for r in click_rows]

    return {
        "questions_per_day": questions_per_day,
        "total_questions": total,
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "error_rate": error_rate,
        "satisfaction": satisfaction,
        "total_clicks": sum(r["count"] for r in clicks_by_action),
        "clicks_by_action": clicks_by_action,
    }
