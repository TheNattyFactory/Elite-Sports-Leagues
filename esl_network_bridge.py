"""ESL Core: verified, idempotent sport-to-network report ingestion.

Sports authenticate with individual shared keys. ESL stores official reports as
league data; it does not invent player honors or change sporting results.
"""
import hashlib
import hmac
import json
import os
import re
import time

MAX_BYTES = 16384
ALLOWED = {"GAME_FINAL", "SIGNING", "AWARD", "LEAGUE_NEWS", "RETIREMENT", "CONTRACT_EXTENSION"}
SUPPORTED = {"baseball", "racing", "golf", "tennis", "mma", "football", "hockey", "basketball", "soccer"}


def init_schema(connect):
    c = connect()
    try:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS network_reports(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sport_id INTEGER NOT NULL,
          source_event_id TEXT NOT NULL,
          report_type TEXT NOT NULL,
          headline TEXT NOT NULL,
          summary TEXT NOT NULL,
          report_json TEXT NOT NULL DEFAULT '{}',
          occurred_at TEXT NOT NULL,
          received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(sport_id,source_event_id),
          FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_network_reports_recent
          ON network_reports(occurred_at DESC,id DESC);
        """)
        c.commit()
    finally:
        c.close()


def _failure(handler, code, message):
    return handler.send_json({"error": message}, code)


def ingest(handler, connect):
    """Call BEFORE the generic read_json() handler consumes the request body."""
    sport = (handler.headers.get("X-ESL-Sport") or "").strip().lower()
    secret = os.environ.get("ELITE_NETWORK_" + sport.upper() + "_SECRET", "") if sport in SUPPORTED else ""
    if not secret or len(secret) < 32:
        return _failure(handler, 403, "SPORT_PUBLISHING_NOT_CONFIGURED")
    raw_ts = (handler.headers.get("X-ESL-Timestamp") or "").strip()
    signature = (handler.headers.get("X-ESL-Signature") or "").strip()
    try:
        ts = int(raw_ts)
        if abs(time.time() - ts) > 300:
            return _failure(handler, 401, "SIGNATURE_EXPIRED")
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        return _failure(handler, 400, "INVALID_REQUEST")
    if length <= 0 or length > MAX_BYTES:
        return _failure(handler, 413, "PAYLOAD_SIZE_REJECTED")
    payload = handler.rfile.read(length)
    actual = hmac.new(secret.encode(), (raw_ts + ".").encode() + payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, "sha256=" + actual):
        return _failure(handler, 401, "INVALID_SIGNATURE")
    try:
        body = json.loads(payload)
    except (ValueError, UnicodeError):
        return _failure(handler, 400, "INVALID_JSON")
    if not isinstance(body, dict):
        return _failure(handler, 400, "INVALID_REPORT")
    event_id, kind = body.get("event_id"), body.get("type")
    headline, summary = body.get("headline"), body.get("summary")
    happened, details = body.get("occurred_at"), body.get("details", {})
    if not (isinstance(event_id, str) and re.fullmatch(r"[a-z0-9:_-]{3,120}", event_id)
            and isinstance(kind, str) and kind in ALLOWED
            and isinstance(headline, str) and 3 <= len(headline) <= 180
            and isinstance(summary, str) and 1 <= len(summary) <= 1200
            and isinstance(happened, str) and re.fullmatch(r"\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d", happened)
            and isinstance(details, dict) and len(json.dumps(details)) < 4500):
        return _failure(handler, 400, "INVALID_REPORT")
    # Dev/Genesis fixtures must never be republished as verified sports history.
    if event_id.startswith(("demo:", "test:", "genesis:")):
        return _failure(handler, 400, "TEST_REPORT_REJECTED")
    if kind == "GAME_FINAL":
        if not (isinstance(details.get("home"), str) and isinstance(details.get("away"), str)
                and isinstance(details.get("home_runs"), int) and isinstance(details.get("away_runs"), int)
                and 0 <= details["home_runs"] <= 999 and 0 <= details["away_runs"] <= 999):
            return _failure(handler, 400, "INVALID_SCORE")
    c = connect()
    try:
        row = c.execute("SELECT id FROM sports WHERE slug=? AND is_public=1", (sport,)).fetchone()
        if row is None:
            return _failure(handler, 403, "SPORT_NOT_PUBLIC")
        cur = c.execute("""INSERT OR IGNORE INTO network_reports
            (sport_id,source_event_id,report_type,headline,summary,report_json,occurred_at)
            VALUES(?,?,?,?,?,?,?)""", (row["id"], event_id, kind, headline, summary,
                                   json.dumps(details, separators=(",", ":")), happened.replace("T", " ")))
        created = bool(cur.rowcount)
        c.commit()
        return handler.send_json({"ok": True, "created": created, "duplicate": not created}, 201 if created else 200)
    finally:
        c.close()


def recent_reports(connect, limit=60):
    c = connect()
    try:
        recs = c.execute("""SELECT r.id,r.source_event_id,r.report_type,r.headline,r.summary,
                r.report_json,r.occurred_at AS published_at,
                s.slug sport_slug,s.name sport_name,s.icon
                FROM network_reports r JOIN sports s ON s.id=r.sport_id
                WHERE s.is_public=1 ORDER BY r.occurred_at DESC,r.id DESC LIMIT ?""", (limit,)).fetchall()
        output = []
        for r in recs:
            item = dict(r)
            item["id"] = "official:" + str(item["id"])
            try:
                item["details"] = json.loads(item.pop("report_json"))
            except (TypeError, ValueError):
                item["details"] = {}
            output.append(item)
        return output
    finally:
        c.close()


def receipt_status(connect):
    """Public operational facts: confirmed received events, not guessed connections."""
    c = connect()
    try:
        data = c.execute("""SELECT s.slug,s.name,s.status,
                   COUNT(r.id) AS report_count,MAX(r.received_at) AS last_received_at
                   FROM sports s LEFT JOIN network_reports r ON r.sport_id=s.id
                   WHERE s.is_public=1 GROUP BY s.id ORDER BY s.sort_order,s.name""").fetchall()
        sports=[dict(r) for r in data]
        return {"service":"esl-sports-network","sports":sports,
                "confirmed_reports":sum(int(s["report_count"]) for s in sports),
                "note":"Counts only authenticated league reports received; no activity does not mean a sport is offline."}
    finally:
        c.close()
