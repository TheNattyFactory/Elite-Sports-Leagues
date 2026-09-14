# Elite Adapter → Core Notification Flow v1

## Example: EBL game starts

```text
EBL SIMULATOR
    │
    │ GAME STATE → LIVE
    ▼
EBL ELITE ADAPTER
    │
    │ signed EVENT_UPSERT
    ▼
ELITE CORE
    │
    ├── update Event Card
    ├── record publication
    └── resolve followers / involved Elite users
             │
             ▼
      NOTIFICATION ENGINE
             │
       ┌─────┴─────┐
       ▼           ▼
    IN-APP      FUTURE EMAIL/PUSH
```

EBL remains authoritative for the game itself. Core does not simulate an inning or decide whether the game is live.

## Example: Racing result

Racing publishes:
- race FINAL
- finishing position
- career activity
- honor if applicable

Core can then:
- update the Hub card
- update Career Passport headline information
- create Trophy Room history
- notify followers

## Example: Golf tee-time change

Golf publishes a NOTIFY request for event followers. Core checks notification preferences before delivery.

## Deduplication
Every publication has a sport-scoped `external_id`. Repeated delivery of the same publication must not create duplicate trophies, events, or notifications.

## Production safety
Adapter endpoints should use:
- HTTPS only
- hashed/rotatable service credentials
- request timestamps
- nonce/replay protection
- rate limits
- payload size limits
- schema validation
- audit logs
