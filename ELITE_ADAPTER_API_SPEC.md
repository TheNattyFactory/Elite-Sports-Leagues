# Elite Core Adapter API v1

## POST /api/adapter/publish

Headers:
- `Authorization: Bearer <sport-adapter-key>`
- `Content-Type: application/json`

Body:

```json
{
  "publication_type": "EVENT_UPSERT",
  "external_id": "ebl-game-4421-live",
  "payload": {
    "external_event_id": "game-4421",
    "event_type": "GAME",
    "title": "Atlanta Firebirds vs Chicago",
    "event_status": "LIVE",
    "primary_label": "Atlanta 2 - Chicago 1",
    "secondary_label": "Top 5th",
    "detail_label": "LIVE",
    "action_label": "Gamecast",
    "action_path": "/game/4421"
  }
}
```

## Response

```json
{
  "ok": true,
  "accepted": true,
  "duplicate": false
}
```

## POST /api/adapter/notify

This may eventually be a convenience wrapper over `publication_type=NOTIFY`.

Example:

```json
{
  "external_id": "ebl-game-4421-start",
  "audience": {
    "type": "EVENT_FOLLOWERS",
    "external_event_id": "game-4421"
  },
  "title": "First pitch",
  "body": "Atlanta vs Chicago is now live.",
  "action_path": "/game/4421",
  "preference_key": "EVENT_START"
}
```

## Notification preference keys

Recommended initial keys:
- `EVENT_START`
- `EVENT_FINAL`
- `SCHEDULE_CHANGE`
- `CAREER_MILESTONE`
- `AWARD`
- `CHAMPIONSHIP`
- `DIRECT_MESSAGE`
- `FRIEND_REQUEST`

Users should be able to disable sport/event notifications without disabling essential account/security notices.
