"""EBL -> ESL Sports Network publisher. Deploy alongside EBL server.py.

Runs only when EBL_ESL_PUBLISH_ENABLED=1 and a 32+ byte secret is configured.
Initial activation starts from the current event edge; it does not syndicate
historical Genesis/test matches. Only committed EBL DB records are published.
"""
import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ALLOWED_TX = {"CONTRACT_SIGNED": "SIGNING", "RENEWAL_ACCEPTED": "CONTRACT_EXTENSION", "PLAYER_RETIRED": "RETIREMENT"}


def configured():
    secret = os.environ.get("EBL_ESL_NETWORK_SECRET", "")
    url = os.environ.get("EBL_ESL_CORE_URL", "").rstrip("/")
    if os.environ.get("EBL_ESL_PUBLISH_ENABLED", "0") != "1":
        return False
    if len(secret) < 32 or not url:
        raise RuntimeError("EBL ESL bridge requires EBL_ESL_CORE_URL and a 32+ byte EBL_ESL_NETWORK_SECRET")
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
        raise RuntimeError("ESL bridge requires HTTPS except for localhost testing")
    return True


def send_report(event):
    url = os.environ["EBL_ESL_CORE_URL"].rstrip("/") + "/api/network/ingest"
    secret = os.environ["EBL_ESL_NETWORK_SECRET"]
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), (ts + ".").encode() + body, hashlib.sha256).hexdigest()
    req = Request(url, body, method="POST", headers={
        "Content-Type": "application/json", "X-ESL-Sport": "baseball",
        "X-ESL-Timestamp": ts, "X-ESL-Signature": "sha256=" + sig,
        "User-Agent": "EBL-ESL-Network/2.0"
    })
    with urlopen(req, timeout=8) as result:
        response = json.loads(result.read().decode())
        if result.status not in (200, 201) or not response.get("ok"):
            raise RuntimeError("ESL rejected report")
        return response


def _get(c, k):
    x = c.execute("SELECT v FROM league_state WHERE k=?", ("esln_" + k,)).fetchone()
    return x["v"] if x else None


def _set(c, k, v):
    c.execute("INSERT OR REPLACE INTO league_state(k,v) VALUES(?,?)", ("esln_" + k, str(v)))


