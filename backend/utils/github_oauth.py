import json
import os
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

_TOKEN_REFRESH_BUFFER_SECONDS = 120


def _repo_root() -> Path:
    # backend/utils/github_oauth.py -> repo root is two parents up from backend/
    return Path(__file__).resolve().parents[2]


def _resolve_token_path() -> Path:
    raw = (os.getenv("GITHUB_OAUTH_TOKEN_PATH") or ".github-oauth-token.json").strip()
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    return (_repo_root() / p).resolve()


@dataclass
class OAuthToken:
    access_token: str
    expires_at: datetime | None
    refresh_token: str | None
    refresh_token_expires_at: datetime | None

    @staticmethod
    def from_dict(data: dict) -> "OAuthToken":
        def parse_dt(value: str | None) -> datetime | None:
            if not value:
                return None
            # stored as ISO 8601
            return datetime.fromisoformat(value)

        return OAuthToken(
            access_token=data.get("access_token") or "",
            expires_at=parse_dt(data.get("expires_at")),
            refresh_token=data.get("refresh_token"),
            refresh_token_expires_at=parse_dt(data.get("refresh_token_expires_at")),
        )

    def to_dict(self) -> dict:
        def dump_dt(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "access_token": self.access_token,
            "expires_at": dump_dt(self.expires_at),
            "refresh_token": self.refresh_token,
            "refresh_token_expires_at": dump_dt(self.refresh_token_expires_at),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


def load_token() -> OAuthToken | None:
    path = _resolve_token_path()
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return OAuthToken.from_dict(data)
    except Exception as exc:
        logging.error("Failed to load OAuth token file '%s': %s", path, exc)
        return None


def save_token(token: OAuthToken) -> Path:
    path = _resolve_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(token.to_dict(), fh, indent=2)

    os.replace(tmp, path)

    # best-effort: restrict permissions on unix-y systems
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

    return path


def _client_id_secret() -> tuple[str, str]:
    client_id = (os.getenv("GITHUB_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GITHUB_OAUTH_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "GitHub OAuth refresh requires `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET`."
        )
    return client_id, client_secret


def exchange_code_for_token(code: str, redirect_uri: str) -> OAuthToken:
    client_id, client_secret = _client_id_secret()

    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"OAuth token exchange failed: {data.get('error')}: {data.get('error_description') or data.get('error_uri')}"
        )

    access_token = data.get("access_token")
    expires_in = data.get("expires_in")
    refresh_token = data.get("refresh_token")
    refresh_token_expires_in = data.get("refresh_token_expires_in")

    if not access_token:
        raise RuntimeError(
            "OAuth token exchange succeeded but access_token was missing."
        )

    now = datetime.now(timezone.utc)
    expires_at = None
    if isinstance(expires_in, int):
        expires_at = now + timedelta(seconds=expires_in)

    refresh_expires_at = None
    if isinstance(refresh_token_expires_in, int):
        refresh_expires_at = now + timedelta(seconds=refresh_token_expires_in)

    return OAuthToken(
        access_token=access_token,
        expires_at=expires_at,
        refresh_token=refresh_token,
        refresh_token_expires_at=refresh_expires_at,
    )


def refresh_access_token(refresh_token: str) -> OAuthToken:
    client_id, client_secret = _client_id_secret()

    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"OAuth token refresh failed: {data.get('error')}: {data.get('error_description') or data.get('error_uri')}"
        )

    access_token = data.get("access_token")
    expires_in = data.get("expires_in")

    # GitHub may rotate refresh tokens; if present, use the new one.
    new_refresh_token = data.get("refresh_token")
    refresh_token_expires_in = data.get("refresh_token_expires_in")

    if not access_token:
        raise RuntimeError(
            "OAuth token refresh succeeded but access_token was missing."
        )

    now = datetime.now(timezone.utc)
    expires_at = None
    if isinstance(expires_in, int):
        expires_at = now + timedelta(seconds=expires_in)

    refresh_expires_at = None
    if isinstance(refresh_token_expires_in, int):
        refresh_expires_at = now + timedelta(seconds=refresh_token_expires_in)

    return OAuthToken(
        access_token=access_token,
        expires_at=expires_at,
        refresh_token=new_refresh_token or refresh_token,
        refresh_token_expires_at=refresh_expires_at,
    )


def _is_expiring_soon(expires_at: datetime | None) -> bool:
    if not expires_at:
        # Non-expiring token (or unknown expiry) -> treat as not expiring.
        return False
    now = datetime.now(timezone.utc)
    return expires_at <= now + timedelta(seconds=_TOKEN_REFRESH_BUFFER_SECONDS)


def get_valid_access_token() -> str:
    """Return a valid OAuth user access token, refreshing if needed.

    Requires that a token file exists (written by the /api/oauth/callback endpoint).
    """
    token = load_token()
    if not token or not token.access_token:
        raise RuntimeError(
            "No GitHub OAuth token found. Run the OAuth flow at /api/oauth/login to generate one, "
            "or set `PAT` / `GITHUB_TOKEN`."
        )

    if not _is_expiring_soon(token.expires_at):
        return token.access_token

    if not token.refresh_token:
        raise RuntimeError(
            "OAuth access token is expired/expiring and no refresh_token is available. "
            "Re-run the OAuth flow at /api/oauth/login to generate a new token, or set `PAT` / `GITHUB_TOKEN`."
        )

    refreshed = refresh_access_token(token.refresh_token)
    save_token(refreshed)
    return refreshed.access_token
