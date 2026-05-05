import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Blueprint, redirect, request, session, url_for

from backend.utils.github_oauth import exchange_code_for_token, save_token
from backend.utils.github_oauth import get_valid_access_token

oauth_bp = Blueprint("oauth", __name__, url_prefix="/api/oauth")


def _login_secret_ok() -> bool:
    required = (os.getenv("GITHUB_OAUTH_LOGIN_SECRET") or "").strip()
    if not required:
        return True

    provided = (request.args.get("secret") or "").strip()
    if not provided:
        provided = (request.headers.get("X-GitHub-OAuth-Login-Secret") or "").strip()

    return secrets.compare_digest(provided, required)


def _require_login_secret():
    if _login_secret_ok():
        return None
    return (
        "OAuth login is disabled without the correct secret.\n",
        403,
        {"Content-Type": "text/plain"},
    )


def _whoami_login(access_token: str) -> str:
    resp = requests.get(
        "https://api.github.com/user",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    return (data.get("login") or "").strip()


@oauth_bp.route("/login")
def login():
    denied = _require_login_secret()
    if denied:
        return denied

    client_id = (os.getenv("GITHUB_OAUTH_CLIENT_ID") or "").strip()
    if not client_id:
        return (
            "Missing `GITHUB_OAUTH_CLIENT_ID`. Set it in your .env and retry.",
            500,
        )

    redirect_uri = (os.getenv("GITHUB_OAUTH_REDIRECT_URI") or "").strip()
    if not redirect_uri:
        redirect_uri = url_for("oauth.callback", _external=True)

    # Optional scopes. For Sponsors GraphQL, many users report it works with minimal/empty scopes.
    # If you run into permission issues for org queries, try adding: read:org
    scope = (os.getenv("GITHUB_OAUTH_SCOPES") or "").strip()

    state = secrets.token_urlsafe(32)
    session["github_oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if scope:
        params["scope"] = scope

    return redirect("https://github.com/login/oauth/authorize?" + urlencode(params))


@oauth_bp.route("/status")
def status():
    """Debug/status endpoint: shows who the saved token belongs to.

    Does not return the token.
    """
    denied = _require_login_secret()
    if denied:
        return denied

    allowed_login = (os.getenv("GITHUB_OAUTH_ALLOWED_LOGIN") or "").strip()

    try:
        access_token = get_valid_access_token()
    except Exception as exc:
        return (
            "No saved GitHub OAuth token is available for this server.\n"
            "Run /api/oauth/login to generate one (or set PAT / GITHUB_TOKEN).\n\n"
            f"Error: {exc}\n",
            404,
            {"Content-Type": "text/plain"},
        )

    try:
        actual_login = _whoami_login(access_token)
    except Exception as exc:
        return (
            "A token exists, but identity validation via GET /user failed.\n\n"
            f"Error: {exc}\n",
            500,
            {"Content-Type": "text/plain"},
        )

    ok = True
    if allowed_login and actual_login.lower() != allowed_login.lower():
        ok = False

    return (
        "GitHub OAuth token status\n\n"
        f"Authorized GitHub login: {actual_login or '(unknown)'}\n"
        f"Allowed login: {allowed_login or '(not set)'}\n"
        f"Allowed login match: {'yes' if ok else 'NO'}\n",
        200,
        {"Content-Type": "text/plain"},
    )


@oauth_bp.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    expected = session.get("github_oauth_state")
    if not expected or not state or state != expected:
        return ("Invalid OAuth state. Please retry /api/oauth/login.", 400)

    if not code:
        return ("Missing OAuth code. Please retry /api/oauth/login.", 400)

    redirect_uri = (os.getenv("GITHUB_OAUTH_REDIRECT_URI") or "").strip()
    if not redirect_uri:
        redirect_uri = url_for("oauth.callback", _external=True)

    token = exchange_code_for_token(code=code, redirect_uri=redirect_uri)

    # Optional safety: ensure only an expected GitHub user can set this server's token cache.
    # This matters if /api/oauth/login is reachable publicly.
    allowed_login = (os.getenv("GITHUB_OAUTH_ALLOWED_LOGIN") or "").strip()
    try:
        actual_login = _whoami_login(token.access_token)
    except Exception as exc:
        return (
            "OAuth authorization succeeded, but failed to validate token identity via /user.\n\n"
            f"Error: {exc}\n",
            500,
            {"Content-Type": "text/plain"},
        )

    if allowed_login and actual_login.lower() != allowed_login.lower():
        return (
            "OAuth authorization refused.\n\n"
            f"This server only accepts tokens for GitHub user: {allowed_login}\n"
            f"But you authorized as: {actual_login or '(unknown)'}\n\n"
            "Sign into the correct GitHub account and retry /api/oauth/login.\n",
            403,
            {"Content-Type": "text/plain"},
        )

    path = save_token(token)

    # Clear state so refreshes don't accidentally re-use it
    session.pop("github_oauth_state", None)

    expires = (
        token.expires_at.isoformat() if token.expires_at else "(no expiry returned)"
    )
    refresh_present = "yes" if token.refresh_token else "no"

    return (
        "OAuth authorization successful.\n\n"
        f"Authorized GitHub login: {actual_login or '(unknown)'}\n"
        f"Saved token to: {path}\n"
        f"Access token expires_at: {expires}\n"
        f"Refresh token present: {refresh_present}\n\n"
        "You can now run the ingest worker without setting PAT.\n",
        200,
        {"Content-Type": "text/plain"},
    )
