# ESL Phase 2.5 — combined launch release candidate (NOT LIVE)

This ZIP combines v2.3 verified ESL Sports Network with v2.4 secure EBL account linking and adds a prominent existing-player connection CTA. It was built and locally tested on saved Drive code, not current production GitHub revisions.

## Contents
- `ESL/` = frontend assets and the two new integration modules. Preserve existing repo pages/assets not shown here.
- `EBL/` = two additive Python integration modules and new `/static/connect-elite.html`.
- `patches/ESL_server_combined.patch` and `patches/EBL_server_combined.patch` = consolidated diffs replacing the separate v2.3/v2.4 patches. Do not apply earlier patches on top of these.
- `tests/` = regression suites for network, signed reports, linking, and route authorization.

## Merge (do not paste old whole server.py!)
1. Back up both production databases/volumes, confirm current deployed GitHub commit and clean checkout.
2. Create a feature branch for each repo. Copy the respective source files into the same repo, preserving unmentioned files.
3. Run `git apply --check` with that repo's combined patch on current GitHub `server.py`. If it fails, manually merge only the intended code and review the modern source instead of replacing it with the old source.
4. Compile server and new modules; run these tests on temporary, NON-PRODUCTION SQLite DBs plus existing EBL test suite.
5. Deploy ESL first to staging/preview, confirm `/api/network/home`, `/api/network/status`, `/api/network/hall-of-fame`, `/link-baseball.html`, existing auth/signup, and CSS/JS on phone.
6. Deploy EBL with publishing OFF. Confirm existing user sign-in, verified EBL account proof endpoint, training, signing, season actions, avatars, and EBL game simulation.
7. Confirm the staged Railway secrets match: ESL `ELITE_NETWORK_BASEBALL_SECRET` and `ELITE_EBL_ACCOUNT_LINK_SECRET`; EBL `EBL_ESL_NETWORK_SECRET`, `EBL_ELITE_ACCOUNT_LINK_SECRET`, `EBL_ESL_CORE_URL=https://elitesportsleagues.com`, `EBL_ESL_PUBLISH_ENABLED=0`. Never put values in Git or frontend.
8. Use dedicated verified test accounts to test connection. Only turn EBL news publishing ON after server authentication, ingestion and monitoring checks succeed. First send starts at current cursor and skips test/Genesis historical backlog.
9. Roll back code commits/variable toggles for faults; **never reset any player DB**.

## Honest scope
- Existing EBL and ESL users keep their separate accounts and passwords; this provides verified account linking, not automatic single sign-on. No player, avatar, contract, or saved progression is moved to ESL.
- The signed league newsroom publishes confirmed events. Empty Hall of Fame stays empty until actual official inductions.
- Existing historic unverified links require a manual ownership audit; the migration cannot automatically prove which links were correct.
- `POST /api/gateway/link-external` is discontinued (410) because it previously allowed an unproven sports-account ID to be claimed. Review dependent racing or other sport workflows before releasing.
- The current GitHub EBL source has progressed beyond the provided Drive snapshot, so production GitHub review is REQUIRED; do not deploy this kit as an entire root directory.
