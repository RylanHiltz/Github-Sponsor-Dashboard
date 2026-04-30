import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.utils import github_api


class GitHubApiAuthTests(unittest.TestCase):
    def setUp(self):
        github_api._APP_TOKEN_CACHE["token"] = None
        github_api._APP_TOKEN_CACHE["expires_at"] = None

    def tearDown(self):
        github_api._APP_TOKEN_CACHE["token"] = None
        github_api._APP_TOKEN_CACHE["expires_at"] = None

    @patch.dict(
        os.environ,
        {
            "PAT": "pat_token_value",
            "GITHUB_APP_ID": "",
            "GITHUB_APP_INSTALLATION_ID": "",
            "GITHUB_APP_PRIVATE_KEY": "",
            "GITHUB_APP_PRIVATE_KEY_PATH": "",
        },
        clear=False,
    )
    def test_build_headers_uses_pat_when_app_not_configured(self):
        headers = github_api._build_headers()
        self.assertEqual(headers["Authorization"], "Bearer pat_token_value")
        self.assertIn("User-Agent", headers)

    @patch.dict(
        os.environ,
        {
            "PAT": "",
            "GITHUB_TOKEN": "",
            "GITHUB_APP_ID": "12345",
            "GITHUB_APP_INSTALLATION_ID": "67890",
            "GITHUB_APP_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----",
        },
        clear=False,
    )
    def test_app_token_is_refreshed_and_cached(self):
        fake_jwt = SimpleNamespace(encode=Mock(return_value="signed.jwt"))
        expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        fake_response = Mock()
        fake_response.raise_for_status = Mock()
        fake_response.json = Mock(return_value={"token": "inst_token", "expires_at": expires})

        with patch.object(github_api, "jwt", fake_jwt), patch.object(
            github_api.requests, "post", return_value=fake_response
        ) as post_mock:
            token_first = github_api._get_github_token()
            token_second = github_api._get_github_token()

        self.assertEqual(token_first, "inst_token")
        self.assertEqual(token_second, "inst_token")
        self.assertEqual(post_mock.call_count, 1)

    @patch.dict(
        os.environ,
        {
            "PAT": "",
            "GITHUB_TOKEN": "",
            "GITHUB_APP_ID": "12345",
            "GITHUB_APP_INSTALLATION_ID": "67890",
            "GITHUB_APP_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\\nfake\\n-----END PRIVATE KEY-----",
        },
        clear=False,
    )
    def test_app_auth_requires_pyjwt(self):
        with patch.object(github_api, "jwt", None):
            with self.assertRaises(RuntimeError):
                github_api._get_github_token()


if __name__ == "__main__":
    unittest.main()