def bootstrap(connect):
    """Skip preexisting records, but watch future finals even on the same day."""
    if not configured():
        return False
    c=connect()
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS esln_sent_games(
            game_id TEXT PRIMARY KEY, published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        if _get(c, "bootstrapped") == "1":
            c.commit()
            return True
        for kind, table in (("news_id","news"),("award_id","award_history"),("tx_id","transactions")):
            _set(c,kind,c.execute(f"SELECT COALESCE(MAX(id),0) AS last FROM {table}").fetchone()["last"])
        latest=c.execute("""SELECT season,league_day FROM games WHERE status='FINAL'
                    ORDER BY season DESC,league_day DESC LIMIT 1""").fetchone()
        if latest:
            season,day=int(latest["season"]),int(latest["league_day"])
            _set(c,"game_season",season);_set(c,"game_day",day)
            c.execute("""INSERT OR IGNORE INTO esln_sent_games(game_id)
                SELECT id FROM games WHERE status='FINAL' AND season=? AND league_day=?""",(season,day))
        else:
            _set(c,"game_season",0);_set(c,"game_day",0)
        _set(c,"bootstrapped",1)
        c.commit()
        return True
    finally:
        c.close()


def _now(row):
    value = row["created_at"] if "created_at" in row.keys() else ""
    return str(value)[:19] if value else time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _team(c, fid):
    if not fid:
        return ""
    r=c.execute("""SELECT COALESCE(NULLIF(TRIM(b.display_name),''),f.name) name
         FROM franchises f LEFT JOIN franchise_branding b ON b.franchise_id=f.id
         WHERE f.id=?""", (str(fid),)).fetchone()
    return str(r["name"]) if r else ""


def _player(c, pid, fallback="Player"):
    if not pid:
        return fallback
    r=c.execute("SELECT name FROM players WHERE id=?", (pid,)).fetchone()
    return str(r["name"]) if r else fallback


def _report_tx(c, r):
    kind=ALLOWED_TX.get(str(r["event_type"]).upper())
    if not kind: return None
    try: data=json.loads(r["payload_json"] or "{}")
    except (ValueError, TypeError): return None
    player = _player(c,data.get("player_id"),data.get("player_name") or "Player")
    club = _team(c,data.get("franchise_id"))
    if not player or player == "Player" or (kind!="RETIREMENT" and not club): return None
    if kind=="SIGNING":
        headline=f"{player} signs with {club}"
        body=f"The {club} announce a contract signing with {player}."
    elif kind=="CONTRACT_EXTENSION":
        headline=f"{club} extend {player}"
        body=f"{player} and the {club} have agreed to a new contract."
    else:
        headline=f"{player} announces EBL retirement"
        body=f"{player} has retired from the Elite Baseball League."
    return dict(event_id=f"tx:{r['id']}",type=kind,headline=headline[:180],summary=body,
                occurred_at=_now(r),details={"transaction_id":r["id"],"player_id":data.get("player_id"),"team":club})


def _report_news(r):
    # Score finals and awards have dedicated authoritative feeds below; don't
    # syndicate their companion news items twice.
    if str(r["category"] or "").upper() in {"GAME", "AWARD"}: return None
    if int(r["importance"] or 0) < 2: return None
    return dict(event_id=f"news:{r['id']}",type="LEAGUE_NEWS",
                headline=str(r["headline"])[:180],summary=str(r["body"])[:1200],
                occurred_at=_now(r),details={"season":r["season"],"league_day":r["league_day"],"news_id":r["id"]})


def _report_award(c, r):
    name=_player(c,r["player_id"])
    club=_team(c,r["franchise_id"])
    title=str(r["award_name"])
    return dict(event_id=f"award:{r['id']}",type="AWARD",
                headline=f"{name} earns {title}"[:180],
                summary=f"Season {r['season']} · {str(r['period']).replace('_',' ').title()} · {club or 'Elite Baseball League'}",
                occurred_at=_now(r),details={"award_code":r["award_code"],"season":r["season"],"player_id":r["player_id"]})


def _report_final(r):
    gid=str(r["id"])
    aw,ho=str(r["away_name"]),str(r["home_name"])
    ar,hr=int(r["away_runs"]),int(r["home_runs"])
    return dict(event_id="game:" + hashlib.sha256(gid.encode()).hexdigest()[:40],type="GAME_FINAL",
                headline=f"{aw} {ar}, {ho} {hr} — Final"[:180],
                summary=f"Season {r['season']} · League Day {r['league_day']} · Final score",
                occurred_at=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                details={"game_id":gid,"season":r["season"],"league_day":r["league_day"],
                         "away":aw,"home":ho,"away_runs":ar,"home_runs":hr})


def tick(connect, cap=30):
    """One publishing pass; database cursors only advance on positive receipt."""
    if not configured():
        return 0
    bootstrap(connect)
    c=connect();count=0
    try:
        for key, table, make in (("tx_id","transactions",_report_tx),
                                 ("news_id","news",lambda c,r:_report_news(r)),
                                 ("award_id","award_history",_report_award)):
            last=int(_get(c,key) or 0)
            rr=c.execute(f"SELECT * FROM {table} WHERE id>? ORDER BY id LIMIT ?",(last,cap)).fetchall()
            for record in rr:
                obj=make(c,record)
                if obj:
                    send_report(obj)  # failures do not advance the cursor
                    count+=1
                _set(c,key,record["id"])
                c.commit()
        season=int(_get(c,"game_season") or 0)
        day=int(_get(c,"game_day") or 0)
        gg=c.execute("""SELECT g.*,
               COALESCE(NULLIF(TRIM(ab.display_name),''),af.name) away_name,
               COALESCE(NULLIF(TRIM(hb.display_name),''),hf.name) home_name
               FROM games g JOIN franchises af ON af.id=g.away_id
               JOIN franchises hf ON hf.id=g.home_id
               LEFT JOIN franchise_branding ab ON ab.franchise_id=g.away_id
               LEFT JOIN franchise_branding hb ON hb.franchise_id=g.home_id
               LEFT JOIN esln_sent_games sg ON sg.game_id=g.id
               WHERE g.status='FINAL' AND sg.game_id IS NULL
                 AND (g.season>? OR (g.season=? AND g.league_day>=?))
               ORDER BY g.season,g.league_day,g.id LIMIT ?""",(season,season,day,cap)).fetchall()
        for record in gg:
            send_report(_report_final(record))
            c.execute("INSERT OR IGNORE INTO esln_sent_games(game_id) VALUES(?)", (record["id"],))
            _set(c,"game_season",record["season"])
            _set(c,"game_day",record["league_day"])
            c.commit();count+=1
        return count
    finally:
        c.close()


def worker(connect, interval=15):
    if not configured(): return
    while True:
        try:
            n=tick(connect)
            if n: print(f"ESL SPORTS NETWORK: published {n} confirmed EBL events",flush=True)
        except Exception as exc:
            print(f"ESL SPORTS NETWORK: retrying after {type(exc).__name__}",flush=True)
        time.sleep(interval)
