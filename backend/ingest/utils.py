import time
import logging
import base64
from datetime import timedelta, datetime
from dotenv import load_dotenv
from backend.utils.github_api import postRequest

# Scraping Import
from playwright.sync_api import sync_playwright

# Query Import
from backend.db.queries.users import getGithubIDs
from backend.db.queries.queue import batchAddQueue


load_dotenv()

# Globals
URL = "https://api.github.com/graphql"
SPONSORS_URL = "https://github.com/sponsors/explore"


# Parent function to handle both functions running
# Return a list of sponsors, sponsored users, and a count of private sponsors
def get_sponsorships(username, github_id: int, user_type):
    logging.info(f"Starting Sponsorship Fetch via API for {user_type} '{username}'")

    sponsor_list, private_count, lowest_tier_cost = get_sponsors_from_api(
        github_id,
        user_type,
    )
    sponsored_list = get_sponsored_from_api(
        github_id,
        user_type,
    )
    return sponsor_list, sponsored_list, private_count, lowest_tier_cost


# Returns the sponsors that are associated to the passed in user
def get_sponsors_from_api(github_id, user_type):
    """
    Fetches all sponsors for a given user or organization using the GitHub GraphQL API.
        :param username: The login name of the user or organization.
        :param user_type: The type of account, either 'user' or 'organization'.

    If a user does not have a minimum monthly tier, the database will set that value to 0.
    Their monthly income estimate will be derived from the median monthly sponsor cost.
    """
    if user_type.lower() not in ["user", "organization"]:
        raise ValueError("user_type must be 'user' or 'organization'")

    prefix = "04:" if user_type.lower() == "user" else "12:"
    node_id = base64.b64encode(
        f"{prefix}{user_type.title()}{github_id}".encode("utf-8")
    ).decode("utf-8")

    sponsors_list: list[int] = []
    private_sponsors_count = 0
    lowest_tier_cost = 0
    has_next_page = True
    cursor = None
    response = None

    # Dynamic query template for the Github GraphQL API
    # snippet-start: GraphQL-Sponsor-Query
    query_template = f"""
    query($nodeId: ID!, $cursor: String) {{
      node(id: $nodeId) {{
        ... on {user_type.title()} {{
          sponsorshipsAsMaintainer(first: 100, after: $cursor, includePrivate: true) {{
            totalCount
            pageInfo {{
              endCursor
              hasNextPage
            }}
            nodes {{
              privacyLevel
              sponsorEntity {{
                ... on User {{ databaseId }}
                ... on Organization {{ databaseId }}
              }}
            }}
          }}
          sponsorsListing {{
            tiers(first: 20) {{
              nodes {{
                monthlyPriceInCents
                isOneTime
              }}
            }}
          }}
        }}
      }}
    }}
    """
    # snippet-end

    print(f"Starting Sponsors Fetch for {user_type} ''")
    start_time = time.time()

    while has_next_page:
        # Corrected variables dictionary. The key 'nodeId' must match the query variable '$nodeId'.
        variables = {"nodeId": node_id, "cursor": cursor}
        query = {"query": query_template, "variables": variables}

        try:
            response = postRequest(url=URL, json=query)
            data = response.json()
        except Exception as e:
            logging.error(f"Failed to fetch sponsors. Error: {e}")
            break

        if "errors" in data:
            logging.error(f"GraphQL errors: {data['errors']}")
            # DO NOT BREAK. RAISE EXCEPTION.
            raise Exception("Partial fetch detected: GraphQL returned errors.")

        entity_data = data.get("data", {}).get("node", {})
        if not entity_data:
            # If we expected data but got none, abort.
            raise Exception("Partial fetch detected: Node data missing.")

        if not cursor:  # First page
            sponsors_listing = entity_data.get("sponsorsListing")
            if sponsors_listing and sponsors_listing.get("tiers"):
                tiers = sponsors_listing["tiers"]["nodes"]
                monthly_prices_in_cents = [
                    tier["monthlyPriceInCents"]
                    for tier in tiers
                    if not tier.get("isOneTime") and "monthlyPriceInCents" in tier
                ]
                if monthly_prices_in_cents:
                    lowest_tier_cost = min(monthly_prices_in_cents) / 100
                    logging.info(f"Lowest monthly tier: ${lowest_tier_cost:.2f}")

        sponsorships = entity_data.get("sponsorshipsAsMaintainer")
        if not sponsorships:
            logging.info(f"Could not retrieve sponsorships for ID {github_id}.")
            break

        if not cursor:
            total_sponsors = sponsorships.get("totalCount", 0)
            logging.info(f"Total sponsors reported by API: {total_sponsors}")

        for node in sponsorships.get("nodes", []):
            if not node:
                continue
            if node.get("privacyLevel") == "PRIVATE":
                private_sponsors_count += 1
            elif node.get("sponsorEntity") and node["sponsorEntity"].get("databaseId"):
                sponsors_list.append(node["sponsorEntity"]["databaseId"])

        page_info = sponsorships.get("pageInfo", {})
        has_next_page = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")

    end_time = time.time()
    logging.info(f"API fetch completed in {end_time - start_time:.2f} seconds.")
    print(sponsors_list, len(sponsors_list))

    return sponsors_list, private_sponsors_count, lowest_tier_cost


