# Elite Core v10 Runtime Test Results

Tested against a temporary local server on an alternate port.

## Passed
- Registration: `201`
- New account state: email unverified
- Baseball gateway before verification: `403 EMAIL_VERIFICATION_REQUIRED`
- Email verification: `200`
- Baseball gateway after verification: `200`
- Password reset request: `200`
- Development reset delivery/token: available
- Password reset completion: `200`
- Existing sessions revoked on reset: yes
- Login with new password: `200`

## Important
Development email tokens are exposed only through the local development outbox. `ELITE_ENV=production` disables that route/behavior. A real transactional email adapter is still required for deployment.
