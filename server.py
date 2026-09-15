
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import json
import sqlite3
from pathlib import Path
import hashlib
import hmac
import secrets
import time
import re
import base64
import os
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "elite_core.db"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT","8080"))
SESSION_COOKIE = "elite_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
GATEWAY_TTL_SECONDS = 60
GATEWAY_SECRET = os.environ.get("ELITE_GATEWAY_SECRET","dev-only-change-me-before-production")
APP_ENV = os.environ.get("ELITE_ENV","development").lower()
if APP_ENV=="production" and GATEWAY_SECRET=="dev-only-change-me-before-production":
    raise RuntimeError("ELITE_GATEWAY_SECRET is required in production")
VERIFY_TTL_SECONDS = 60 * 60 * 24
RESET_TTL_SECONDS = 60 * 30
PUBLIC_REGISTRATION = os.environ.get("ELITE_PUBLIC_REGISTRATION","1") == "1"
EMAIL_PROVIDER = os.environ.get("ELITE_EMAIL_PROVIDER","dev").lower()
EMAIL_FROM = os.environ.get("ELITE_EMAIL_FROM","Elite Sports <noreply@example.com>")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY","")
APP_BASE_URL = os.environ.get("ELITE_APP_BASE_URL","http://localhost:8080").rstrip("/")
CSRF_COOKIE = "elite_csrf"
RATE_WINDOW_SECONDS = 60
RATE_LIMITS = {"LOGIN":12,"REGISTER":6,"RESET_REQUEST":6,"VERIFY_RESEND":5}

