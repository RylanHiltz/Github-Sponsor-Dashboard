# ENV Imports
from dotenv import load_dotenv
import os

# DB Query imports
from backend.db.queries.queue import deleteFromQueue
from backend.models.UserModel import UserModel

# Functional Imports
from backend.utils.github_api import getRequest, postRequest
from openai import OpenAI
from datetime import datetime, timezone
import requests
import json
import re

# Scraper Imports
from playwright.sync_api import sync_playwright

# Logging Imports
import logging

# Load sensitive variables
load_dotenv()
EMAIL = os.getenv("email")
API_KEY = os.getenv("API_KEY")
URL = "https://api.github.com/graphql"


# File for query logic that will be used/imported into the scraper
def createUser(github_id: int, db):

    user = getUserData(github_id, db)

    # Check if user is None before proceeding
    if user is None:
        logging.error(f"Cannot create user {github_id}: No data returned.")
        return None, None

    print(user)

    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (
                github_id,
                username,
                name,
                type,
                has_pronouns,
                gender,
                location,
                avatar_url,
                profile_url,
                company,
                following,
                followers,
                hireable,
                bio,
                public_repos,
                public_gists,
                twitter_username,
                email,
                last_scraped,
                is_enriched,
                github_created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (github_id) DO UPDATE SET
                username = EXCLUDED.username,
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                has_pronouns = EXCLUDED.has_pronouns,
                gender = EXCLUDED.gender,
                location = EXCLUDED.location,
                avatar_url = EXCLUDED.avatar_url,
                profile_url = EXCLUDED.profile_url,
                company = EXCLUDED.company,
                following = EXCLUDED.following,
                followers = EXCLUDED.followers,
                hireable = EXCLUDED.hireable,
                bio = EXCLUDED.bio,
                public_repos = EXCLUDED.public_repos,
                public_gists = EXCLUDED.public_gists,
                twitter_username = EXCLUDED.twitter_username,
                email = EXCLUDED.email,
                last_scraped = EXCLUDED.last_scraped,
                is_enriched = EXCLUDED.is_enriched,
                github_created_at = EXCLUDED.github_created_at;
            """,
            (
                user.github_id,
                user.username,
                user.name,
                user.type,
                user.has_pronouns,
                user.gender,
                user.location,
                user.avatar_url,
                user.profile_url,
                user.company,
                user.following,
                user.followers,
                user.hireable,
                user.bio,
                user.public_repos,
                user.public_gists,
                user.twitter_username,
                user.email,
                user.last_scraped,
                user.is_enriched,
                user.github_created_at,
            ),
        )
        # Get the user id
        cur.execute(
            """
            SELECT id FROM users WHERE github_id = %s;
            """,
            (user.github_id,),
        )
        user_id = cur.fetchone()[0]

        db.commit()
        cur.close()
        logging.info(f"Created or updated user with GitHub ID: {user.github_id}")
    # Returns the user object and user id to the worker
    return user, user_id


# User already exists from previous sponsorship relation, run Github API request, collect and update user data
def enrichUser(github_id: int, db, enriched=False, identity=None):

    try:
        if not enriched:
            user = getUserData(github_id=github_id, db=db)
        else:
            user = getUserData(
                github_id=github_id, db=db, is_enriched=enriched, identity=identity
            )
    except ValueError as ve:
        logging.info(f"User {github_id} not found or removed: {ve}")
        raise  # re-raise so caller (worker) can handle it
    except Exception:
        logging.exception(f"Error fetching user data for {github_id}")
        return None

    if user is None:
        logging.info(f"No user data returned for {github_id}, skipping enrichment")
        return None

    with db.cursor() as cur:

        cur.execute(
            "SELECT id, github_id FROM users WHERE username = %s LIMIT 1;",
            (user.username,),
        )
        row = cur.fetchone()
        if row and row[1] != user.github_id:
            existing_id, _ = row
            # Merge strategy: remove placeholder row for this github_id (if any),
            # then assign the correct github_id to the username row.
            cur.execute(
                "DELETE FROM users WHERE github_id = %s AND id <> %s;",
                (user.github_id, existing_id),
            )
            cur.execute(
                "UPDATE users SET github_id = %s WHERE id = %s;",
                (user.github_id, existing_id),
            )

        cur.execute(
            """
            UPDATE users SET
                github_id = %s,
                username = %s,
                name = %s,
                type = %s,
                has_pronouns = %s,
                gender = %s,
                location = %s,
                avatar_url = %s,
                profile_url = %s,
                company = %s,
                following = %s,
                followers = %s,
                hireable = %s,
                bio = %s,
                public_repos = %s,
                public_gists = %s,
                twitter_username = %s,
                email = %s,
                last_scraped = %s,
                is_enriched = %s,
                github_created_at = %s
            WHERE github_id = %s
            """,
            (
                user.github_id,
                user.username,
                user.name,
                user.type,
                user.has_pronouns,
                user.gender,
                user.location,
                user.avatar_url,
                user.profile_url,
                user.company,
                user.following,
                user.followers,
                user.hireable,
                user.bio,
                user.public_repos,
                user.public_gists,
                user.twitter_username,
                user.email,
                user.last_scraped,
                user.is_enriched,
                user.github_created_at,
                user.github_id,
            ),
        )
        db.commit()
        logging.info(f"Enriched user")
    # Returns the type of the user after getting metadata for scraping
    return user


# Batch create minimum users for sponsorship relations
def batchCreateUser(github_ids, db):

    entries = [(github_id,) for github_id in github_ids]

    with db.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO users (github_id)
            VALUES (%s)
            ON CONFLICT (github_id) DO NOTHING;
            """,
            entries,
        )
    db.commit()
    cur.close()
    return


