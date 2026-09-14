# EBL → Elite Core: First Real Sport Integration

This bridge is designed around the EBL backend currently preserved in the project File Library. That build already has:
- persistent `sid` sessions
- `new_session(...)`
- PLAYER / COACH / COMMISSIONER roles
- `user_security`
- verified emails
- suspensions
- Resend email support

The Elite bridge keeps all of those Baseball systems.

## 1. Put `ebl_elite_bridge.py` beside EBL `server.py`

## 2. Add this import near the top of EBL server.py

```python
from ebl_elite_bridge import complete_elite_handoff, ELITE_AUTH_MODE
```

Change the urllib import only if needed; the bridge has its own HTTP imports.

## 3. Import `parse_qs`

Current EBL has:

```python
from urllib.parse import urlparse
```

Change to:

```python
from urllib.parse import urlparse, parse_qs
```

## 4. Add the Elite handoff route in `H.do_GET`

Place it BEFORE the `if p.startswith("/api/")` branch:

```python
if p=="/auth/elite":
    qs=parse_qs(urlparse(self.path).query)
    token=(qs.get("elite_token") or [""])[0].strip()

    if not token:
        return self.out({"error":"MISSING_ELITE_TOKEN"},400)

    result,err,status=complete_elite_handoff(
        self,
        token,
        conn,
        pwhash,
        new_session
    )

    if err:
        return self.out({"error":err},status)

    self.send_response(302)
    self.send_header("Location","/")
    self.send_header(
        "Set-Cookie",
        f"sid={result['sid']}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000"
    )
    self.end_headers()
    return
```

## 5. Keep old EBL login during migration

Start with:

```text
ELITE_AUTH_MODE=hybrid
```

That lets old direct EBL login coexist while we confirm linking.

After existing users are linked and Elite Core is stable:

```text
ELITE_AUTH_MODE=core_only
```

Then the EBL `/api/register`, `/api/login`, and EBL password-recovery UI can be retired in favor of Elite Core.

## 6. Configure EBL Railway

```text
ELITE_CORE_URL=https://YOUR-ELITE-CORE-DOMAIN
ELITE_AUTH_MODE=hybrid
```

## 7. Configure Elite Core Railway

```text
ELITE_BASEBALL_URL=https://elite-baseball.com/auth/elite
```

Core will generate:

```text
https://elite-baseball.com/auth/elite?elite_token=<one-time-token>
```

## Existing-account migration rule

When an Elite user enters EBL for the first time:

1. If Core already has an EBL link → use that EBL user ID.
2. Otherwise EBL checks its own **verified email**.
3. Verified email match → preserve that exact EBL user, role, player, team, stats, history.
4. No verified email match → create a new local EBL PLAYER identity.
5. EBL sends the resulting local user ID back to Core using a five-minute signed link ticket.
6. Later entries go directly to the linked EBL account.

**Username alone is never enough to automatically claim an old EBL account.**

## Commissioner / Coach preservation

Because the bridge links to the existing `users.id`, the existing EBL `role` remains authoritative. A linked commissioner stays COMMISSIONER. A linked coach stays COACH.

## Baseball ownership boundary

Elite Core owns:
- Elite login
- email verification
- password recovery
- cross-sport identity
- gateway
- global community/legacy/profile

EBL continues to own:
- EBL user role
- players
- teams
- roster slots
- contracts
- XP
- games
- Gamecast
- standings
- playoffs
- Baseball awards
- commissioner actions