# Returns an array of users who are sponsored by the passed in user
def get_sponsored_from_api(github_id, user_type):
    """
    Fetches all sponsored for a given user or organization using the GitHub GraphQL API.
    :param github_id: The database ID of the user or organization.
    :param user_type: The type of account, either 'user' or 'organization'.
    """
    if user_type.lower() not in ["user", "organization"]:
        raise ValueError("user_type must be 'user' or 'organization'")

    # The prefix for a User ID is '04:' and for an Organization ID is '12:'.
    # This is not officially documented but is the current standard.
    prefix = "04:" if user_type.lower() == "user" else "12:"
    node_id = base64.b64encode(
        f"{prefix}{user_type.title()}{github_id}".encode("utf-8")
    ).decode("utf-8")

    sponsored_list: list[int] = []
    has_next_page = True
    cursor = None

    # Dynamic query template for the Github GraphQL API
    query_template = f"""
    query($nodeId: ID!, $cursor: String) {{
      node(id: $nodeId) {{
        ... on {user_type.title()} {{
          sponsorshipsAsSponsor(first: 100, after: $cursor) {{
            totalCount
            pageInfo {{
              endCursor
              hasNextPage
            }}
            nodes {{
              sponsorable {{
                ... on User {{ databaseId }}
                ... on Organization {{ databaseId }}
              }}
            }}
          }}
        }}
      }}
    }}
    """

    start_time = time.time()

    logging.info(f"Starting Sponsoring Fetch for {user_type} ID '{github_id}'")
    while has_next_page:
        variables = {"nodeId": node_id, "cursor": cursor}
        query = {"query": query_template, "variables": variables}

        try:
            response = postRequest(url=URL, json=query)
            data = response.json()
        except Exception as e:
            logging.error(f"Failed to fetch sponsored for ID '{github_id}'. Error: {e}")
            # FIX: Raise exception so worker retry logic kicks in
            raise Exception(f"Sponsoring API Error: {e}")

        if "errors" in data:
            logging.error(f"GraphQL errors: {data['errors']}")
            # FIX: Raise exception to protect DB
            raise Exception("Partial fetch detected: GraphQL returned errors.")

        entity_data = data.get("data", {}).get("node", {})
        if not entity_data:
            logging.warning(f"Could not find entity with the provided ID {github_id}.")
            raise Exception("Partial fetch detected: Node data missing.")

        sponsored = entity_data.get("sponsorshipsAsSponsor")
        if not sponsored:
            logging.warning(
                f"Could not retrieve sponsored users for ID {github_id}. They may not be sponsoring any users."
            )
            break

        if not cursor:  # Only log total on the first page
            total_sponsoring = sponsored.get("totalCount", 0)
            logging.info(f"Total sponsored users reported by API: {total_sponsoring}")

        for node in sponsored.get("nodes", []):
            if (
                node
                and node.get("sponsorable")
                and node["sponsorable"].get("databaseId")
            ):
                sponsored_list.append(node["sponsorable"]["databaseId"])

        page_info = sponsored.get("pageInfo", {})
        has_next_page = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")

    end_time = time.time()
    logging.info(f"API fetch completed in {end_time - start_time:.2f} seconds.")
    if response:
        logging.info(
            f"Remaining Github API Tokens: {response.headers.get('X-RateLimit-Remaining')}"
        )
    print(sponsored_list, len(sponsored_list))
    return sponsored_list


