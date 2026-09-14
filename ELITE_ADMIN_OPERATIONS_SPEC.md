# Elite Administration & Operations v1

## Purpose
The master admin layer governs Elite Core and ecosystem-level operations.

It does **not** replace sport commissioner tools.

## Elite Core Admin responsibilities
- users and account status
- global announcements
- moderation reports
- blocks and abuse handling
- sport registry
- adapter/service health
- incident tracking
- system audit log
- notification delivery health
- global community controls
- public profile moderation
- shop/platform-wide settings later

## Sport Commissioner responsibilities
A sport's commissioner still owns:
- league seasons
- rosters
- schedules
- playoffs
- sport awards
- simulation advancement
- sport-specific rules
- sport-specific discipline if appropriate

## Admin roles
Recommended:
- `SUPER_ADMIN`
- `PLATFORM_ADMIN`
- `MODERATOR`
- `SUPPORT`
- `SPORT_OPERATOR`
- `READ_ONLY_AUDITOR`

`SPORT_OPERATOR` may be scoped to one sport.

## Separation rule
A platform admin should not accidentally gain baseball commissioner powers just because they can see EBL health.

Likewise, an EBL commissioner should not automatically gain platform moderation access.
