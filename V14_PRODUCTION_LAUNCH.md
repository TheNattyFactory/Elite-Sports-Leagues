# Elite Core v14 — Production Launch

Production fixes:
- `PORT` now reads Railway's `PORT`
- gateway signing secret now reads `ELITE_GATEWAY_SECRET`
- production refuses to boot with the development gateway secret
- `railway.toml` adds explicit start command, healthcheck, and restart policy

Required Railway variables:

```text
ELITE_ENV=production
ELITE_APP_BASE_URL=https://elitesportsleagues.com
ELITE_BASEBALL_URL=https://elite-baseball.com/auth/elite
ELITE_GATEWAY_SECRET=<strong random secret>
ELITE_IP_HASH_SECRET=<strong random secret>
ELITE_PUBLIC_REGISTRATION=0
ELITE_EMAIL_PROVIDER=development
```

Before opening registration, switch email to Resend and provide:

```text
ELITE_EMAIL_PROVIDER=resend
RESEND_API_KEY=<secret>
ELITE_EMAIL_FROM=Elite Sports <verified sender>
```
