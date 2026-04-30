import requests
import time
import os
import logging
import threading
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv


load_dotenv()

try:
    import jwt
except ImportError:  # pragma: no cover - exercised only when dependency missing
    jwt = None


_APP_TOKEN_CACHE = {"token": None, "expires_at": None}
_APP_TOKEN_LOCK = threading.Lock()
_APP_TOKEN_REFRESH_BUFFER_SECONDS = 120


def _read_github_app_private_key() -> str:
    key = (os.getenv("GITHUB_APP_PRIVATE_KEY") or "").strip()
    if key:
        return key.replace("\\n", "\n")

    key_path = (os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip()
    if key_path:
        with open(key_path, "r", encoding="utf-8") as fh:
            return fh.read()

    raise RuntimeError(
        "GitHub App auth is enabled but no private key found. "
        "Set `GITHUB_APP_PRIVATE_KEY` or `GITHUB_APP_PRIVATE_KEY_PATH`."
    )


def _github_app_auth_enabled() -> bool:
    return bool(
        (os.getenv("GITHUB_APP_ID") or "").strip()
        and (os.getenv("GITHUB_APP_INSTALLATION_ID") or "").strip()
        and (
            (os.getenv("GITHUB_APP_PRIVATE_KEY") or "").strip()
            or (os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip()
        )
    )


def _get_cached_app_token(now: datetime) -> str | None:
    expires_at = _APP_TOKEN_CACHE.get("expires_at")
    token = _APP_TOKEN_CACHE.get("token")
    if not token or not expires_at:
        return None

    if expires_at > now + timedelta(seconds=_APP_TOKEN_REFRESH_BUFFER_SECONDS):
        return token
    return None


def _build_github_app_jwt(app_id: str, private_key: str) -> str:
    if jwt is None:
        raise RuntimeError(
            "GitHub App auth requires PyJWT. Install dependencies and retry."
        )

    now = datetime.now(timezone.utc)
    payload = {
        "iat": int((now - timedelta(seconds=60)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def _request_installation_token() -> tuple[str, datetime]:
    app_id = (os.getenv("GITHUB_APP_ID") or "").strip()
    installation_id = (os.getenv("GITHUB_APP_INSTALLATION_ID") or "").strip()

    if not app_id or not installation_id:
        raise RuntimeError(
            "GitHub App auth requires `GITHUB_APP_ID` and `GITHUB_APP_INSTALLATION_ID`."
        )

    private_key = _read_github_app_private_key()
    app_jwt = _build_github_app_jwt(app_id, private_key)
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"

    response = requests.post(
        url=url,
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "User-Agent": os.getenv("GITHUB_USER_AGENT", "Github-Sponsor-Dashboard"),
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    token = data.get("token")
    expires_at_raw = data.get("expires_at")
    if not token or not expires_at_raw:
        raise RuntimeError(
            "GitHub App token exchange succeeded but response was missing token fields."
        )

    expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
    return token, expires_at


def _get_github_app_installation_token() -> str:
    now = datetime.now(timezone.utc)
    cached = _get_cached_app_token(now)
    if cached:
        return cached

    with _APP_TOKEN_LOCK:
        now = datetime.now(timezone.utc)
        cached = _get_cached_app_token(now)
        if cached:
            return cached

        token, expires_at = _request_installation_token()
        _APP_TOKEN_CACHE["token"] = token
        _APP_TOKEN_CACHE["expires_at"] = expires_at
        return token


def _get_github_token() -> str:
    """Return GitHub auth token from environment.

    This project historically uses `PAT`. We also accept `GITHUB_TOKEN` as an alias
    to reduce configuration footguns.
    """
    if _github_app_auth_enabled():
        return _get_github_app_installation_token()

    token = (os.getenv("PAT") or os.getenv("GITHUB_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "Missing GitHub auth configuration. Set GitHub App env vars "
            "(`GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`/`..._PATH`) "
            "or set `PAT` (preferred) / `GITHUB_TOKEN`."
        )
    return token


def _build_headers() -> dict:
    token = _get_github_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        # GitHub API best practice: include a User-Agent.
        "User-Agent": os.getenv("GITHUB_USER_AGENT", "Github-Sponsor-Dashboard"),
    }


# Function to automatically detect API limits if they occur when running GET requests
def getRequest(url):
    headers = _build_headers()
    while True:
        res = requests.get(url=url, headers=headers)

        if res.status_code == 200:
            return res
        elif res.status_code == 403:
            if "Repository access blocked" in res.text:
                logging.warning(
                    f"{res.status_code}: Repository access blocked, Skipping. {url}"
                )
                return [], res.headers
            remaining = res.headers.get("X-RateLimit-Remaining")
            reset = res.headers.get("X-RateLimit-Reset")

            # If API request tokens remaining hits 0
            if remaining == "0" and reset:
                resetTokens(reset)
                continue
            else:
                logging.error(f"{res.status_code}: API ERROR: {res.text}")
                raise Exception(f"403 Forbidden, not due to rate limit: {res.text}")
        else:
            res.raise_for_status()


# Function to automatically detect API limits if they occur when running POST requests
# (Specifically to the Github GraphQL API)
def postRequest(url, json=None, initial_delay=2, max_retries=5, timeout=30):
    """Sends a POST request with retries for server errors and rate limits.
    Args:
        url (str): The URL to send the request to.
        json (dict, optional): The JSON payload for the request. Defaults to None.
        initial_delay (int, optional): Initial delay in seconds for retries. Defaults to 2.
        max_retries (int, optional): Maximum number of retries. Defaults to 5.
        timeout (int, optional): Request timeout in seconds. Defaults to 30.
    Raises:
        requests.exceptions.HTTPError: For client-side errors (4xx).
        Exception: If the request fails after all retries.
    Returns:
        requests.Response: The response object on success.
    """
    headers = _build_headers()

    for attempt in range(max_retries):
        try:
            response = requests.post(
                url=url, headers=headers, json=json, timeout=timeout
            )

            # Check for rate limiting on every response
            if (
                "X-RateLimit-Remaining" in response.headers
                and response.headers["X-RateLimit-Remaining"] == "0"
            ):
                resetTokens(response.headers.get("X-RateLimit-Reset"))
                # After waiting, we should retry the request, so we continue the loop
                logging.info("Rate limit reset. Waiting for tokens to refresh.")
                continue

            # Raise an exception for any non-200 status codes
            response.raise_for_status()

            # If we get here, the request was successful (2xx status code)
            print(
                f"\rRemaining API Tokens: {response.headers.get('X-RateLimit-Remaining', 'N/A')}",
                end="",
                flush=True,
            )
            return response

        except requests.exceptions.HTTPError as e:
            # Only retry on server-side errors (5xx)
            if 500 <= e.response.status_code < 600:
                logging.warning(
                    f"Server error ({e.response.status_code}) received. (Attempt {attempt + 1}/{max_retries})"
                )
            else:
                # For client errors (4xx), fail immediately without retrying
                if e.response.status_code == 401:
                    logging.error(
                        "Unauthorized (401) from GitHub API. This usually means your token is missing, invalid, or revoked. "
                        "Verify `PAT` (or `GITHUB_TOKEN`) is set and valid."
                    )
                logging.error(
                    f"Client error ({e.response.status_code}) received. Not retrying. Error: {e}"
                )
                raise

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logging.warning(
                f"Network error ({type(e).__name__}) occurred. (Attempt {attempt + 1}/{max_retries})"
            )

        # If this was the last attempt, break the loop to raise the final exception
        if attempt == max_retries - 1:
            break

        # Wait before the next retry
        delay = initial_delay * (2**attempt)
        logging.info(f"Retrying in {delay} seconds...")
        time.sleep(delay)

    # If the loop completes without returning, it means all retries have failed.
    raise Exception(f"API request failed for {url} after {max_retries} attempts.")


# If API limit is hit during an api request, calculate the time remaining till tokens refresh and sleep worker
def resetTokens(reset):
    reset_time = int(reset)
    now = int(time.time())
    sleep_time = reset_time - now
    print(f"\n\n[Rate Limit Hit] Sleeping {sleep_time} seconds...")
    for i in range(sleep_time + 5):
        print(f"\rCurrent Time Slept: {i} seconds", end="", flush=True)
        time.sleep(1)
    print("\nGithub Tokens Restored!\n\n")
    return
