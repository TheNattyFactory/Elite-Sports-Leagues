# ESL v2.5 local test results — October 9, 2026

All tests below were run against patched **saved Drive snapshots** in fresh local temporary SQLite databases, never live user data.

- PASS combined ESL + EBL patch application and Python compile
- PASS JavaScript syntax and markup for homepage, network, hall-of-fame, EBL connection and ESL account-linking pages
- PASS /api/network/home, /api/network/status and /api/network/hall-of-fame behavior; nine worlds with no fabricated feed or honors
- PASS no private, suspended, demo, or unofficial induction data in public network pages
- PASS signed report ingestion; bad signature/timestamp, duplicate and demo-event rejection
- PASS EBL publishing: preexisting history skipped; signing, award, league news, final, retirement delivered once
- PASS account proof: correct owner, wrong user, replay, expiry, tampered proof, wrong secret, EBL role, verified ESL requirements
- PASS HTTP route integration: legacy arbitrary external IDs and former insecure gateway link endpoint blocked
- PASS all checked static files served HTTP 200 in local harness

**Not yet tested:** latest GitHub commits, production Railway deploys, live EBL database, live account linking, actual cross-domain SSO. EBL existing gameplay/regression suite must run before release.
