# SpicyPy

## Run

```sh
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

Open the app, paste your SpicyChat **refresh token**, and choose **Masuk ke SpicyPy**.
No private password or shared SpicyChat account is required. Each browser uses its
own account. Never paste a token into a public issue, chat, or untrusted deployment.

## Deployment

Set a strong, stable `SECRET_KEY` in the deployment environment. On Vercel this is
required; use the same key across workers and keep it secret. Rotate the key to
invalidate all SpicyPy sessions. Existing sessions must log in again after this update.
`PRIVATE_APP_PASSWORD` and `SPICYCHAT_REFRESH_TOKEN` are no longer used.

Tokens are exchanged server-side and stored in an authenticated, encrypted,
HttpOnly, SameSite=Lax cookie (Secure on Vercel). Use HTTPS in production.
Sessions last up to 30 days of inactivity; the provider can expire or revoke tokens
earlier. Access tokens refresh before expiry and provider-issued rotated refresh
tokens replace the old token. Logout clears this browser's cookie; it does not
revoke tokens at SpicyChat. No tokens are stored in localStorage or the repository.
Oversized sessions are rejected rather than emitting cookies browsers cannot save.

The login page is accessible to anyone who can reach the deployment, but each user
must provide their own valid SpicyChat token. The old shared-account password gate
has been removed.

## Verification

```sh
python -m unittest discover -s tests -v
```

Tests mock SpicyChat; live token exchange requires a valid account token and is not
covered by these checks.
