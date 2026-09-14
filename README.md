# Elite Sports Hub + EBL Bridge MVP

This build makes Elite Baseball League the first real integration target.

## Added
- `sport_account_links`
- Elite ↔ EBL account mapping
- role mirroring
- Baseball status API
- Baseball bootstrap API
- Baseball linking API
- Gateway responses now include linked external accounts
- drop-in `ebl_elite_adapter.py`
- EBL migration plan
- browser integration guide

## Baseball APIs

### Status
`GET /api/integrations/baseball/status`

### Link existing EBL account
`POST /api/integrations/baseball/link`

```json
{
  "external_user_id": "123",
  "external_username": "tmoney",
  "role": "PLAYER"
}
```

### Bootstrap
`GET /api/integrations/baseball/bootstrap`

## Architecture rule

Elite Core owns:
- identity
- Hub
- cross-sport memberships
- Legacy
- shared services

Elite Baseball League owns:
- Baseball account authorization
- players and careers
- franchises
- rosters
- games
- standings
- contracts
- stats/history

## Next step
Patch the live EBL `server.py` with an `/auth/elite` route and point the Hub Baseball URL to the deployed EBL domain.



# Elite Core v2 — Career Passport Foundation

This extension formalizes the universal architecture.

## Added foundation
- Elite Sports Design Doctrine
- Universal Sport Contract v1
- Career Passport schema
- sport-defined headline-stat model
- universal honors / Trophy Room schema
- sport health registry
- Career Passport UI prototype

## Core rule
**Shared identity. Separate worlds. Connected legacy.**

Elite Core stores universal identity/history summaries. Each sport remains authoritative for its simulation, teams, schedules, attributes, statistics, progression, terminology, and visual experience.

## Intended v2 APIs
- `GET /api/passport/me`
- `GET /api/trophy-room/me`
- `GET /api/sports/status`

The next implementation step is for EBL to publish its real career summary through an adapter, replacing the prototype Passport data.


# Elite Core v3 — Public Identity Layer

Added:
- public Elite profiles
- profile settings/privacy foundation
- cross-sport activity/history feed
- global public activity endpoint
- Trophy Room presentation
- Career Passport + Trophy Room + History on one public page
- Elite Activity Contract v1
- Public Profile specification

Prototype profile:
`/profile.html?u=t-money`

New endpoints:
- `GET /api/public/profile/{username}`
- `GET /api/activity/me`
- `GET /api/activity/global`

This layer remains historical/social only. It does not affect competitive ratings or attributes.


# Elite Core v4 — Community Foundation

Added:
- cross-sport friend requests
- friend acceptance/decline
- shared DMs
- shared notifications
- conversation membership
- user blocking
- report schema
- Community UI
- Elite Community Contract v1

Prototype:
`/community.html`

New endpoints:
- `GET /api/community/friends`
- `GET /api/community/notifications`
- `GET /api/community/conversations`
- `POST /api/community/friend-request`
- `POST /api/community/friend-respond`
- `POST /api/community/dm/start`
- `POST /api/community/block`

Production still needs:
- rate limiting
- spam detection
- moderation tooling
- report-review endpoints
- notification read state endpoints
- message pagination/edit/delete
- CSRF protections


# Elite Core v5 — Living Hub

Added:
- personalized dashboard aggregation API
- personalized sport launcher
- Continue Career area
- Legacy/friends/notification counters
- Trophy Case preview
- cross-sport news
- Elite activity stream
- global ticker
- gateway-powered Enter buttons
- Living Hub design specification

Open:
`/dashboard.html`

API:
`GET /api/dashboard`

The next platform layer should be the universal Event Card contract so Baseball games, Racing weekends, MMA fight cards, Golf tournaments, Soccer fixtures, etc. can all publish upcoming/live/completed events to the Hub without losing their sport-specific identity.


# Elite Core v6 — Events & Live Presence

Added:
- Universal Event Card contract
- universal event schema
- event-follow schema
- Live & Upcoming UI prototype
- sport-specific event payload design
- Live Presence specification

The next implementation layer is adapter-driven event publishing and notifications: sports push LIVE/FINAL/schedule changes into Core while remaining fully authoritative for their own live simulation.


# Elite Core v7 — Adapter Publishing & Notifications

This build defines the service boundary between each independently deployed sport and Elite Core.

Added:
- trusted sport-adapter credential schema
- idempotent sport publication inbox
- notification preference schema
- notification delivery tracking
- Adapter Publication Contract v1
- Adapter API specification
- sport → Core notification flow
- Notification Center UI prototype

The key rule is now explicit:

**The sport creates the moment. Core connects the moment to the person.**

This keeps Baseball, Racing, Golf, MMA and every future sport independent while still giving the Hub live events, Career Passport updates, trophies, activity, and notifications.


# Elite Core v8 — Administration & Operations

Added:
- master administration data model
- admin role/scoping model
- global announcement schema
- system audit log
- incident tracking
- service-check history
- Admin & Operations UI prototype
- Operations Contract v1
- separation rules between platform admins and sport commissioners

Core rule:

**Platform admins govern the ecosystem. Sport commissioners govern competition.**

This avoids turning Elite Core into a giant commissioner panel while still providing one place to monitor users, moderation, service health, adapter status, incidents, and announcements.

Recommended next layer:
**Account & launch readiness** — email verification, password reset, rate limiting, audit/security events, legal acceptance, account status controls, and invite/onboarding flows.


# Elite Core v10 — Working Account Lifecycle

The security/account specifications are now partially implemented in the running Python Core. See `V10_RUNTIME_ACCOUNT_LIFECYCLE.md`.


# Elite Core v11 — Production Hardening

Working CSRF protection, production cookie hardening, rate limits, baseline security headers, and a Resend-compatible email adapter are now included.

# Elite Core v12 — Baseball: First Real Sport Bridge

The Core gateway can now securely bind an Elite identity to an existing or newly created EBL local user through a short-lived signed external-link ticket.

The included `ebl_elite_bridge.py` is built for the current EBL authentication/session architecture and preserves Baseball user IDs, roles, players, teams, seasons and statistics.


# Elite Core v13 — EBL Migration Toolkit

Added an automated EBL patcher, timestamped backup/rollback, syntax verification, Elite Core health checks, and hybrid-to-core-only cutover controls.
