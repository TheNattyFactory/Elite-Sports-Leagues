"""
Drop-in helper for the existing Elite Baseball League server.

Recommended route:
GET /auth/elite?elite_token=...
"""
import json
import urllib.request

ELITE_CORE_URL = "https://YOUR-ELITE-HUB-DOMAIN"

def consume_elite_token(token):
    payload = json.dumps({
        "sport": "baseball",
        "token": token
    }).encode("utf-8")

    req = urllib.request.Request(
        ELITE_CORE_URL + "/api/gateway/consume",
        data=payload,
        headers={"Content-Type":"application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def resolve_ebl_user(token):
    data = consume_elite_token(token)

    if not data.get("ok"):
        raise ValueError("Elite gateway rejected token")

    if data.get("sport",{}).get("slug") != "baseball":
        raise ValueError("Wrong sport token")

    external = data.get("external_account")
    if not external:
        raise ValueError("Elite user is not linked to an EBL account")

    return {
        "elite_user_id": data["elite_user_id"],
        "ebl_user_id": external["external_user_id"],
        "ebl_username": external.get("external_username"),
        "role": external.get("sport_role","PLAYER")
    }
