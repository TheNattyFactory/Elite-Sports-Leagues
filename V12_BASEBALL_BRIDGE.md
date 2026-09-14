# Elite Core v12 — Baseball Bridge

## New runtime behavior
`POST /api/gateway/consume`
- consumes the existing one-time sport gateway token
- if Baseball is already linked, returns the external EBL account
- if not linked, returns a five-minute signed `link_ticket`

`POST /api/gateway/link-external`
- accepts the signed link ticket
- binds Elite user ↔ existing/new EBL user
- records EBL username and EBL role
- cannot bind a different sport than the ticket was issued for

## Important v11 correction
Gateway service endpoints are CSRF-exempt because they use signed one-time gateway credentials and are called server-to-server. Browser account/community write endpoints remain CSRF protected.

## Baseball URL
Set:
`ELITE_BASEBALL_URL=https://elite-baseball.com/auth/elite`

No database edit is required after deployment.
