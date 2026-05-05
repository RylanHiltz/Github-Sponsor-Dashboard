import os
import unittest
from unittest.mock import Mock, patch

from backend.utils import github_api


class GitHubApiAuthTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "PAT": "pat_token_value",
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
        },
        clear=False,
    )
    def test_build_headers_uses_oauth_token_when_pat_missing(self):
        with patch(
            "backend.utils.github_oauth.get_valid_access_token",
            return_value="oauth_access_token",
        ):
            headers = github_api._build_headers()
        self.assertEqual(headers["Authorization"], "Bearer oauth_access_token")

    @patch.dict(
        os.environ,
        {
            "PAT": "pat_token_value",
        },
        clear=False,
    )
    def test_postrequest_graphql_can_extract_one_sponsor_and_sponsored(self):
        query = {"query": """
            query {
              viewer {
                sponsorshipsAsMaintainer(first: 1) {
                  nodes {
                    sponsorEntity {
                      ... on User { databaseId }
                      ... on Organization { databaseId }
                    }
                  }
                }
                sponsorshipsAsSponsor(first: 1) {
                  nodes {
                    sponsorable {
                      ... on User { databaseId }
                      ... on Organization { databaseId }
                    }
                  }
                }
              }
            }
            """}

        fake_response = Mock()
        fake_response.raise_for_status = Mock()
        fake_response.headers = {"X-RateLimit-Remaining": "4999"}
        fake_response.json = Mock(
            return_value={
                "data": {
                    "viewer": {
                        "sponsorshipsAsMaintainer": {
                            "nodes": [
                                {
                                    "sponsorEntity": {
                                        "databaseId": 111,
                                    }
                                }
                            ]
                        },
                        "sponsorshipsAsSponsor": {
                            "nodes": [
                                {
                                    "sponsorable": {
                                        "databaseId": 222,
                                    }
                                }
                            ]
                        },
                    }
                }
            }
        )

        with patch.object(
            github_api.requests, "post", return_value=fake_response
        ) as post_mock:
            resp = github_api.postRequest("https://api.github.com/graphql", json=query)
            data = resp.json()

        # Verify request had auth header.
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs["url"], "https://api.github.com/graphql")
        self.assertEqual(kwargs["json"], query)
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer pat_token_value")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")

        # Extract one sponsor and one sponsored id from the response.
        viewer = data["data"]["viewer"]
        sponsor_nodes = viewer["sponsorshipsAsMaintainer"]["nodes"]
        sponsoring_nodes = viewer["sponsorshipsAsSponsor"]["nodes"]

        sponsor_id = sponsor_nodes[0]["sponsorEntity"]["databaseId"]
        sponsored_id = sponsoring_nodes[0]["sponsorable"]["databaseId"]

        self.assertEqual(sponsor_id, 111)
        self.assertEqual(sponsored_id, 222)


if __name__ == "__main__":
    unittest.main()