# Recursively queries the Github GraphQL API to collect users who are sponsorable
def getSponsorableUsers(db, init: bool):
    """Retrieve GitHub account IDs for accounts that are sponsorable by querying the GitHub GraphQL API.

    This function coordinates with the provided database connection and the GitHub GraphQL
    endpoint to collect account identifiers for entities whose "isSponsorable" flag is true.
    Behaviour is controlled by the `init` flag:

    Parameters
    ----------
    db : object
        Database connection or session used to read/write state related to worker.py.
        Expected to be a DB-API/ORM session (for example, a SQLAlchemy Session) or an
        application-specific connection object. The function may read from and/or update
        tables that track last-run timestamps, pagination cursors, or fetched identifiers.
    init : bool
        Worker initialization flag:
        - **True:** full collection mode (collect all possible sponsorable user IDs).
        - **False:** incremental mode (collect a recent, bounded set - 2000 by default).
    """

    sort_clause = ""
    if not init:
        sort_clause = "sort:joined-desc"

    # helper to page through a search query (when userCount <= 1000)
    def fetch_and_queue(search_query):
        cursor = None
        has_next = True
        total_fetched = 0
        while has_next:
            variables = {"cursor": cursor}
            query = {
                "query": f"""
                query($cursor: String) {{
                  search(query: "{search_query}", type: USER, first: 100, after: $cursor) {{
                    userCount
                    pageInfo {{ endCursor hasNextPage }}
                    edges {{
                      node {{
                        ... on User {{ databaseId }}
                        ... on Organization {{ databaseId }}
                      }}
                    }}
                  }}
                }}
                """,
                "variables": variables,
            }
            resp = postRequest(url=URL, json=query)
            data = resp.json()
            if "errors" in data:
                logging.error("GraphQL errors: %s", data["errors"])
                return 0, True  # signal error to caller

            search = data.get("data", {}).get("search", {})
            edges = search.get("edges", [])
            user_ids = []
            for edge in edges:
                node = edge.get("node", {})
                dbid = node.get("databaseId")
                if dbid:
                    user_ids.append(dbid)

            if user_ids:
                batchAddQueue(user_ids, 1, db)
                total_fetched += len(user_ids)

            page_info = search.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")
        return total_fetched, False

    # adaptive recursive splitter for date ranges
    def fetch_range(start_date: datetime, end_date: datetime):
        # Build search qualifier with created range
        created_q = f"created:{start_date.date()}..{end_date.date()}"
        search_query = f"is:sponsorable {created_q} {sort_clause}".strip()

        # initial count probe (first page)
        variables = {"cursor": None}
        probe_query = {
            "query": f"""
            query($cursor: String) {{
              search(query: "{search_query}", type: USER, first: 1, after: $cursor) {{
                userCount
              }}
            }}
            """,
            "variables": variables,
        }
        resp = postRequest(url=URL, json=probe_query)
        data = resp.json()
        if "errors" in data:
            logging.error("GraphQL errors during probe: %s", data["errors"])
            return 0

        user_count = data.get("data", {}).get("search", {}).get("userCount", 0)
        logging.info(
            "Probe %s -> %s : %d users", start_date.date(), end_date.date(), user_count
        )

        # If zero — nothing to do
        if user_count == 0:
            return 0

        # If within API limit, fetch pages and queue
        if user_count <= 1000:
            fetched, errored = fetch_and_queue(search_query)
            if errored:
                logging.error("Error during fetch_and_queue for %s", search_query)
            return fetched

        # If too big and the range is > 1 day, split and recurse
        if (end_date - start_date).days <= 1:
            # fallback: we can't split further; log and fetch what we can (will still be capped)
            logging.warning(
                "Range %s..%s still >1000 results, fetching pages (will be capped at 1000).",
                start_date.date(),
                end_date.date(),
            )
            fetched, _ = fetch_and_queue(search_query)
            return fetched

        mid = start_date + (end_date - start_date) / 2
        left = fetch_range(start_date, mid)
        right = fetch_range(mid + timedelta(days=1), end_date)
        return left + right

    # determine global range to scan. For full init, scan from 2008-01-01 until today; adjust as needed.
    today = datetime.now()
    if init:
        start = datetime(2008, 1, 1)  # GitHub earliest possible
    else:
        # incremental: scan recent 2 weeks
        start = today - timedelta(weeks=2)

    total = fetch_range(start, today)
    logging.info("Finished sponsorable collection. Total queued: %d", total)
    return
