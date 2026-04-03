import requests
import time
import os
import logging
from dotenv import load_dotenv


load_dotenv()


def _get_github_token() -> str:
    """Return GitHub auth token from environment.

    This project historically uses `PAT`. We also accept `GITHUB_TOKEN` as an alias
    to reduce configuration footguns.
    """
    token = (os.getenv("PAT") or os.getenv("GITHUB_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "Missing GitHub token. Set `PAT` (preferred) or `GITHUB_TOKEN` in your .env/environment. "
            "The token must be a GitHub Personal Access Token with the required scopes."
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