def getUserData(github_id: int, db, is_enriched=False, identity=None):
    try:
        data = getGithubData(github_id=github_id, db=db)
        if not data:
            return None

        user = UserModel.from_api(data)

        if user.location is not None:
            user.location = getLocation(user.location)

        # If user type is User
        if user.type == "User":
            # safe identity access (identity expected to be dict or None)
            prev_has_pronouns = False
            prev_gender = None
            if isinstance(identity, dict):
                prev_has_pronouns = bool(identity.get("pronouns", False))
                prev_gender = identity.get("gender", None)

            # Preset variables, if GitHub is not provided for scraping, function will skip pronouns
            # and fall back on gpt-4o-mini query
            has_pronouns = False
            gender_data = None

            # Conditionally scrape pronouns only if credentials are provided in the .env file
            if os.getenv("gh_username") and os.getenv("gh_password"):
                try:
                    has_pronouns, gender_data = scrapePronouns(user.username)
                except Exception as e:
                    # Log the error but don't crash the whole process
                    logging.error(f"Pronoun scraping failed for {user.username}: {e}")

            user.has_pronouns = bool(has_pronouns)

            if not is_enriched:
                # initial enrichment: prefer explicit pronouns, else infer
                if user.has_pronouns:
                    user.gender = gender_data
                else:
                    user.gender = getGender(user.name, user.location)
                user.is_enriched = True
                return user

            # This block handles re-enrichment of an existing user.
            # If no new pronouns are found on the profile during the scrape:
            if not user.has_pronouns:
                # Preserve the previously stored gender and pronoun status.
                user.gender = prev_gender
                user.has_pronouns = prev_has_pronouns
            else:
                # If new pronouns are found, update the gender based on them.
                user.gender = gender_data

            user.is_enriched = True
            return user

        # Organization
        user.is_enriched = True
        return user

    except requests.exceptions.HTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 404:
            logging.error(
                f"GitHub user {github_id} not found (404). Removing from queue/db."
            )
            raise ValueError("User not found on GitHub.")
        logging.error(
            f"Failed to fetch GitHub profile for {github_id}: "
            f"{getattr(e, 'response', '')}"
        )
        return None
    except Exception as e:
        logging.error(
            f"Unexpected error in getUserData for {github_id}: {e}", exc_info=True
        )
        return None


# Use GraphQL to query for users data based off their github ID
def getGithubData(github_id: int, db):
    try:
        rest_url = f"https://api.github.com/user/{github_id}"
        response = getRequest(url=rest_url)

        # Ensure response is a Response object to satisfy Pylance type checker
        if not isinstance(response, requests.Response):
            raise ValueError(f"Expected requests.Response, got {type(response)}")

        response.raise_for_status()
        return response.json()

    # If user data does not exist in Github API, nuke from sponsorship database
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.error(
                f" has changed usernames or no longer exists on github, Nuke user from DB."
            )
            deleteFromQueue(github_id, db)
            deleteUser(github_id, db)
            raise ValueError(f"User not found on GitHub.")
        else:
            logging.error(
                f"An unexpected error occurred fetching user by ID {github_id}: {e}"
            )
    return None


