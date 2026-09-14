# Elite Core v11 — Production Hardening

Implemented:
- CSRF double-submit protection for cookie-authenticated writes
- HttpOnly session cookie + readable CSRF cookie
- Secure cookie flag in production
- login/register/reset/resend rate limits
- privacy-preserving IP hashing for rate-limit buckets
- Resend-compatible transactional email delivery
- development email outbox fallback
- security-event logging for failed email delivery
- baseline security headers including HSTS in production

Production environment:
- `ELITE_ENV=production`
- `ELITE_APP_BASE_URL=https://<core-domain>`
- `ELITE_EMAIL_PROVIDER=resend`
- `RESEND_API_KEY=<secret>`
- `ELITE_EMAIL_FROM=Elite Sports <verified-address>`
- `ELITE_IP_HASH_SECRET=<long-random-secret>`

Closed alpha:
- `ELITE_PUBLIC_REGISTRATION=0`

Notes:
- only trust X-Forwarded-For behind your controlled proxy/load balancer
- if Core runs multiple application instances, move rate limiting to a shared store
- admin MFA and session/device management remain recommended
