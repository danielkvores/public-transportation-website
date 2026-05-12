"""
tracking.py — Custom user-tracking for Where the Lines End.

Three things get logged:
  1. Page views        — server-side, in `before_request` (works with JS off)
  2. Time on page      — client-side, beacon on tab close / navigation
  3. Custom events     — country selection, metric toggles, chart-tab clicks

Privacy notes:
  * IP addresses are SHA-256 hashed with a salt before storage.
  * User-Agent is truncated to 300 chars; no parsing for fingerprinting.
  * Sessions are identified by a server-generated UUID held in a signed
    Flask cookie. No third party sees the data.
"""

import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from flask import (
    Blueprint,
    current_app,
    g,
    render_template,
    request,
    session,
)

bp = Blueprint("tracking", __name__)

# Paths we never log as page views.
EXCLUDE_PREFIXES = ("/static/", "/track/", "/api/", "/favicon")
EXCLUDE_PATHS = {"/tracker"}

IP_HASH_SALT = os.environ.get(
    "TRACKING_IP_SALT", "the-15-minute-divide-dev-salt"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_ip(ip: str) -> str:
    if not ip:
        return ""
    return hashlib.sha256((IP_HASH_SALT + ip).encode()).hexdigest()[:16]


def _db():
    return sqlite3.connect(current_app.config["DB_PATH"])


# ---------------------------------------------------------------------------
# Schema (idempotent)
# ---------------------------------------------------------------------------

def init_tracking_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracking_sessions (
            session_id  TEXT PRIMARY KEY,
            started_at  TEXT NOT NULL,
            user_agent  TEXT,
            ip_hash     TEXT,
            referrer    TEXT
        );

        CREATE TABLE IF NOT EXISTS tracking_pageviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            path        TEXT    NOT NULL,
            viewed_at   TEXT    NOT NULL,
            duration_ms INTEGER,
            FOREIGN KEY (session_id) REFERENCES tracking_sessions(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_pageviews_path
            ON tracking_pageviews(path);
        CREATE INDEX IF NOT EXISTS idx_pageviews_session
            ON tracking_pageviews(session_id);

        CREATE TABLE IF NOT EXISTS tracking_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            event_value TEXT,
            path        TEXT,
            occurred_at TEXT    NOT NULL,
            FOREIGN KEY (session_id) REFERENCES tracking_sessions(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_events_type
            ON tracking_events(event_type);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Session bootstrap & request hook
# ---------------------------------------------------------------------------

def _ensure_session() -> str:
    sid = session.get("tracking_sid")
    if sid:
        return sid
    sid = uuid.uuid4().hex
    session["tracking_sid"] = sid
    session.permanent = True
    conn = _db()
    conn.execute(
        "INSERT INTO tracking_sessions "
        "(session_id, started_at, user_agent, ip_hash, referrer) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            sid,
            _now_iso(),
            (request.user_agent.string or "")[:300],
            _hash_ip(request.remote_addr or ""),
            (request.referrer or "")[:500],
        ),
    )
    conn.commit()
    conn.close()
    return sid


def before_request_hook():
    if request.method != "GET":
        return
    path = request.path
    if path in EXCLUDE_PATHS:
        return
    if any(path.startswith(p) for p in EXCLUDE_PREFIXES):
        return

    sid = _ensure_session()
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tracking_pageviews (session_id, path, viewed_at) "
        "VALUES (?, ?, ?)",
        (sid, path, _now_iso()),
    )
    g.tracking_pageview_id = cur.lastrowid
    conn.commit()
    conn.close()


def context_processor():
    # Exposed to Jinja so base.html can render the meta tag.
    return {"tracking_pageview_id": getattr(g, "tracking_pageview_id", None)}


# ---------------------------------------------------------------------------
# Client-driven endpoints
# ---------------------------------------------------------------------------

@bp.post("/track/duration")
def track_duration():
    """JS pings here on page-hide with how long the page was visible."""
    data = request.get_json(silent=True) or {}
    pv_id = data.get("pageview_id")
    duration = data.get("duration_ms")
    if (
        not isinstance(pv_id, int)
        or not isinstance(duration, int)
        or duration < 0
        or duration > 24 * 60 * 60 * 1000  # cap absurd values at 24h
    ):
        return ("", 204)
    conn = _db()
    conn.execute(
        "UPDATE tracking_pageviews SET duration_ms = ? "
        "WHERE id = ? AND duration_ms IS NULL",
        (duration, pv_id),
    )
    conn.commit()
    conn.close()
    return ("", 204)


@bp.post("/track/event")
def track_event():
    """Generic event sink: country selected, chart tab clicked, etc."""
    data = request.get_json(silent=True) or {}
    et = (data.get("type") or "")[:50]
    ev = (data.get("value") or "")[:200]
    pth = (data.get("path") or "")[:200]
    if not et:
        return ("", 204)
    sid = session.get("tracking_sid")
    if not sid:
        return ("", 204)
    conn = _db()
    conn.execute(
        "INSERT INTO tracking_events "
        "(session_id, event_type, event_value, path, occurred_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (sid, et, ev, pth, _now_iso()),
    )
    conn.commit()
    conn.close()
    return ("", 204)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@bp.get("/tracker")
def dashboard():
    conn = _db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM tracking_sessions")
    n_sessions = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM tracking_pageviews")
    n_pageviews = cur.fetchone()["n"]

    cur.execute("""
        SELECT path,
               COUNT(*)                              AS views,
               ROUND(AVG(duration_ms) / 1000.0, 1)   AS avg_seconds,
               COUNT(duration_ms)                    AS n_with_duration
        FROM tracking_pageviews
        GROUP BY path
        ORDER BY views DESC
    """)
    by_page = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT event_value AS country, COUNT(*) AS n
        FROM tracking_events
        WHERE event_type = 'country_select' AND event_value <> ''
        GROUP BY event_value
        ORDER BY n DESC
        LIMIT 15
    """)
    countries = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT event_type, event_value AS metric, path, COUNT(*) AS n
        FROM tracking_events
        WHERE event_type IN ('chart_tab', 'metric_toggle')
        GROUP BY event_type, event_value, path
        ORDER BY n DESC
        LIMIT 20
    """)
    metric_use = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT event_type, event_value, path, occurred_at
        FROM tracking_events
        ORDER BY id DESC
        LIMIT 30
    """)
    recent_events = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT
            SUM(CASE WHEN n = 1 THEN 1 ELSE 0 END) AS bounced,
            COUNT(*)                                AS total
        FROM (
            SELECT session_id, COUNT(*) AS n
            FROM tracking_pageviews
            GROUP BY session_id
        )
    """)
    b = dict(cur.fetchone())
    bounce_pct = (
        round(100 * (b["bounced"] or 0) / b["total"], 1)
        if b["total"] else 0.0
    )

    conn.close()
    return render_template(
        "tracker.html",
        n_sessions=n_sessions,
        n_pageviews=n_pageviews,
        bounce_pct=bounce_pct,
        by_page=by_page,
        countries=countries,
        metric_use=metric_use,
        recent_events=recent_events,
    )
