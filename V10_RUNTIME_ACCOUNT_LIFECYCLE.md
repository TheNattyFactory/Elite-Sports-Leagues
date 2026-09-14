# Elite Core v10 — Runtime Account Lifecycle

## Implemented in server.py
- registration creates EMAIL_UNVERIFIED account
- current legal documents must be accepted
- verification tokens are hashed in SQLite
- development-only email outbox simulates transactional email
- email verification activates account
- resend verification invalidates prior unused token
- login supports unverified Core sessions
- sport gateway requires verified email + current legal acceptance
- password reset request does not disclose whether account exists
- reset tokens are hashed, expire in 30 minutes, and are single use
- successful reset revokes all sessions
- security-sensitive events are logged

## Development
Run normally:
`python server.py`

The verification page can read `/api/dev/email-outbox` for the signed-in user.

## Production
Set:
`ELITE_ENV=production`

In production the development outbox is disabled. Replace `queue_dev_email()` with a transactional email adapter such as Resend before inviting users.

For invite-only alpha:
`ELITE_PUBLIC_REGISTRATION=0`

## Still required before public launch
- transactional email provider
- request/IP rate limiting
- CSRF tokens for cookie-authenticated writes
- HTTPS Secure cookies
- production secret management
- session/device management UI
- real legal-document routes/content
- automated tests around abuse/security edge cases