# Attempts to remove words that may confuse the location API to pull country of origin for user
def clean_location(location):
    if not location or location.strip() == "":
        return None

    # Remove common symbols and meaningless characters
    location = re.sub(r'[#@$%^&*()_+=\[\]{}|\\:";\'<>?/~`]', "", location)

    # Remove URLs and email-like patterns
    location = re.sub(r"https?://\S+", "", location)
    location = re.sub(r"\S+@\S+\.\S+", "", location)

    # Remove numbers at the start/end (like zip codes, but keep numbers in middle)
    location = re.sub(r"^\d+\s*|\s*\d+$", "", location)

    # Existing patterns
    patterns_to_remove = [
        r"greater\s+",
        r"area",
        r"metro",
        r"vicinity",
        r"region",
        r"\bthe\b",
    ]

    location = location.lower()
    for pattern in patterns_to_remove:
        location = re.sub(pattern, "", location)

    # Remove extra spaces, commas, and trim
    location = re.sub(r"\s+", " ", location).strip(" ,.-")

    # If location is too short or meaningless after cleaning, return None
    if len(location) < 2 or location.lower() in ["n/a", "none", "null", ""]:
        return None

    return location.title()


def getLocationByImportance(locations):
    if not locations:
        return None
    best = max(locations, key=lambda x: x.get("importance", 0))
    address = best.get("address", {})
    return address.get("country")


# Take the location of the github user, use openstreetmap API to pull the country of origin
def getLocation(location):
    location = clean_location(location)
    if location:
        url = f"https://nominatim.openstreetmap.org/search?q={location}&format=json&addressdetails=1"
        headers = {
            "User-Agent": f"github-sponsor-dashboard/1.0 ({EMAIL})",
            "Accept-Language": "en",
        }
        res = requests.get(url=url, headers=headers)
        if res.status_code == 200:
            data = res.json()

            # Check if we got a valid response structure
            if data and "address" in data[0]:
                address = data[0]["address"]

                # Case 1: Standard Country found
                if "country" in address:
                    country = getLocationByImportance(data)
                    return country

                # Case 2: It's a continent
                elif "continent" in address:
                    # This may change in the future, but for now return none
                    return None
            else:
                logging.warning(f"No location data found for '{location}'.")
                return None
        else:
            logging.error(
                f"OpenStreetMap.Org Request failed:", res.status_code, res.text
            )
            return None
    return None


# Scrapes the pronouns of a passed in user
def scrapePronouns(name):
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        url = f"https://github.com/{name}"

        context = browser.new_context(storage_state="auth.json")
        page = context.new_page()
        page.goto(url)

        # content = page.content()
        pronoun_span = page.query_selector("span[itemprop='pronouns']")
        if pronoun_span:
            pronouns = pronoun_span.inner_text()
            has_pronouns, gender = extract_pronouns(pronouns)
        else:
            has_pronouns, gender = False, None

        browser.close()
        return has_pronouns, gender


# Extracts the pronouns out of the pronoun span (users may have random words and pronouns mixed)
def extract_pronouns(text):
    text = text.lower()

    # Normalize slashes and spaces
    text = re.sub(r"\s*/\s*", "/", text)  # 'he / him' → 'he/him'
    text = re.sub(r"[^\w/]", " ", text)  # remove punctuation except slash

    # Tokenize and look for pronoun sets
    pronouns = re.findall(
        r"\b(?:he/him|she/her|they/them|he/they|she/they|he/her|she/him)\b", text
    )

    if not pronouns:
        return False, None

    found = pronouns[0]

    # Check for ambiguous/mixed combinations
    if found in ["he/her", "she/him"]:
        return True, "Other"

    if found == "he/him" or found == "he/they":
        return True, "Male"
    if found == "she/her" or found == "she/they":
        return True, "Female"
    if found == "they/them":
        return True, "Other"

    # Fallback
    return True, "Other"


