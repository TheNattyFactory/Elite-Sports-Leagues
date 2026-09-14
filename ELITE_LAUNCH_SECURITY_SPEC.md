# Elite Launch Security v1

## Required lifecycle
Register/invite → accept current legal docs → verify email → activate account → enter sports.

## Security rules
- Hash verification/reset tokens; never store raw tokens.
- Reset requests never reveal whether an email exists.
- Verification/reset tokens expire and are single-use.
- Successful password reset should revoke older sessions.
- Rate-limit login, registration, reset, verification resend, DMs, friend requests, reports, and adapter publishing.
- Production cookies: Secure, HttpOnly, appropriate SameSite; add CSRF protection for cookie-authenticated writes.
- Keep gateway secrets, adapter keys, email keys, database credentials, and session secrets outside source code.
- Log security-sensitive account events.
- Version Terms, Privacy, and Community Rules and retain acceptance timestamps.
- Platform suspension and sport discipline are separate systems.

## Account actions
WARNING, CHAT_RESTRICTED, PROFILE_RESTRICTED, SPORT_RESTRICTED, TEMP_SUSPENSION, SUSPENSION, BAN.
