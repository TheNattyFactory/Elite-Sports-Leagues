# EBL Automated Elite Migration Runbook

Put these files beside the live EBL `server.py`:
- `ebl_elite_bridge.py`
- `patch_ebl_for_elite.py`
- `verify_ebl_elite_patch.py`
- `rollback_ebl_elite_patch.py`

## Apply

```bash
python patch_ebl_for_elite.py server.py
```

The patcher:
1. compiles the existing server first
2. makes a timestamped backup
3. patches only known anchors
4. compiles the patched server and bridge
5. restores the backup automatically if validation fails
6. can be run again safely

## Verify

```bash
python verify_ebl_elite_patch.py server.py
```

## EBL Railway

```text
ELITE_CORE_URL=https://<elite-core-domain>
ELITE_AUTH_MODE=hybrid
```

## Elite Core Railway

```text
ELITE_BASEBALL_URL=https://elite-baseball.com/auth/elite
```

## Smoke test

Open:

```text
/api/elite/status
```

Then:
1. sign into Elite Core
2. verify the Elite email
3. click Enter Baseball
4. confirm EBL opens already authenticated
5. verify `/api/me` returns the expected EBL user
6. confirm COACH / COMMISSIONER roles remain unchanged where applicable
7. sign out and re-enter from Core to prove the permanent link is reused

## Cutover

After hybrid migration is proven:

```text
ELITE_AUTH_MODE=core_only
```

The old EBL registration/login/recovery endpoints then return `USE_ELITE_CORE_AUTH`.

## Rollback

```bash
python rollback_ebl_elite_patch.py server.py
```

The patcher never modifies `ebl.db`.