# Infer the gender of the username using the full name and current country (assuming place of origin for some users)
def getGender(name, country):
    # Use gpt-4o-mini for gender inferencing
    client = OpenAI(api_key=API_KEY)
    user_message = f"full name: {name}"
    if country is not None:
        user_message += f", current location: {country}"

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
                    Infer gender using fullname. Only output valid json in this format (Try not to output Unknown): { "gender": "Male" }, { "gender": "Female" }, or { "gender": "Unknown" }
                """,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
    )
    output = res.choices[0].message.content

    if not output:
        return "Unknown"

    try:
        user = json.loads(output)
        gender = user.get("gender", "Unknown")
        return gender
    except json.JSONDecodeError:
        return "Unknown"


# Runs a check if the user exists in the database an has already been visisted once
def findUser(github_id: int, db):
    """
    Returns a dictionary object of specific data required for the data enrichment of users.
    - Will output different data depending on the enriched state of the user in queue
    """

    identity: dict = {
        "user_id": None,
        "user_exists": False,
        "is_enriched": False,
        "gender": None,
        "pronouns": None,
    }

    with db.cursor() as cur:
        cur.execute(
            "SELECT id, is_enriched FROM users WHERE github_id = %s LIMIT 1;",
            (github_id,),
        )
        r1 = cur.fetchone()
        if r1:
            identity["user_id"] = r1[0]
            identity["is_enriched"] = bool(r1[1])
            identity["user_exists"] = True

            if identity["is_enriched"]:
                cur.execute(
                    """
                    SELECT
                        gender,
                        has_pronouns
                    FROM users WHERE github_id = %s LIMIT 1;
                    """,
                    (github_id,),
                )
                r2 = cur.fetchone()
                if r2:
                    identity["gender"] = r2[0]
                    identity["pronouns"] = r2[1]
    return identity


# Returns an array of user id's mapped to the specific usernames
def batchGetUserId(github_ids: list[int], db):
    with db.cursor() as cur:
        query = """
            SELECT id, github_id 
            FROM users 
            WHERE github_id = ANY(%s)
        """
        cur.execute(query, (github_ids,))
        rows = cur.fetchall()
        # Convert to a dict or list as needed
        return [user_id for user_id, _ in rows]
    return


# Deletes a specfic user from the DB
def deleteUser(github_id: int, db):
    with db.cursor() as cur:
        cur.execute(
            """
            DELETE FROM users
            WHERE github_id = %s;
            """,
            (github_id,),
        )
        db.commit()
        cur.close()
        logging.info(f"Deleted Github ID {github_id} From Database")
        return


# Update last_scraped for the passed in user in the DB
def finalizeUserScrape(github_id: int, private_count, min_sponsor_tier, db):

    scraped = datetime.now(timezone.utc)

    with db.cursor() as cur:
        cur.execute(
            """
            UPDATE users SET
                last_scraped = %s,
                private_sponsor_count = %s,
                min_sponsor_cost = %s     
            WHERE github_id = %s;
            """,
            (scraped, private_count, min_sponsor_tier, github_id),
        )
        db.commit()
        cur.close()
    return


def getGithubIDs(usernames):
    """
    Gets the GitHub database IDs for a list of usernames by batching
    GraphQL queries.
    """
    user_map = []
    # GitHub's GraphQL API has a node limit per query (usually 100).
    # We query for both user and organization for each username, so 2 nodes per name.
    # A batch size of 50 is safe (50 usernames * 2 nodes = 100 nodes).
    batch_size = 50

    for i in range(0, len(usernames), batch_size):
        batch = usernames[i : i + batch_size]

        # Dynamically build the query with aliases for each username
        query_parts = []
        for username in batch:
            # Sanitize username to be a valid GraphQL alias
            alias_username = f"_{username.replace('-', '_')}"
            query_parts.append(
                f"""
                user{alias_username}: user(login: "{username}") {{
                    databaseId
                    login
                }}
                org{alias_username}: organization(login: "{username}") {{
                    databaseId
                    login
                }}
            """
            )

        query = "query {" + " ".join(query_parts) + "}"

        # Make the single API call for the entire batch
        payload = {"query": query}
        response = postRequest(url=URL, json=payload)
        data = response.json().get("data", {})

        if not data:
            logging.warning(f"Received no data for user batch starting with {batch[0]}")
            continue

        # 3. Process the response for the batch
        for username in batch:
            alias_username = f"_{username.replace('-', '_')}"
            user_data = data.get(f"user{alias_username}")
            org_data = data.get(f"org{alias_username}")

            entity_data = user_data or org_data  # Pick the one that is not null

            if entity_data and entity_data.get("databaseId"):
                github_id = int(entity_data["databaseId"])
                user_map.append(github_id)
            else:
                logging.warning(
                    f"Could not find user or organization {username} on GitHub. Skipping."
                )
    print(user_map)
    return user_map
