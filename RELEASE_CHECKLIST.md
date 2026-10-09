# Production rollout checklist

- [ ] Current ESL/EBL GitHub commits fetched, reviewed, and tagged for rollback.
- [ ] Backups of live SQLite volumes obtained/validated.
- [ ] Combined server patches merged with current code without replacing newer gameplay.
- [ ] Production release keeps `ELITE_SEED_DEMO=0` and the EBL publisher disabled until read-only verification passes.
- [ ] Security secrets staged and reviewed; not committed to Git.
- [ ] Private profiles, suspended accounts, and demo events excluded from public network feeds.
- [ ] Signed score, award, signing, retirement, replay rejection tested in staging.
- [ ] EBL account link proof: wrong user, replay, expiry, and double-link rejected.
- [ ] Hub landing, registration, login, existing EBL account CTA and connect pages verified on mobile.
- [ ] EBL startup, roster, gameplay, avatar source and recruitment checked with unchanged real data.
- [ ] Enable publisher with a separate Railway change only after both environments pass.
- [ ] Confirm fresh EBL event appears exactly once on ESL; observe logs and revert if not.
