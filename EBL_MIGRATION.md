# EBL → Elite Core Migration Plan

## Preserve
- existing EBL user IDs
- usernames
- roles
- player IDs
- teams/franchises
- career history
- commissioner and coach permissions

## Existing user flow
1. Sign into Elite.
2. Link Elite `user_id` to existing EBL `user_id`.
3. Keep the original EBL account unchanged.
4. Store only the mapping in `sport_account_links`.
5. Future Hub entries authenticate through the Gateway.
6. EBL recreates its own normal session.

## New user flow
1. Create Elite account.
2. Enter Baseball.
3. EBL creates its own local user/player when necessary.
4. Link the new EBL ID back to Elite Core.

## Roles
- PLAYER → PLAYER
- COACH → COACH
- COMMISSIONER → COMMISSIONER

## Boundary
Elite Core should never become the Baseball simulation database.
It owns identity and cross-sport services.
EBL owns Baseball.
