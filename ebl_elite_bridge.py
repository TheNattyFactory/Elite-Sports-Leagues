"""
Elite Baseball League <-> Elite Core authentication bridge.

Designed for the current EBL server architecture:
- sqlite conn()
- users + user_security tables
- persistent_sessions
- new_session(c,user_id,handler)
- pwhash(...)
- H handler class using self.out(...)

The bridge never moves baseball simulation data into Core.
"""
import json, os, secrets
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ELITE_CORE_URL=os.environ.get("ELITE_CORE_URL","http://127.0.0.1:8080").rstrip("/")
ELITE_AUTH_MODE=os.environ.get("ELITE_AUTH_MODE","hybrid").lower()

def _elite_post(path,payload):
    req=Request(
        ELITE_CORE_URL+path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type":"application/json",
            "User-Agent":"EBL-Elite-Bridge/1.0"
        }
    )
    try:
        with urlopen(req,timeout=12) as resp:
            raw=resp.read().decode("utf-8")
            return json.loads(raw or "{}"),resp.status
    except HTTPError as exc:
        raw=exc.read().decode("utf-8",errors="replace")
        try:data=json.loads(raw)
        except Exception:data={"error":"ELITE_CORE_HTTP_ERROR","detail":raw[:300]}
        return data,exc.code
    except URLError as exc:
        return {"error":"ELITE_CORE_UNAVAILABLE","detail":str(exc.reason)},503
    except Exception as exc:
        return {"error":"ELITE_CORE_UNAVAILABLE","detail":str(exc)},503

def elite_core_status():
    try:
        req=Request(
            ELITE_CORE_URL+"/api/health",
            method="GET",
            headers={"User-Agent":"EBL-Elite-Bridge/1.1"}
        )
        with urlopen(req,timeout=5) as resp:
            data=json.loads(resp.read().decode("utf-8") or "{}")
            return {
                "reachable":200 <= resp.status < 300,
                "status":resp.status,
                "service":data.get("service")
            }
    except Exception as exc:
        return {
            "reachable":False,
            "error":str(exc)[:160]
        }

def consume_elite_token(token):
    return _elite_post("/api/gateway/consume",{
        "token":token,
        "sport":"baseball"
    })

def bind_external_account(link_ticket,ebl_user):
    return _elite_post("/api/gateway/link-external",{
        "link_ticket":link_ticket,
        "sport":"baseball",
        "external_user_id":str(ebl_user["id"]),
        "external_username":ebl_user["username"],
        "sport_role":ebl_user["role"]
    })

def find_existing_ebl_user_by_verified_email(c,email):
    if not email:return None
    return c.execute("""
      SELECT u.id,u.username,u.role
      FROM users u
      JOIN user_security s ON s.user_id=u.id
      WHERE lower(s.email)=lower(?) AND s.email_verified=1
      LIMIT 1
    """,(email,)).fetchone()

def load_ebl_user(c,user_id):
    return c.execute(
        "SELECT id,username,role FROM users WHERE id=?",
        (int(user_id),)
    ).fetchone()

def unique_ebl_username(c,preferred):
    base="".join(ch for ch in (preferred or "elite-player").lower()
                 if ch.isalnum() or ch in "_-")[:24] or "elite-player"
    name=base
    n=2
    while c.execute("SELECT 1 FROM users WHERE username=?",(name,)).fetchone():
        suffix=f"-{n}"
        name=(base[:24-len(suffix)]+suffix)
        n+=1
    return name

def create_ebl_user_for_elite(c,elite_user,pwhash):
    username=unique_ebl_username(c,elite_user.get("username"))
    unusable=secrets.token_urlsafe(48)
    c.execute(
        "INSERT INTO users(username,password_hash,role) VALUES(?,?,'PLAYER')",
        (username,pwhash(unusable))
    )
    uid=c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
    email=(elite_user.get("email") or "").strip().lower()
    c.execute("""INSERT OR REPLACE INTO user_security(
      user_id,email,email_verified,email_token_hash,email_token_expires,
      reset_token_hash,reset_token_expires,created_at,updated_at
    ) VALUES(?,?,1,NULL,NULL,NULL,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
      (uid,email or None))
    return load_ebl_user(c,uid)

def resolve_ebl_user(c,consume_data,pwhash):
    external=consume_data.get("external_account")
    if external:
        found=load_ebl_user(c,external["external_user_id"])
        if not found:
            return None,"LINKED_EBL_USER_NOT_FOUND",False
        return found,None,False

    elite_user=consume_data["user"]

    # SAFETY RULE: automatically claim an existing EBL account only via verified email.
    found=find_existing_ebl_user_by_verified_email(c,elite_user.get("email"))
    created=False
    if not found:
        found=create_ebl_user_for_elite(c,elite_user,pwhash)
        created=True
    return found,None,created

def complete_elite_handoff(handler,token,conn,pwhash,new_session):
    data,status=consume_elite_token(token)
    if status!=200 or not data.get("ok"):
        return None,data.get("error","ELITE_HANDOFF_FAILED"),status

    c=conn()
    try:
        ebl_user,err,created=resolve_ebl_user(c,data,pwhash)
        if err:
            c.close()
            return None,err,409

        if data.get("external_account") is None:
            link_ticket=data.get("link_ticket")
            if not link_ticket:
                c.close()
                return None,"MISSING_LINK_TICKET",502
            link_data,link_status=bind_external_account(link_ticket,ebl_user)
            if link_status!=200 or not link_data.get("ok"):
                c.close()
                return None,link_data.get("error","ELITE_LINK_FAILED"),link_status

        sid,_=new_session(c,ebl_user["id"],handler)
        c.commit()
        result={
            "sid":sid,
            "ebl_user":{
                "id":ebl_user["id"],
                "username":ebl_user["username"],
                "role":ebl_user["role"]
            },
            "elite_user_id":data["elite_user_id"],
            "created_ebl_user":created
        }
        c.close()
        return result,None,200
    except Exception:
        try:c.rollback();c.close()
        except Exception:pass
        return None,"ELITE_HANDOFF_FAILED",500
