"""Verify an EBL account proof and atomically attach exactly one EBL identity to ESL."""
import base64, hashlib, hmac, json, os, re, sqlite3, time

ISSUER="elite-baseball.com"
AUDIENCE="elitesportsleagues.com"
CONTEXT=b"ebl-elite-account-link-v1."

def _decode(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+",value):
        raise ValueError("INVALID_LINK_PROOF")
    return base64.urlsafe_b64decode(value+"="*((-len(value))%4))

def verify(proof):
    secret=os.environ.get("ELITE_EBL_ACCOUNT_LINK_SECRET","")
    if len(secret)<32:
        return None,"LINK_NOT_CONFIGURED"
    if not isinstance(proof,str) or len(proof)>1800 or len(proof)<80 or proof.count(".")!=1:
        return None,"INVALID_LINK_PROOF"
    try:
        b64,mac64=proof.split(".")
        body=_decode(b64)
        mac=_decode(mac64)
        if len(body)>550 or len(mac)!=32:
            return None,"INVALID_LINK_PROOF"
        expected=hmac.new(secret.encode(),CONTEXT+body,hashlib.sha256).digest()
        if not hmac.compare_digest(mac,expected):
            return None,"INVALID_LINK_PROOF"
        claims=json.loads(body)
        now=int(time.time())
        if not isinstance(claims,dict) or claims.get("v")!=1 or claims.get("iss")!=ISSUER or claims.get("aud")!=AUDIENCE:
            return None,"INVALID_LINK_PROOF"
        iat=claims.get("iat");exp=claims.get("exp");uid=claims.get("uid")
        if type(iat)!=int or type(exp)!=int or type(uid)!=int or uid<1 or iat>now+30 or iat<now-300 or exp<=now or exp>iat+180:
            return None,"EXPIRED_OR_INVALID_LINK_PROOF"
        name=claims.get("username");role=claims.get("role");nonce=claims.get("nonce")
        if (not isinstance(name,str) or not 1<=len(name)<=64 or
            role not in ("PLAYER","COACH","COMMISSIONER") or
            not isinstance(nonce,str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,80}",nonce)):
            return None,"INVALID_LINK_PROOF"
        return claims,None
    except (ValueError,TypeError,KeyError,UnicodeError,OverflowError):
        return None,"INVALID_LINK_PROOF"

def link(conn_factory,elite_user_id,proof):
    claims,error=verify(proof)
    if error:return None,error
    c=conn_factory()
    try:
        c.execute("BEGIN IMMEDIATE")
        user=c.execute("SELECT status,email_verified FROM users WHERE id=?",(elite_user_id,)).fetchone()
        if not user or user["status"]!="ACTIVE" or not user["email_verified"]:
            c.rollback();return None,"ELITE_ACCOUNT_NOT_VERIFIED"
        sport=c.execute("SELECT id FROM sports WHERE slug='baseball'").fetchone()
        if not sport:
            c.rollback();return None,"SPORT_NOT_FOUND"
        sid=int(sport["id"]);ext_id=str(claims["uid"])
        existing=c.execute("SELECT external_user_id FROM sport_account_links WHERE user_id=? AND sport_id=?",(elite_user_id,sid)).fetchone()
        if existing and str(existing["external_user_id"])!=ext_id:
            c.rollback();return None,"ALREADY_LINKED_TO_DIFFERENT_EBL_ACCOUNT"
        owner=c.execute("SELECT user_id FROM sport_account_links WHERE sport_id=? AND external_user_id=?",(sid,ext_id)).fetchone()
        if owner and int(owner["user_id"])!=int(elite_user_id):
            c.rollback();return None,"EBL_ACCOUNT_ALREADY_CLAIMED"
        c.execute("""CREATE TABLE IF NOT EXISTS ebl_link_used_nonces(
             nonce_hash TEXT PRIMARY KEY,used_at INTEGER NOT NULL)""")
        # A successful proof lasts only 180 seconds; keep replay hashes one day.
        c.execute("DELETE FROM ebl_link_used_nonces WHERE used_at<?", (int(time.time())-86400,))
        nonce_hash=hashlib.sha256(claims["nonce"].encode()).hexdigest()
        try:
            c.execute("INSERT INTO ebl_link_used_nonces(nonce_hash,used_at) VALUES(?,?)",(nonce_hash,int(time.time())))
        except sqlite3.IntegrityError:
            c.rollback();return None,"LINK_PROOF_ALREADY_USED"
        if existing:
            c.execute("UPDATE sport_account_links SET external_username=?,sport_role=?,last_synced_at=CURRENT_TIMESTAMP WHERE user_id=? AND sport_id=?",
                      (claims["username"],claims["role"],elite_user_id,sid))
        else:
            c.execute("""INSERT INTO sport_account_links(user_id,sport_id,external_user_id,external_username,sport_role,last_synced_at)
              VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)""",
              (elite_user_id,sid,ext_id,claims["username"],claims["role"]))
        c.execute("""INSERT INTO user_sport_memberships(user_id,sport_id,role,last_active_at)
          VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,sport_id) DO UPDATE SET
          role=excluded.role,last_active_at=CURRENT_TIMESTAMP""",
          (elite_user_id,sid,claims["role"]))
        c.commit()
        return {"sport":"baseball","external_user_id":ext_id,"external_username":claims["username"],"sport_role":claims["role"]},None
    except sqlite3.IntegrityError:
        c.rollback();return None,"EBL_ACCOUNT_ALREADY_CLAIMED"
    finally:
        c.close()
