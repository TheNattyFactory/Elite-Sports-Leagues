"""Issue short-lived account ownership proof only from an authenticated EBL session."""
import base64, hashlib, hmac, json, os, secrets, time

ISSUER="elite-baseball.com"
AUDIENCE="elitesportsleagues.com"
CONTEXT=b"ebl-elite-account-link-v1."

def _encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

def issue(user):
    secret=os.environ.get("EBL_ELITE_ACCOUNT_LINK_SECRET","")
    if len(secret)<32:
        raise RuntimeError("EBL account linking has not been configured")
    uid=int(user["id"])
    if uid<1:raise ValueError("invalid account")
    username=str(user["username"] or "")
    role=str(user.get("role") or "PLAYER").upper()
    if not (1<=len(username)<=64 and role in ("PLAYER","COACH","COMMISSIONER")):
        raise ValueError("invalid account")
    now=int(time.time())
    claims={"v":1,"iss":ISSUER,"aud":AUDIENCE,"uid":uid,"username":username,
            "role":role,"iat":now,"exp":now+180,"nonce":secrets.token_urlsafe(24)}
    body=json.dumps(claims,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")
    mac=hmac.new(secret.encode(),CONTEXT+body,hashlib.sha256).digest()
    return {"proof":_encode(body)+"."+_encode(mac),"expires_at":now+180}