SPORTS = [
    ("baseball","Elite Baseball League","EBL","LIVE","⚾",1),
    ("racing","Elite Stock Car Racing","ESCR","ALPHA","🏎️",2),
    ("basketball","Elite Basketball","EBL-B","DEVELOPMENT","🏀",3),
    ("football","Elite Football","EFL","DEVELOPMENT","🏈",4),
    ("hockey","Elite Hockey","EHL","DEVELOPMENT","🏒",5),
    ("soccer","Elite Soccer","ESL-S","DEVELOPMENT","⚽",6),
    ("mma","Elite MMA","EMMA","DEVELOPMENT","🥊",7),
    ("golf","Elite Golf League","EGL","DEVELOPMENT","⛳",8),
    ("tennis","Elite Tennis","ETL","DEVELOPMENT","🎾",9),
]

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_security_schema():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS email_verification_tokens(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token_hash TEXT UNIQUE NOT NULL,
      expires_at INTEGER NOT NULL,
      used_at INTEGER,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS password_reset_tokens(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token_hash TEXT UNIQUE NOT NULL,
      expires_at INTEGER NOT NULL,
      used_at INTEGER,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS account_security_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      event_type TEXT NOT NULL,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS legal_documents(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      document_key TEXT NOT NULL,
      version TEXT NOT NULL,
      title TEXT NOT NULL,
      published_at INTEGER NOT NULL,
      is_current INTEGER NOT NULL DEFAULT 1,
      UNIQUE(document_key,version)
    );

    CREATE TABLE IF NOT EXISTS legal_acceptances(
      user_id INTEGER NOT NULL,
      legal_document_id INTEGER NOT NULL,
      accepted_at INTEGER NOT NULL,
      PRIMARY KEY(user_id,legal_document_id),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(legal_document_id) REFERENCES legal_documents(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS invitations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email_normalized TEXT,
      invite_code_hash TEXT UNIQUE NOT NULL,
      intended_role TEXT,
      expires_at INTEGER,
      redeemed_by_user_id INTEGER,
      redeemed_at INTEGER,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(redeemed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS dev_email_outbox(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      email TEXT NOT NULL,
      email_type TEXT NOT NULL,
      subject TEXT NOT NULL,
      token TEXT,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS rate_limit_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      bucket_key TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_rate_limit_bucket
      ON rate_limit_events(bucket_key,created_at);
    """)
    now = int(time.time())
    for key,title in [
        ("TERMS","Terms of Service"),
        ("PRIVACY","Privacy Policy"),
        ("COMMUNITY_RULES","Community Rules"),
    ]:
        c.execute("""INSERT OR IGNORE INTO legal_documents(
            document_key,version,title,published_at,is_current
        ) VALUES(?,?,?,?,1)""",(key,"1.0",title,now))
    c.commit()
    c.close()

def security_event(user_id, event_type, metadata=None):
    c = conn()
    c.execute("""INSERT INTO account_security_events(user_id,event_type,metadata_json,created_at)
                 VALUES(?,?,?,?)""",
              (user_id,event_type,json.dumps(metadata or {}),int(time.time())))
    c.commit()
    c.close()

def issue_account_token(user_id, table_name, ttl_seconds):
    if table_name not in {"email_verification_tokens","password_reset_tokens"}:
        raise ValueError("invalid token table")
    raw = secrets.token_urlsafe(32)
    now = int(time.time())
    c = conn()
    c.execute(f"DELETE FROM {table_name} WHERE user_id=? AND used_at IS NULL",(user_id,))
    c.execute(f"""INSERT INTO {table_name}(user_id,token_hash,expires_at,created_at)
                  VALUES(?,?,?,?)""",
              (user_id,token_hash(raw),now+ttl_seconds,now))
    c.commit()
    c.close()
    return raw

def consume_account_token(raw, table_name):
    if table_name not in {"email_verification_tokens","password_reset_tokens"}:
        return None
    now = int(time.time())
    c = conn()
    r = c.execute(f"""SELECT id,user_id FROM {table_name}
                      WHERE token_hash=? AND used_at IS NULL AND expires_at>?
                      LIMIT 1""",(token_hash(raw),now)).fetchone()
    if not r:
        c.close()
        return None
    c.execute(f"UPDATE {table_name} SET used_at=? WHERE id=?",(now,r["id"]))
    c.commit()
    uid = r["user_id"]
    c.close()
    return uid

def send_transactional_email(user_id,email,email_type,subject,token):
    verify_url=f"{APP_BASE_URL}/verify.html?token={urllib.parse.quote(token)}"
    reset_url=f"{APP_BASE_URL}/reset-password.html?token={urllib.parse.quote(token)}"

    if email_type=="VERIFY_EMAIL":
        text=f"Verify your Elite Sports account: {verify_url}"
    elif email_type=="PASSWORD_RESET":
        text=f"Reset your Elite Sports password: {reset_url}"
    else:
        text=subject

    if APP_ENV!="production" or EMAIL_PROVIDER=="dev":
        c=conn()
        c.execute("""INSERT INTO dev_email_outbox(user_id,email,email_type,subject,token,created_at)
                     VALUES(?,?,?,?,?,?)""",
                  (user_id,email,email_type,subject,token,int(time.time())))
        c.commit()
        c.close()
        return True

    if EMAIL_PROVIDER=="resend":
        if not RESEND_API_KEY:
            raise RuntimeError("RESEND_API_KEY is required")
        payload=json.dumps({
            "from":EMAIL_FROM,
            "to":[email],
            "subject":subject,
            "text":text
        }).encode("utf-8")
        req=urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            method="POST",
            headers={
                "Authorization":f"Bearer {RESEND_API_KEY}",
                "Content-Type":"application/json"
            }
        )
        try:
            with urllib.request.urlopen(req,timeout=10) as resp:
                ok = 200 <= resp.status < 300
                print(f"EMAIL_DELIVERY {'SUCCESS' if ok else 'FAILED'} type={email_type} provider=resend status={resp.status}", flush=True)
                if not ok:
                    security_event(user_id,"EMAIL_DELIVERY_FAILED",{"type":email_type,"status":resp.status})
                return ok
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                detail = ""
            safe_detail = re.sub(r'(?i)(bearer\s+)[^\s"}]+', r'\1[REDACTED]', detail)
            print(f"EMAIL_DELIVERY FAILED type={email_type} provider=resend http_status={exc.code} detail={safe_detail}", flush=True)
            security_event(user_id,"EMAIL_DELIVERY_FAILED",{"type":email_type,"http_status":exc.code,"error":safe_detail[:200]})
            return False
        except Exception as exc:
            safe_error = str(exc)[:300]
            print(f"EMAIL_DELIVERY FAILED type={email_type} provider=resend error={safe_error}", flush=True)
            security_event(user_id,"EMAIL_DELIVERY_FAILED",{"type":email_type,"error":safe_error[:200]})
            return False

    raise RuntimeError(f"Unsupported email provider: {EMAIL_PROVIDER}")

def client_ip_hash(handler):
    forwarded=(handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    raw=forwarded or handler.client_address[0]
    secret=os.environ.get("ELITE_IP_HASH_SECRET","dev-ip-secret")
    return hashlib.sha256((secret+"|"+raw).encode()).hexdigest()

def rate_limit_check(handler,bucket,identity=""):
    limit=RATE_LIMITS.get(bucket)
    if not limit:
        return True
    now=int(time.time())
    key=hashlib.sha256(f"{bucket}|{identity.lower()}|{client_ip_hash(handler)}".encode()).hexdigest()
    c=conn()
    cutoff=now-RATE_WINDOW_SECONDS
    c.execute("DELETE FROM rate_limit_events WHERE created_at<?",(cutoff,))
    count=c.execute(
        "SELECT COUNT(*) n FROM rate_limit_events WHERE bucket_key=? AND created_at>=?",
        (key,cutoff)
    ).fetchone()["n"]
    if count>=limit:
        c.commit()
        c.close()
        return False
    c.execute("INSERT INTO rate_limit_events(bucket_key,created_at) VALUES(?,?)",(key,now))
    c.commit()
    c.close()
    return True

def csrf_cookie_value(handler):
    cookie=handler.headers.get("Cookie") or ""
    m=re.search(r"(?:^|;\s*)"+re.escape(CSRF_COOKIE)+r"=([^;]+)",cookie)
    return m.group(1) if m else None

def csrf_required(handler,path):
    if handler.command not in {"POST","PUT","PATCH","DELETE"}:
        return False
    if path.startswith("/api/adapter/"):
        return False
    return path not in {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/request-password-reset",
        "/api/auth/reset-password",
        "/api/auth/verify-email",
        "/api/gateway/consume",
        "/api/gateway/link-external"
    }

def validate_csrf(handler,path):
    if not csrf_required(handler,path):
        return True
    cookie_token=csrf_cookie_value(handler)
    header_token=handler.headers.get("X-CSRF-Token")
    return bool(cookie_token and header_token and secrets.compare_digest(cookie_token,header_token))

def accept_current_legal(user_id):
    now = int(time.time())
    c = conn()
    docs = c.execute("SELECT id FROM legal_documents WHERE is_current=1").fetchall()
    c.executemany("""INSERT OR IGNORE INTO legal_acceptances(user_id,legal_document_id,accepted_at)
                     VALUES(?,?,?)""",[(user_id,d["id"],now) for d in docs])
    c.commit()
    c.close()

def has_current_legal_acceptance(user_id):
    c = conn()
    required = c.execute("SELECT COUNT(*) n FROM legal_documents WHERE is_current=1").fetchone()["n"]
    accepted = c.execute("""SELECT COUNT(*) n
                            FROM legal_acceptances la
                            JOIN legal_documents ld ON ld.id=la.legal_document_id
                            WHERE la.user_id=? AND ld.is_current=1""",(user_id,)).fetchone()["n"]
    c.close()
    return required > 0 and accepted == required

def password_hash(password: str):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${dk.hex()}"

def password_verify(password: str, encoded: str):
    try:
        algo, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            int(rounds)
        )
        return hmac.compare_digest(test.hex(), digest_hex)
    except Exception:
        return False

def init_db():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      email TEXT UNIQUE NOT NULL,
      display_name TEXT NOT NULL,
      password_hash TEXT,
      legacy_points INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      email_verified INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS sessions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token_hash TEXT UNIQUE NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS gateway_tokens(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      sport_id INTEGER NOT NULL,
      nonce TEXT UNIQUE NOT NULL,
      expires_at INTEGER NOT NULL,
      used_at INTEGER,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS sport_account_links(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      sport_id INTEGER NOT NULL,
      external_user_id TEXT NOT NULL,
      external_username TEXT,
      sport_role TEXT NOT NULL DEFAULT 'PLAYER',
      linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_synced_at TEXT,
      UNIQUE(sport_id, external_user_id),
      UNIQUE(user_id, sport_id),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS profile_settings(
      user_id INTEGER PRIMARY KEY,
      bio TEXT,
      banner_label TEXT,
      featured_sport_slug TEXT,
      public_profile INTEGER NOT NULL DEFAULT 1,
      show_activity INTEGER NOT NULL DEFAULT 1,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS activity_feed(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      sport_id INTEGER,
      activity_type TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT,
      external_ref TEXT,
      visibility TEXT NOT NULL DEFAULT 'PUBLIC',
      occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_activity_user_time
      ON activity_feed(user_id, occurred_at DESC);

    CREATE INDEX IF NOT EXISTS idx_activity_global_time
      ON activity_feed(visibility, occurred_at DESC);

    CREATE TABLE IF NOT EXISTS sports(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slug TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      short_name TEXT NOT NULL,
      status TEXT NOT NULL,
      icon TEXT NOT NULL,
      base_url TEXT NOT NULL DEFAULT '#',
      sort_order INTEGER NOT NULL DEFAULT 100,
      is_public INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS user_sport_memberships(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      sport_id INTEGER NOT NULL,
      role TEXT NOT NULL DEFAULT 'PLAYER',
      joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_active_at TEXT,
      UNIQUE(user_id,sport_id),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS careers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      sport_id INTEGER NOT NULL,
      external_career_id TEXT,
      display_name TEXT NOT NULL,
      team_name TEXT,
      role_name TEXT,
      season_label TEXT,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS legacy_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      sport_id INTEGER,
      event_type TEXT NOT NULL,
      title TEXT NOT NULL,
      points INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS hub_news(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sport_id INTEGER,
      headline TEXT NOT NULL,
      summary TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 0,
      published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      is_featured INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE SET NULL
    );
    """)

    # Migration safety for earlier DB versions.
    cols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "email_verified" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")

    for slug,name,short,status,icon,sort_order in SPORTS:
        c.execute("""
          INSERT INTO sports(slug,name,short_name,status,icon,sort_order)
          VALUES(?,?,?,?,?,?)
          ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            short_name=excluded.short_name,
            status=excluded.status,
            icon=excluded.icon,
            sort_order=excluded.sort_order
        """,(slug,name,short,status,icon,sort_order))

    # Sport destinations are configured independently so the hub never hardcodes a league deployment.
    sport_urls = {
        "baseball": os.environ.get("ELITE_BASEBALL_URL", "").strip(),
        "racing": os.environ.get("ELITE_RACING_URL", "").strip(),
        "basketball": os.environ.get("ELITE_BASKETBALL_URL", "").strip(),
        "football": os.environ.get("ELITE_FOOTBALL_URL", "").strip(),
        "hockey": os.environ.get("ELITE_HOCKEY_URL", "").strip(),
        "soccer": os.environ.get("ELITE_SOCCER_URL", "").strip(),
        "mma": os.environ.get("ELITE_MMA_URL", "").strip(),
        "golf": os.environ.get("ELITE_GOLF_URL", "").strip(),
        "tennis": os.environ.get("ELITE_TENNIS_URL", "").strip(),
    }
    for sport_slug, sport_url in sport_urls.items():
        if sport_url:
            c.execute("UPDATE sports SET base_url=? WHERE slug=?", (sport_url, sport_slug))

    if os.environ.get("ELITE_SEED_DEMO","0") == "1":
        demo = c.execute("SELECT * FROM users WHERE username='t-money'").fetchone()
        if not demo:
            c.execute("""
              INSERT INTO users(username,email,display_name,password_hash,legacy_points,email_verified)
              VALUES(?,?,?,?,?,?)
            """,("t-money","tmoney@example.com","T-Money",password_hash("EliteDemo123!"),1840,1))
        elif not demo["password_hash"]:
            c.execute("""
              UPDATE users SET password_hash=?, email_verified=1
              WHERE id=?
            """,(password_hash("EliteDemo123!"),demo["id"]))
    
        uid = c.execute("SELECT id FROM users WHERE username='t-money'").fetchone()["id"]
        baseball = c.execute("SELECT id FROM sports WHERE slug='baseball'").fetchone()["id"]
        racing = c.execute("SELECT id FROM sports WHERE slug='racing'").fetchone()["id"]
    
        c.execute("INSERT OR IGNORE INTO user_sport_memberships(user_id,sport_id,role) VALUES(?,?,?)",(uid,baseball,"PLAYER"))
        c.execute("INSERT OR IGNORE INTO user_sport_memberships(user_id,sport_id,role) VALUES(?,?,?)",(uid,racing,"PLAYER"))
    
        if c.execute("SELECT COUNT(*) n FROM careers WHERE user_id=?",(uid,)).fetchone()["n"] == 0:
            c.execute("""INSERT INTO careers(user_id,sport_id,external_career_id,display_name,team_name,role_name,season_label)
                         VALUES(?,?,?,?,?,?,?)""",(uid,baseball,"ebl-player-1","Thomas Garner","Atlanta Firebirds","SS","Season 3"))
            c.execute("""INSERT INTO careers(user_id,sport_id,external_career_id,display_name,team_name,role_name,season_label)
                         VALUES(?,?,?,?,?,?,?)""",(uid,racing,"escr-driver-1","T. Garner","#28 • Garner Racing","Driver","Season 1"))
    
        if c.execute("SELECT COUNT(*) n FROM legacy_events WHERE user_id=?",(uid,)).fetchone()["n"] == 0:
            c.executemany("""INSERT INTO legacy_events(user_id,sport_id,event_type,title,points) VALUES(?,?,?,?,?)""",[
                (uid,baseball,"CHAMPIONSHIP","Baseball Championship",500),
                (uid,baseball,"MAJOR_AWARD","Season MVP",250),
                (uid,baseball,"SEASON_COMPLETED","Completed Baseball Season",100),
                (uid,baseball,"SEASON_COMPLETED","Completed Baseball Season",100),
                (uid,baseball,"SEASON_COMPLETED","Completed Baseball Season",100),
                (uid,racing,"WIN","First Career Racing Win",150),
                (uid,racing,"SEASON_COMPLETED","Completed Racing Season",100),
            ])
    
    
        c.execute("""INSERT INTO profile_settings(user_id,bio,banner_label,featured_sport_slug)
                     VALUES(?,?,?,?)
                     ON CONFLICT(user_id) DO NOTHING""",
                  (uid,"Multi-sport Elite competitor building a legacy across the universe.",
                   "FOUNDING MEMBER","baseball"))
    
        if c.execute("SELECT COUNT(*) n FROM activity_feed WHERE user_id=?",(uid,)).fetchone()["n"] == 0:
            c.executemany("""INSERT INTO activity_feed(
              user_id,sport_id,activity_type,title,description,external_ref,visibility,occurred_at
            ) VALUES(?,?,?,?,?,?,?,?)""",[
              (uid,baseball,"CHAMPIONSHIP","Won the EBL Championship",
               "Captured a Baseball championship with the Atlanta Firebirds.",
               "demo-ebl-title","PUBLIC","2026-08-30 20:00:00"),
              (uid,racing,"CAREER_WIN","First Elite Stock Car victory",
               "Earned the first career win in Elite Stock Car Racing.",
               "demo-escr-win","PUBLIC","2026-09-08 19:30:00"),
              (uid,baseball,"SEASON_MILESTONE","Completed another EBL season",
               "Added another completed Baseball season to the Career Passport.",
               "demo-ebl-season","PUBLIC","2026-09-02 18:00:00")
            ])
    
        if c.execute("SELECT COUNT(*) n FROM hub_news").fetchone()["n"] == 0:
            basketball = c.execute("SELECT id FROM sports WHERE slug='basketball'").fetchone()["id"]
            c.executemany("""INSERT INTO hub_news(sport_id,headline,summary,priority,is_featured) VALUES(?,?,?,?,?)""",[
                (baseball,"Atlanta clinches division title","A late-season surge locks up the division and sets the stage for October.",10,1),
                (racing,"Rookie earns first career victory","The newest Elite series produces its first breakout moment of the season.",9,1),
                (basketball,"Basketball league foundation enters planning phase","Teams, careers, contracts and season structure are being designed now.",8,0),
            ])
    c.commit()
    c.close()


def b64url(data: bytes):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def b64url_decode(text: str):
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)

def sign_gateway_payload(payload_bytes: bytes):
    return hmac.new(GATEWAY_SECRET.encode(), payload_bytes, hashlib.sha256).digest()

def create_gateway_token(user_id: int, sport_id: int):
    nonce = secrets.token_urlsafe(16)
    now = int(time.time())
    exp = now + GATEWAY_TTL_SECONDS
    payload = {"uid": user_id, "sid": sport_id, "nonce": nonce, "iat": now, "exp": exp}
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    token = f"{b64url(payload_bytes)}.{b64url(sign_gateway_payload(payload_bytes))}"

    c = conn()
    c.execute("DELETE FROM gateway_tokens WHERE expires_at < ? OR used_at IS NOT NULL", (now,))
    c.execute("""
      INSERT INTO gateway_tokens(user_id,sport_id,nonce,expires_at,created_at)
      VALUES(?,?,?,?,?)
    """, (user_id, sport_id, nonce, exp, now))
    c.commit()
    c.close()
    return token, exp

def verify_gateway_token(token: str, expected_sport_slug: str):
    try:
        p64, s64 = token.split(".", 1)
        payload_bytes = b64url_decode(p64)
        signature = b64url_decode(s64)

        if not hmac.compare_digest(signature, sign_gateway_payload(payload_bytes)):
            return None, "BAD_SIGNATURE"

        payload = json.loads(payload_bytes.decode())
        now = int(time.time())

        if int(payload.get("exp", 0)) < now:
            return None, "TOKEN_EXPIRED"

        c = conn()
        sport = c.execute(
            "SELECT id,slug,name FROM sports WHERE id=?",
            (payload["sid"],)
        ).fetchone()

        if not sport or sport["slug"] != expected_sport_slug:
            c.close()
            return None, "SPORT_MISMATCH"

        row = c.execute("""
          SELECT id,user_id,sport_id,nonce,expires_at,used_at
          FROM gateway_tokens
          WHERE nonce=? AND user_id=? AND sport_id=?
        """, (payload["nonce"], payload["uid"], payload["sid"])).fetchone()

        if not row:
            c.close()
            return None, "TOKEN_NOT_FOUND"
        if row["used_at"] is not None:
            c.close()
            return None, "TOKEN_ALREADY_USED"
        if row["expires_at"] < now:
            c.close()
            return None, "TOKEN_EXPIRED"

        user = c.execute("""
          SELECT id,username,email,display_name,status,email_verified
          FROM users
          WHERE id=? AND status='ACTIVE'
        """, (payload["uid"],)).fetchone()

        if not user:
            c.close()
            return None, "USER_NOT_FOUND"

        membership = c.execute("""
          SELECT id,role
          FROM user_sport_memberships
          WHERE user_id=? AND sport_id=?
        """, (payload["uid"], payload["sid"])).fetchone()

        if not membership:
            c.execute("""
              INSERT INTO user_sport_memberships(user_id,sport_id,role)
              VALUES(?,?,?)
            """, (payload["uid"], payload["sid"], "PLAYER"))
            membership = c.execute("""
              SELECT id,role
              FROM user_sport_memberships
              WHERE user_id=? AND sport_id=?
            """, (payload["uid"], payload["sid"])).fetchone()

        c.execute(
            "UPDATE gateway_tokens SET used_at=? WHERE id=?",
            (now, row["id"])
        )
        c.commit()

        linked = c.execute("""
          SELECT external_user_id,external_username,sport_role
          FROM sport_account_links
          WHERE user_id=? AND sport_id=?
        """,(payload["uid"],payload["sid"])).fetchone()

        result = {
            "user": dict(user),
            "sport": {
                "id": sport["id"],
                "slug": sport["slug"],
                "name": sport["name"]
            },
            "membership": dict(membership),
            "elite_user_id": user["id"],
            "external_account": dict(linked) if linked else None
        }
        c.close()
        return result, None
    except Exception:
        return None, "INVALID_TOKEN"



def create_external_link_ticket(user_id, sport_id, ttl_seconds=300):
    payload={
        "typ":"external-link",
        "uid":int(user_id),
        "sid":int(sport_id),
        "exp":int(time.time())+int(ttl_seconds),
        "nonce":secrets.token_urlsafe(16)
    }
    raw=json.dumps(payload,separators=(",",":"),sort_keys=True).encode("utf-8")
    sig=hmac.new(GATEWAY_SECRET.encode("utf-8"),raw,hashlib.sha256).digest()
    return b64url(raw)+"."+b64url(sig)

def verify_external_link_ticket(ticket):
    try:
        p64,s64=ticket.split(".",1)
        raw=b64url_decode(p64)
        sig=b64url_decode(s64)
        expected=hmac.new(GATEWAY_SECRET.encode("utf-8"),raw,hashlib.sha256).digest()
        if not hmac.compare_digest(sig,expected):
            return None,"BAD_LINK_TICKET"
        payload=json.loads(raw.decode("utf-8"))
        if payload.get("typ")!="external-link":
            return None,"BAD_LINK_TICKET"
        if int(payload.get("exp",0))<int(time.time()):
            return None,"LINK_TICKET_EXPIRED"
        return payload,None
    except Exception:
        return None,"BAD_LINK_TICKET"

def link_sport_account(user_id, sport_slug, external_user_id, external_username=None, sport_role="PLAYER"):
    c = conn()
    sport = c.execute("SELECT id FROM sports WHERE slug=?", (sport_slug,)).fetchone()
    if not sport:
        c.close()
        return None, "SPORT_NOT_FOUND"

    try:
        c.execute("""
          INSERT INTO sport_account_links(
            user_id,sport_id,external_user_id,external_username,sport_role,last_synced_at
          )
          VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
          ON CONFLICT(user_id,sport_id) DO UPDATE SET
            external_user_id=excluded.external_user_id,
            external_username=excluded.external_username,
            sport_role=excluded.sport_role,
            last_synced_at=CURRENT_TIMESTAMP
        """,(user_id,sport["id"],str(external_user_id),external_username,sport_role))

        c.execute("""
          INSERT INTO user_sport_memberships(user_id,sport_id,role,last_active_at)
          VALUES(?,?,?,CURRENT_TIMESTAMP)
          ON CONFLICT(user_id,sport_id) DO UPDATE SET
            role=excluded.role,
            last_active_at=CURRENT_TIMESTAMP
        """,(user_id,sport["id"],sport_role))

        c.commit()
        row = c.execute("""
          SELECT sal.*,s.slug,s.name
          FROM sport_account_links sal
          JOIN sports s ON s.id=sal.sport_id
          WHERE sal.user_id=? AND sal.sport_id=?
        """,(user_id,sport["id"])).fetchone()
        c.close()
        return dict(row), None
    except sqlite3.IntegrityError:
        c.close()
        return None, "EXTERNAL_ACCOUNT_ALREADY_LINKED"

def get_sport_link(user_id, sport_slug):
    return one("""
      SELECT sal.id,sal.external_user_id,sal.external_username,sal.sport_role,
             sal.linked_at,sal.last_synced_at,s.slug,s.name
      FROM sport_account_links sal
      JOIN sports s ON s.id=sal.sport_id
      WHERE sal.user_id=? AND s.slug=?
    """,(user_id,sport_slug))


def init_community_schema():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS friendships(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      requester_id INTEGER NOT NULL,
      addressee_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK(requester_id <> addressee_id),
      UNIQUE(requester_id,addressee_id),
      FOREIGN KEY(requester_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(addressee_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS conversations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_type TEXT NOT NULL DEFAULT 'DM',
      sport_id INTEGER,
      title TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS conversation_members(
      conversation_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_read_at TEXT,
      PRIMARY KEY(conversation_id,user_id),
      FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_id INTEGER NOT NULL,
      sender_id INTEGER NOT NULL,
      body TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      edited_at TEXT,
      deleted_at TEXT,
      FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
      FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      notification_type TEXT NOT NULL,
      title TEXT NOT NULL,
      body TEXT,
      action_path TEXT,
      is_read INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS user_blocks(
      blocker_id INTEGER NOT NULL,
      blocked_id INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(blocker_id,blocked_id),
      CHECK(blocker_id <> blocked_id),
      FOREIGN KEY(blocker_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(blocked_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS reports(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      reporter_id INTEGER NOT NULL,
      target_user_id INTEGER,
      target_message_id INTEGER,
      reason TEXT NOT NULL,
      details TEXT,
      status TEXT NOT NULL DEFAULT 'OPEN',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(reporter_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(target_user_id) REFERENCES users(id) ON DELETE SET NULL,
      FOREIGN KEY(target_message_id) REFERENCES messages(id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_notifications_user
      ON notifications(user_id,is_read,created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_messages_conversation
      ON messages(conversation_id,created_at DESC);
    """)
    c.commit()
    c.close()

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def new_session(user_id):
    raw = secrets.token_urlsafe(32)
    now = int(time.time())
    c = conn()
    c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    c.execute(
        "INSERT INTO sessions(user_id,token_hash,created_at,expires_at) VALUES(?,?,?,?)",
        (user_id, token_hash(raw), now, now + SESSION_TTL_SECONDS)
    )
    c.commit()
    c.close()
    return raw

def session_user(token):
    if not token:
        return None
    now = int(time.time())
    c = conn()
    r = c.execute("""
      SELECT u.id,u.username,u.email,u.display_name,u.legacy_points,u.status,u.email_verified
      FROM sessions s
      JOIN users u ON u.id=s.user_id
      WHERE s.token_hash=? AND s.expires_at>? AND u.status IN ('ACTIVE','EMAIL_UNVERIFIED')
    """,(token_hash(token),now)).fetchone()
    c.close()
    return dict(r) if r else None

def delete_session(token):
    if not token:
        return
    c = conn()
    c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
    c.commit()
    c.close()

def rows(sql, args=()):
    c = conn()
    out = [dict(r) for r in c.execute(sql,args).fetchall()]
    c.close()
    return out

def one(sql, args=()):
    c = conn()
    r = c.execute(sql,args).fetchone()
    c.close()
    return dict(r) if r else None

class Handler(BaseHTTPRequestHandler):
    def session_cookie_header(self,token,max_age=SESSION_TTL_SECONDS):
        secure="; Secure" if APP_ENV=="production" else ""
        return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}"

    def csrf_cookie_header(self,token,max_age=SESSION_TTL_SECONDS):
        secure="; Secure" if APP_ENV=="production" else ""
        return f"{CSRF_COOKIE}={token}; Path=/; SameSite=Lax; Max-Age={max_age}{secure}"

    def auth_cookie_headers(self,token):
        csrf=secrets.token_urlsafe(24)
        return [
            ("Set-Cookie",self.session_cookie_header(token)),
            ("Set-Cookie",self.csrf_cookie_header(csrf))
        ]

    def read_json(self):
        length = int(self.headers.get("Content-Length","0") or "0")
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def cookies(self):
        out = {}
        raw = self.headers.get("Cookie","")
        for part in raw.split(";"):
            if "=" in part:
                k,v = part.strip().split("=",1)
                out[k] = v
        return out

    def current_user(self):
        return session_user(self.cookies().get(SESSION_COOKIE))

    def require_user(self):
        u = self.current_user()
        if not u:
            self.send_json({"error":"AUTH_REQUIRED"},401)
            return None
        return u

    def require_verified_user(self):
        u = self.require_user()
        if not u:
            return None
        if not u.get("email_verified"):
            self.send_json({"error":"EMAIL_VERIFICATION_REQUIRED"},403)
            return None
        if not has_current_legal_acceptance(u["id"]):
            self.send_json({"error":"LEGAL_ACCEPTANCE_REQUIRED"},403)
            return None
        return u

    def send_json(self, data, status=200, extra_headers=None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        if extra_headers:
            for k,v in extra_headers.items():
                self.send_header(k,v)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        ext = path.suffix.lower()
        ctype = {
            ".html":"text/html; charset=utf-8",
            ".css":"text/css; charset=utf-8",
            ".js":"application/javascript; charset=utf-8",
            ".json":"application/json; charset=utf-8",
            ".svg":"image/svg+xml; charset=utf-8",
            ".png":"image/png",
            ".jpg":"image/jpeg",
            ".jpeg":"image/jpeg",
            ".webp":"image/webp",
            ".ico":"image/x-icon"
        }.get(ext,"application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        p = urlparse(self.path).path
        if not validate_csrf(self,p):
            return self.send_json({"error":"CSRF_FAILED"},403)
        body = self.read_json()

        if p == "/api/auth/register":
            if not rate_limit_check(self,"REGISTER"):
                return self.send_json({"error":"RATE_LIMITED"},429)
            username = (body.get("username") or "").strip().lower()
            email = (body.get("email") or "").strip().lower()
            display_name = (body.get("display_name") or username).strip()
            password = body.get("password") or ""
            invite_code = (body.get("invite_code") or "").strip()
            legal_ok = all(bool(body.get(k)) for k in (
                "accept_terms","accept_privacy","accept_community_rules"
            ))

            if not PUBLIC_REGISTRATION and not invite_code:
                return self.send_json({"error":"INVITE_REQUIRED"},403)
            if not legal_ok:
                return self.send_json({"error":"LEGAL_ACCEPTANCE_REQUIRED"},400)
            if not re.fullmatch(r"[a-z0-9_-]{3,24}", username):
                return self.send_json({"error":"INVALID_USERNAME"},400)
            if "@" not in email or len(email) > 200:
                return self.send_json({"error":"INVALID_EMAIL"},400)
            if len(password) < 10:
                return self.send_json({"error":"PASSWORD_TOO_SHORT"},400)
            if len(display_name) < 2 or len(display_name) > 50:
                return self.send_json({"error":"INVALID_DISPLAY_NAME"},400)

            invite = None
            if invite_code:
                now = int(time.time())
                invite = one("""SELECT id,email_normalized,expires_at,redeemed_at
                                FROM invitations
                                WHERE invite_code_hash=?
                                LIMIT 1""",(token_hash(invite_code),))
                if not invite or invite["redeemed_at"] or (invite["expires_at"] and invite["expires_at"] <= now):
                    return self.send_json({"error":"INVALID_INVITE"},403)
                if invite["email_normalized"] and invite["email_normalized"] != email:
                    return self.send_json({"error":"INVITE_EMAIL_MISMATCH"},403)

            c = conn()
            try:
                cur = c.execute("""
                  INSERT INTO users(username,email,display_name,password_hash,legacy_points,status,email_verified)
                  VALUES(?,?,?,?,0,'EMAIL_UNVERIFIED',0)
                """,(username,email,display_name,password_hash(password)))
                uid = cur.lastrowid
                c.commit()
            except sqlite3.IntegrityError:
                c.close()
                return self.send_json({"error":"USERNAME_OR_EMAIL_TAKEN"},409)
            c.close()

            accept_current_legal(uid)

            if invite:
                c = conn()
                c.execute("""UPDATE invitations SET redeemed_by_user_id=?,redeemed_at=?
                             WHERE id=?""",(uid,int(time.time()),invite["id"]))
                c.commit()
                c.close()

            verify_token = issue_account_token(uid,"email_verification_tokens",VERIFY_TTL_SECONDS)
            send_transactional_email(uid,email,"VERIFY_EMAIL","Verify your Elite Sports account",verify_token)
            security_event(uid,"REGISTER",{"username":username})

            token = new_session(uid)
            response = {
                "ok":True,
                "verification_required":True,
                "user":{"id":uid,"username":username,"display_name":display_name,"email_verified":0}
            }
            if APP_ENV != "production":
                response["dev_verification_token"] = verify_token

            return self.send_json(
                response,201,
                self.auth_cookie_headers(token)
            )

        if p == "/api/auth/verify-email":
            raw = (body.get("token") or "").strip()
            uid = consume_account_token(raw,"email_verification_tokens")
            if not uid:
                return self.send_json({"error":"INVALID_OR_EXPIRED_TOKEN"},400)
            c = conn()
            c.execute("UPDATE users SET email_verified=1,status='ACTIVE' WHERE id=?",(uid,))
            c.commit(); c.close()
            security_event(uid,"EMAIL_VERIFIED")
            return self.send_json({"ok":True,"email_verified":True})

        if p == "/api/auth/resend-verification":
            user = self.require_user()
            if user and not rate_limit_check(self,"VERIFY_RESEND",str(user["id"])):
                return self.send_json({"error":"RATE_LIMITED"},429)
            if not user:
                return
            if user.get("email_verified"):
                return self.send_json({"ok":True,"already_verified":True})
            raw = issue_account_token(user["id"],"email_verification_tokens",VERIFY_TTL_SECONDS)
            send_transactional_email(user["id"],user["email"],"VERIFY_EMAIL","Verify your Elite Sports account",raw)
            security_event(user["id"],"EMAIL_VERIFICATION_RESENT")
            data={"ok":True}
            if APP_ENV != "production":
                data["dev_verification_token"]=raw
            return self.send_json(data)

        if p == "/api/auth/request-password-reset":
            identity = (body.get("identity") or "").strip().lower()
            if not rate_limit_check(self,"RESET_REQUEST",identity):
                return self.send_json({"ok":True,"message":"If that account exists, reset instructions have been sent."})
            user = one("""SELECT id,email FROM users
                          WHERE lower(email)=? OR lower(username)=?
                          LIMIT 1""",(identity,identity))
            if user:
                raw = issue_account_token(user["id"],"password_reset_tokens",RESET_TTL_SECONDS)
                send_transactional_email(user["id"],user["email"],"PASSWORD_RESET","Reset your Elite Sports password",raw)
                security_event(user["id"],"PASSWORD_RESET_REQUESTED")
            return self.send_json({"ok":True,"message":"If that account exists, reset instructions have been sent."})

        if p == "/api/auth/reset-password":
            raw = (body.get("token") or "").strip()
            password = body.get("password") or ""
            if len(password) < 10:
                return self.send_json({"error":"PASSWORD_TOO_SHORT"},400)
            uid = consume_account_token(raw,"password_reset_tokens")
            if not uid:
                return self.send_json({"error":"INVALID_OR_EXPIRED_TOKEN"},400)
            c = conn()
            c.execute("UPDATE users SET password_hash=? WHERE id=?",(password_hash(password),uid))
            c.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
            c.commit(); c.close()
            security_event(uid,"PASSWORD_RESET_COMPLETED")
            return self.send_json(
                {"ok":True,"sessions_revoked":True},
                200,
                [("Set-Cookie",self.session_cookie_header("",0)),("Set-Cookie",self.csrf_cookie_header("",0))]
            )

        if p == "/api/auth/login":
            identity = (body.get("identity") or "").strip().lower()
            if not rate_limit_check(self,"LOGIN",identity):
                return self.send_json({"error":"RATE_LIMITED"},429)
            password = body.get("password") or ""
            c = conn()
            r = c.execute("""
              SELECT id,username,email,display_name,password_hash,status,email_verified
              FROM users
              WHERE lower(username)=? OR lower(email)=?
              LIMIT 1
            """,(identity,identity)).fetchone()
            c.close()

            valid_status = r and r["status"] in {"ACTIVE","EMAIL_UNVERIFIED"}
            if not r or not valid_status or not password_verify(password,r["password_hash"] or ""):
                if r:
                    security_event(r["id"],"LOGIN_FAILURE")
                return self.send_json({"error":"INVALID_CREDENTIALS"},401)

            security_event(r["id"],"LOGIN_SUCCESS")
            token = new_session(r["id"])
            return self.send_json(
                {"ok":True,"verification_required":not bool(r["email_verified"]),
                 "user":{"id":r["id"],"username":r["username"],"display_name":r["display_name"],
                         "email_verified":r["email_verified"]}},
                200,
                self.auth_cookie_headers(token)
            )

        if p == "/api/integrations/baseball/link":
            user = self.require_user()
            if not user:
                return

            external_user_id = str(body.get("external_user_id") or "").strip()
            external_username = (body.get("external_username") or "").strip() or None
            role = (body.get("role") or "PLAYER").strip().upper()

            if not external_user_id:
                return self.send_json({"error":"MISSING_EXTERNAL_USER_ID"},400)
            if role not in {"PLAYER","COACH","COMMISSIONER"}:
                return self.send_json({"error":"INVALID_ROLE"},400)

            link, err = link_sport_account(
                user["id"], "baseball", external_user_id, external_username, role
            )
            if err:
                return self.send_json({"error":err},409)

            return self.send_json({"ok":True,"link":link})

        if p == "/api/community/friend-request":
            user = self.require_user()
            if not user:
                return
            username = (body.get("username") or "").strip().lower()
            other = one("SELECT id,username,display_name FROM users WHERE lower(username)=? AND status='ACTIVE'",(username,))
            if not other or other["id"]==user["id"]:
                return self.send_json({"error":"USER_NOT_FOUND"},404)
            blocked = one("""SELECT 1 ok FROM user_blocks
                             WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)""",
                          (user["id"],other["id"],other["id"],user["id"]))
            if blocked:
                return self.send_json({"error":"INTERACTION_UNAVAILABLE"},403)
            c=conn()
            try:
                c.execute("""INSERT INTO friendships(requester_id,addressee_id,status)
                             VALUES(?,?,'PENDING')""",(user["id"],other["id"]))
                c.execute("""INSERT INTO notifications(user_id,notification_type,title,body,action_path)
                             VALUES(?,?,?,?,?)""",
                          (other["id"],"FRIEND_REQUEST","New friend request",
                           f'{user["display_name"]} sent you a friend request.',
                           f'/profile.html?u={user["username"]}'))
                c.commit()
            except sqlite3.IntegrityError:
                c.close()
                return self.send_json({"error":"REQUEST_ALREADY_EXISTS"},409)
            c.close()
            return self.send_json({"ok":True})

        if p == "/api/community/friend-respond":
            user = self.require_user()
            if not user:
                return
            username=(body.get("username") or "").strip().lower()
            action=(body.get("action") or "").strip().upper()
            if action not in {"ACCEPT","DECLINE"}:
                return self.send_json({"error":"INVALID_ACTION"},400)
            other=one("SELECT id,username,display_name FROM users WHERE lower(username)=?",(username,))
            if not other:
                return self.send_json({"error":"USER_NOT_FOUND"},404)
            c=conn()
            req=c.execute("""SELECT id FROM friendships
                             WHERE requester_id=? AND addressee_id=? AND status='PENDING'""",
                          (other["id"],user["id"])).fetchone()
            if not req:
                c.close()
                return self.send_json({"error":"REQUEST_NOT_FOUND"},404)
            if action=="ACCEPT":
                c.execute("UPDATE friendships SET status='ACCEPTED',updated_at=CURRENT_TIMESTAMP WHERE id=?",(req["id"],))
                c.execute("""INSERT INTO notifications(user_id,notification_type,title,body,action_path)
                             VALUES(?,?,?,?,?)""",
                          (other["id"],"FRIEND_ACCEPTED","Friend request accepted",
                           f'{user["display_name"]} accepted your friend request.',
                           f'/profile.html?u={user["username"]}'))
            else:
                c.execute("DELETE FROM friendships WHERE id=?",(req["id"],))
            c.commit(); c.close()
            return self.send_json({"ok":True,"action":action})

        if p == "/api/community/dm/start":
            user=self.require_user()
            if not user:
                return
            username=(body.get("username") or "").strip().lower()
            text=(body.get("message") or "").strip()
            other=one("SELECT id,username,display_name FROM users WHERE lower(username)=? AND status='ACTIVE'",(username,))
            if not other or other["id"]==user["id"]:
                return self.send_json({"error":"USER_NOT_FOUND"},404)
            if not text or len(text)>2000:
                return self.send_json({"error":"INVALID_MESSAGE"},400)
            blocked=one("""SELECT 1 ok FROM user_blocks
                           WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)""",
                        (user["id"],other["id"],other["id"],user["id"]))
            if blocked:
                return self.send_json({"error":"INTERACTION_UNAVAILABLE"},403)
            c=conn()
            existing=c.execute("""
              SELECT c.id FROM conversations c
              JOIN conversation_members a ON a.conversation_id=c.id AND a.user_id=?
              JOIN conversation_members b ON b.conversation_id=c.id AND b.user_id=?
              WHERE c.conversation_type='DM'
              LIMIT 1
            """,(user["id"],other["id"])).fetchone()
            if existing:
                cid=existing["id"]
            else:
                cur=c.execute("INSERT INTO conversations(conversation_type) VALUES('DM')")
                cid=cur.lastrowid
                c.executemany("INSERT INTO conversation_members(conversation_id,user_id) VALUES(?,?)",
                              [(cid,user["id"]),(cid,other["id"])])
            c.execute("INSERT INTO messages(conversation_id,sender_id,body) VALUES(?,?,?)",(cid,user["id"],text))
            c.execute("""INSERT INTO notifications(user_id,notification_type,title,body,action_path)
                         VALUES(?,?,?,?,?)""",
                      (other["id"],"MESSAGE",f'Message from {user["display_name"]}',
                       text[:120],f'/community.html?conversation={cid}'))
            c.commit(); c.close()
            return self.send_json({"ok":True,"conversation_id":cid})

        if p == "/api/community/block":
            user=self.require_user()
            if not user:
                return
            username=(body.get("username") or "").strip().lower()
            other=one("SELECT id FROM users WHERE lower(username)=?",(username,))
            if not other or other["id"]==user["id"]:
                return self.send_json({"error":"USER_NOT_FOUND"},404)
            c=conn()
            c.execute("INSERT OR IGNORE INTO user_blocks(blocker_id,blocked_id) VALUES(?,?)",(user["id"],other["id"]))
            c.execute("""DELETE FROM friendships
                         WHERE (requester_id=? AND addressee_id=?) OR (requester_id=? AND addressee_id=?)""",
                      (user["id"],other["id"],other["id"],user["id"]))
            c.commit(); c.close()
            return self.send_json({"ok":True})

        if p == "/api/gateway/consume":
            token = (body.get("token") or "").strip()
            sport_slug = (body.get("sport") or "").strip().lower()
            if not token or not sport_slug:
                return self.send_json({"error":"MISSING_GATEWAY_DATA"},400)

            data, err = verify_gateway_token(token, sport_slug)
            if err:
                return self.send_json({"error":err},401)

            if data.get("external_account") is None:
                data["link_ticket"]=create_external_link_ticket(
                    data["elite_user_id"],
                    data["sport"]["id"]
                )

            return self.send_json({"ok":True, **data})

        if p == "/api/gateway/link-external":
            ticket=(body.get("link_ticket") or "").strip()
            sport_slug=(body.get("sport") or "").strip().lower()
            external_user_id=str(body.get("external_user_id") or "").strip()
            external_username=(body.get("external_username") or "").strip() or None
            sport_role=(body.get("sport_role") or "PLAYER").strip().upper()

            if not ticket or not sport_slug or not external_user_id:
                return self.send_json({"error":"MISSING_LINK_DATA"},400)
            if sport_role not in {"PLAYER","COACH","COMMISSIONER"}:
                return self.send_json({"error":"INVALID_SPORT_ROLE"},400)

            payload,err=verify_external_link_ticket(ticket)
            if err:
                return self.send_json({"error":err},401)

            sport=one("SELECT id,slug FROM sports WHERE slug=?",(sport_slug,))
            if not sport or int(sport["id"])!=int(payload["sid"]):
                return self.send_json({"error":"SPORT_MISMATCH"},401)

            link,err=link_sport_account(
                int(payload["uid"]),
                sport_slug,
                external_user_id,
                external_username,
                sport_role
            )
            if err:
                return self.send_json({"error":err},409 if err=="EXTERNAL_ACCOUNT_ALREADY_LINKED" else 400)

            return self.send_json({"ok":True,"external_account":link})

        if p == "/api/auth/logout":
            token = self.cookies().get(SESSION_COOKIE)
            delete_session(token)
            return self.send_json(
                {"ok":True},
                200,
                [("Set-Cookie",self.session_cookie_header("",0)),("Set-Cookie",self.csrf_cookie_header("",0))]
            )

        self.send_error(404)

    def do_GET(self):
        p = urlparse(self.path).path

        if p == "/api/health":
            return self.send_json({
                "ok":True,
                "service":"elite-core",
                "gateway_external_linking":True
            })

        if p.startswith("/api/gateway/enter/"):
            user = self.require_verified_user()
            if not user:
                return

            sport_slug = p.split("/")[-1].strip().lower()
            sport = one("""
              SELECT id,slug,name,status,base_url
              FROM sports
              WHERE slug=? AND is_public=1
            """, (sport_slug,))

            if not sport:
                return self.send_json({"error":"SPORT_NOT_FOUND"},404)

            token, exp = create_gateway_token(user["id"], sport["id"])
            base_url = sport["base_url"] or "#"

            if base_url == "#":
                entry_url = f"/sport-demo.html?sport={sport_slug}&token={token}"
            else:
                sep = "&" if "?" in base_url else "?"
                entry_url = f"{base_url}{sep}elite_token={token}"

            return self.send_json({
                "ok": True,
                "sport": {
                    "slug": sport["slug"],
                    "name": sport["name"],
                    "status": sport["status"]
                },
                "expires_at": exp,
                "entry_url": entry_url
            })

        if p == "/api/auth/me":
            u = self.current_user()
            if not u:
                return self.send_json({"user":None})
            return self.send_json({"user":u})

        if p == "/api/account/readiness":
            u = self.current_user()
            if not u:
                return self.send_json({"user":None})
            return self.send_json({
                "user":{
                    "id":u["id"],"username":u["username"],"display_name":u["display_name"],
                    "email_verified":bool(u["email_verified"]),"status":u["status"]
                },
                "legal_accepted":has_current_legal_acceptance(u["id"]),
                "sport_entry_ready":bool(u["email_verified"]) and has_current_legal_acceptance(u["id"])
            })

        if p == "/api/dev/email-outbox":
            if APP_ENV == "production":
                return self.send_json({"error":"NOT_FOUND"},404)
            u = self.require_user()
            if not u:
                return
            data = rows("""SELECT id,email,email_type,subject,token,created_at
                           FROM dev_email_outbox
                           WHERE user_id=?
                           ORDER BY id DESC LIMIT 20""",(u["id"],))
            return self.send_json({"messages":data})

        if p == "/api/integrations/baseball/status":
            user = self.require_user()
            if not user:
                return
            link = get_sport_link(user["id"],"baseball")
            return self.send_json({"connected":bool(link),"link":link})

        if p == "/api/integrations/baseball/bootstrap":
            user = self.require_user()
            if not user:
                return

            link = get_sport_link(user["id"],"baseball")
            if not link:
                return self.send_json({"connected":False,"needs_link":True})

            career = one("""
              SELECT c.id,c.external_career_id,c.display_name,c.team_name,c.role_name,
                     c.season_label,c.status
              FROM careers c
              JOIN sports s ON s.id=c.sport_id
              WHERE c.user_id=? AND s.slug='baseball'
              ORDER BY c.id DESC
              LIMIT 1
            """,(user["id"],))

            return self.send_json({
                "connected":True,
                "elite_user":{
                    "id":user["id"],
                    "username":user["username"],
                    "display_name":user["display_name"]
                },
                "baseball_account":link,
                "career":career
            })

        if p.startswith("/api/public/profile/"):
            username = p.split("/")[-1].strip().lower()
            profile_user = one("""
              SELECT id,username,display_name,legacy_points,created_at
              FROM users
              WHERE lower(username)=? AND status='ACTIVE'
            """,(username,))
            if not profile_user:
                return self.send_json({"error":"PROFILE_NOT_FOUND"},404)

            settings = one("""
              SELECT bio,banner_label,featured_sport_slug,public_profile,show_activity
              FROM profile_settings
              WHERE user_id=?
            """,(profile_user["id"],))

            if settings and not settings["public_profile"]:
                return self.send_json({"error":"PROFILE_PRIVATE"},403)

            passports = rows("""
              SELECT cp.id,cp.external_career_id,cp.athlete_name,cp.organization_name,
                     cp.role_name,cp.current_season,cp.career_status,cp.headline,
                     cp.profile_path,cp.started_at,cp.retired_at,
                     s.slug sport_slug,s.name sport_name,s.icon
              FROM career_passports cp
              JOIN sports s ON s.id=cp.sport_id
              WHERE cp.user_id=?
              ORDER BY CASE cp.career_status WHEN 'ACTIVE' THEN 0 ELSE 1 END,s.sort_order
            """,(profile_user["id"],))

            for pp in passports:
                pp["stats"] = rows("""
                  SELECT stat_label,stat_value
                  FROM passport_stats
                  WHERE passport_id=?
                  ORDER BY sort_order,id
                """,(pp["id"],))

            honors = rows("""
              SELECT h.honor_type,h.title,h.season_label,h.event_label,h.awarded_at,
                     h.is_major,s.slug sport_slug,s.name sport_name,s.icon
              FROM honors h
              JOIN sports s ON s.id=h.sport_id
              WHERE h.user_id=?
              ORDER BY h.is_major DESC,h.awarded_at DESC,h.id DESC
            """,(profile_user["id"],))

            activities = []
            if not settings or settings["show_activity"]:
                activities = rows("""
                  SELECT af.activity_type,af.title,af.description,af.occurred_at,
                         s.slug sport_slug,s.name sport_name,s.icon
                  FROM activity_feed af
                  LEFT JOIN sports s ON s.id=af.sport_id
                  WHERE af.user_id=? AND af.visibility='PUBLIC'
                  ORDER BY af.occurred_at DESC,af.id DESC
                  LIMIT 30
                """,(profile_user["id"],))

            return self.send_json({
              "profile":{
                "username":profile_user["username"],
                "display_name":profile_user["display_name"],
                "legacy_points":profile_user["legacy_points"],
                "member_since":profile_user["created_at"],
                "bio":settings["bio"] if settings else None,
                "banner_label":settings["banner_label"] if settings else None,
                "featured_sport_slug":settings["featured_sport_slug"] if settings else None
              },
              "passports":passports,
              "honors":honors,
              "activity":activities
            })

        if p == "/api/activity/me":
            user = self.require_user()
            if not user:
                return
            data = rows("""
              SELECT af.id,af.activity_type,af.title,af.description,af.external_ref,
                     af.visibility,af.occurred_at,s.slug sport_slug,s.name sport_name,s.icon
              FROM activity_feed af
              LEFT JOIN sports s ON s.id=af.sport_id
              WHERE af.user_id=?
              ORDER BY af.occurred_at DESC,af.id DESC
              LIMIT 100
            """,(user["id"],))
            return self.send_json({"activity":data})

        if p == "/api/activity/global":
            data = rows("""
              SELECT af.id,af.activity_type,af.title,af.description,af.occurred_at,
                     u.username,u.display_name,s.slug sport_slug,s.name sport_name,s.icon
              FROM activity_feed af
              JOIN users u ON u.id=af.user_id
              LEFT JOIN sports s ON s.id=af.sport_id
              WHERE af.visibility='PUBLIC' AND u.status='ACTIVE'
              ORDER BY af.occurred_at DESC,af.id DESC
              LIMIT 50
            """)
            return self.send_json({"activity":data})

        if p == "/api/community/friends":
            user = self.require_user()
            if not user:
                return
            data = rows("""
              SELECT u.username,u.display_name,f.status,
                     CASE WHEN f.requester_id=? THEN 'OUTGOING' ELSE 'INCOMING' END direction
              FROM friendships f
              JOIN users u ON u.id=CASE WHEN f.requester_id=? THEN f.addressee_id ELSE f.requester_id END
              WHERE (f.requester_id=? OR f.addressee_id=?)
              ORDER BY f.updated_at DESC
            """,(user["id"],user["id"],user["id"],user["id"]))
            return self.send_json({"friends":data})

        if p == "/api/community/notifications":
            user = self.require_user()
            if not user:
                return
            data = rows("""
              SELECT id,notification_type,title,body,action_path,is_read,created_at
              FROM notifications WHERE user_id=?
              ORDER BY is_read ASC,created_at DESC,id DESC LIMIT 50
            """,(user["id"],))
            return self.send_json({"notifications":data})

        if p == "/api/community/conversations":
            user = self.require_user()
            if not user:
                return
            data = rows("""
              SELECT c.id,c.conversation_type,c.title,c.created_at,s.slug sport_slug,s.name sport_name,
                     (SELECT body FROM messages m WHERE m.conversation_id=c.id AND m.deleted_at IS NULL ORDER BY m.id DESC LIMIT 1) last_message,
                     (SELECT created_at FROM messages m WHERE m.conversation_id=c.id AND m.deleted_at IS NULL ORDER BY m.id DESC LIMIT 1) last_message_at
              FROM conversations c
              JOIN conversation_members cm ON cm.conversation_id=c.id
              LEFT JOIN sports s ON s.id=c.sport_id
              WHERE cm.user_id=?
              ORDER BY COALESCE(last_message_at,c.created_at) DESC
            """,(user["id"],))
            return self.send_json({"conversations":data})

        if p == "/api/dashboard":
            user = self.require_user()
            if not user:
                return

            sports = rows("""
              SELECT s.id,s.slug,s.name,s.icon,s.status,s.base_url,s.sort_order,
                     usm.role membership_role,usm.last_active_at
              FROM sports s
              LEFT JOIN user_sport_memberships usm
                ON usm.sport_id=s.id AND usm.user_id=?
              WHERE s.is_public=1
              ORDER BY CASE WHEN usm.user_id IS NULL THEN 1 ELSE 0 END,s.sort_order
            """,(user["id"],))

            careers = rows("""
              SELECT c.id,c.display_name,c.team_name,c.role_name,c.season_label,c.status,
                     s.slug sport_slug,s.name sport_name,s.icon
              FROM careers c
              JOIN sports s ON s.id=c.sport_id
              WHERE c.user_id=?
              ORDER BY CASE c.status WHEN 'ACTIVE' THEN 0 ELSE 1 END,c.id DESC
            """,(user["id"],))

            unread = one("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND is_read=0",(user["id"],))
            friend_count = one("""
              SELECT COUNT(*) n FROM friendships
              WHERE status='ACCEPTED' AND (requester_id=? OR addressee_id=?)
            """,(user["id"],user["id"]))

            notifications = rows("""
              SELECT id,notification_type,title,body,action_path,created_at
              FROM notifications
              WHERE user_id=? AND is_read=0
              ORDER BY created_at DESC,id DESC LIMIT 5
            """,(user["id"],))

            news = rows("""
              SELECT hn.id,hn.title,hn.summary,hn.created_at,s.slug sport_slug,s.name sport_name,s.icon
              FROM hub_news hn
              LEFT JOIN sports s ON s.id=hn.sport_id
              ORDER BY hn.created_at DESC,hn.id DESC LIMIT 8
            """)

            activity = rows("""
              SELECT af.title,af.description,af.occurred_at,s.slug sport_slug,s.name sport_name,s.icon,
                     u.username,u.display_name
              FROM activity_feed af
              JOIN users u ON u.id=af.user_id
              LEFT JOIN sports s ON s.id=af.sport_id
              WHERE af.visibility='PUBLIC'
              ORDER BY af.occurred_at DESC,af.id DESC LIMIT 8
            """)

            honors = rows("""
              SELECT h.title,h.season_label,h.is_major,s.slug sport_slug,s.name sport_name,s.icon
              FROM honors h
              JOIN sports s ON s.id=h.sport_id
              WHERE h.user_id=?
              ORDER BY h.is_major DESC,h.awarded_at DESC,h.id DESC LIMIT 4
            """,(user["id"],))

            return self.send_json({
              "me":{
                "username":user["username"],
                "display_name":user["display_name"],
                "legacy_points":user["legacy_points"]
              },
              "counts":{
                "unread_notifications":unread["n"] if unread else 0,
                "friends":friend_count["n"] if friend_count else 0,
                "active_careers":sum(1 for c in careers if c["status"]=="ACTIVE")
              },
              "sports":sports,
              "careers":careers,
              "notifications":notifications,
              "news":news,
              "activity":activity,
              "honors":honors
            })

        if p.startswith("/api/hub/"):
            user = self.require_user()
            if not user:
                return

            if p == "/api/hub/me":
                totals = one("""
                  SELECT
                    SUM(CASE WHEN event_type='CHAMPIONSHIP' THEN 1 ELSE 0 END) championships,
                    SUM(CASE WHEN event_type='MAJOR_AWARD' THEN 1 ELSE 0 END) major_awards,
                    SUM(CASE WHEN event_type='SEASON_COMPLETED' THEN 1 ELSE 0 END) seasons_played
                  FROM legacy_events WHERE user_id=?
                """,(user["id"],)) or {}

                sports_entered = one("""
                  SELECT COUNT(DISTINCT sport_id) sports_entered
                  FROM user_sport_memberships WHERE user_id=?
                """,(user["id"],))["sports_entered"]

                level = max(1, user["legacy_points"] // 250 + 1)
                return self.send_json({
                    "user":user,
                    "legacy":{
                        "level":level,
                        "points":user["legacy_points"],
                        "next_level_at":level*250,
                        "championships":totals.get("championships") or 0,
                        "major_awards":totals.get("major_awards") or 0,
                        "seasons_played":totals.get("seasons_played") or 0,
                        "sports_entered":sports_entered
                    }
                })

            if p == "/api/hub/sports":
                data = rows("""
                  SELECT id,slug,name,short_name,status,icon,base_url,sort_order,is_public
                  FROM sports WHERE is_public=1
                  ORDER BY sort_order,name
                """)
                return self.send_json({"sports":data})

            if p == "/api/hub/careers":
                data = rows("""
                  SELECT c.id,c.external_career_id,c.display_name,c.team_name,c.role_name,
                         c.season_label,c.status,s.slug sport_slug,s.name sport_name,s.icon
                  FROM careers c
                  JOIN sports s ON s.id=c.sport_id
                  WHERE c.user_id=? AND c.status='ACTIVE'
                  ORDER BY c.id
                """,(user["id"],))
                return self.send_json({"careers":data})

            if p == "/api/hub/news":
                data = rows("""
                  SELECT n.id,n.headline,n.summary,n.priority,n.published_at,n.is_featured,
                         s.slug sport_slug,s.name sport_name,s.icon
                  FROM hub_news n
                  LEFT JOIN sports s ON s.id=n.sport_id
                  ORDER BY n.is_featured DESC,n.priority DESC,n.published_at DESC
                  LIMIT 12
                """)
                return self.send_json({"news":data})

            if p == "/api/hub/legacy":
                data = rows("""
                  SELECT l.id,l.event_type,l.title,l.points,l.created_at,
                         s.name sport_name,s.icon
                  FROM legacy_events l
                  LEFT JOIN sports s ON s.id=l.sport_id
                  WHERE l.user_id=?
                  ORDER BY l.id DESC
                  LIMIT 50
                """,(user["id"],))
                return self.send_json({"events":data})

        # Root-level frontend assets. Keep the public surface deliberately limited
        # to known web file types and reject nested paths/path traversal.
        if p == "/":
            return self.send_file(ROOT / "index.html")

        asset_name = p.lstrip("/")
        allowed_exts = {".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
        if asset_name and "/" not in asset_name and "\\" not in asset_name and ".." not in asset_name:
            asset_path = ROOT / asset_name
            if asset_path.suffix.lower() in allowed_exts and asset_path.exists() and asset_path.is_file():
                return self.send_file(asset_path)

        self.send_error(404)

    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options","DENY")
        if APP_ENV=="production":
            self.send_header("Strict-Transport-Security","max-age=31536000; includeSubDomains")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    init_db()
    init_community_schema()
    init_security_schema()
    print(f"Elite Core running on http://localhost:{PORT}")
    if os.environ.get("ELITE_SEED_DEMO","0") == "1":
        print("Development demo account seeded.")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
