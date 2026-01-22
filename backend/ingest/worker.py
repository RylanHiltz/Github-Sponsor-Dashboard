# DB Queries
from backend.db.queries.queue import (
    getFirstInQueue,
    batchAddQueue,
    batchRequeue,
    updateStatus,
    enqueueStaleUsers,
    # checkStatus,
)
from backend.db.queries.users import (
    createUser,
    enrichUser,
    findUser,
    batchCreateUser,
    finalizeUserScrape,
)
from backend.db.queries.sponsors import (
    syncSponsors,
    syncSponsorships,
)
from backend.db.queries.user_activity import (
    getUserActivity,
    refreshActivityCheck,
)

# Ingest/Scraper
from backend.ingest.utils import get_sponsorships, getSponsorableUsers
from backend.ingest.init_check import (
    load_worker_state,
    update_worker_state,
)

# Authentication And Database
import psycopg2
from backend.utils.db_conn import db_connection
from backend.ingest.use_auth import get_auth, is_auth_expiring_soon

# Logging Imports
import time
import datetime
from datetime import datetime as date
import logging
from backend.logs.logger_config import init_logger, log_header

MAX_PRIORITY = 10


class IngestWorker:
    def run(self):
        """
        Main worker program to ingest, scrape and and insert data from Github API to database.

        Function Flow
        -----
        - Establish neccessary connections to database and logger.
        - On first run, create `worker_state.json` to track initialization status and last run time.
        - Enter main `while True` loop:
            1.  **State & Seeding**: Load worker state. If it's the first run or has been a long time, seed the queue by fetching all "Sponsorable" users from GitHub.
            2.  **Authentication**: Check if the GitHub auth token is expiring and refresh it if needed.
            3.  **Periodic Tasks**: Every 4 hours, re-establish the database connection and enqueue any "stale" users (not scraped in 7 days) for reprocessing.
            4.  **Fetch from Queue**: Get the highest-priority user from the queue. If the queue is empty, attempt to re-seed.
            5.  **Enrich/Create User**: Check the user's status in the database. If they don't exist, create them. If they exist but lack full details, enrich them using GitHub's REST API.
            6.  **Crawl Sponsorships**: Fetch the user's sponsors and the users they are sponsoring via the GraphQL API.
            7.  **Adjust Priority & Enqueue New Users**:
                - If new, unique users are found in the relationships, increment the current user's priority and add the new users to the queue.
                - If only existing relationships are found, the priority remains the same.
                - If no relationships are found, decrement the priority.
            8.  **Sync Data**: Update the `sponsorship` table with the latest relationships and collect the user's historical activity data if needed.
            9.  **Finalize**: Update the user's status to 'completed' in the queue and record the `last_scraped` timestamp.
            10. **Error Handling**: Catch and log database connection errors or other exceptions, with built-in reconnection logic and graceful shutdown.
        """

        # Establish database connection & logger
        init_logger()
        self.conn = db_connection()
        log_header("Worker has Started")

        # Start rescraping timer
        last_stale_check = time.time()

        while True:
            # Load the worker state
            start = time.time()
            state = load_worker_state()
            init_run, last_init_run = state.get("init_run"), state.get("last_init_run")
            elapsed: datetime

            # Parse last_init_run which is stored as an ISO 8601 string (e.g. 2025-08-24T18:21:35.226820)
            if last_init_run:
                try:
                    last_init_run = date.fromisoformat(last_init_run)
                except Exception:
                    # Fallback for strict parsing with microseconds
                    last_init_run = date.strptime(last_init_run, "%Y-%m-%dT%H:%M:%S.%f")
                # Total time sice the last run
                elapsed = date.now() - last_init_run
            else:
                elapsed = None

            # Else if time since is none or older than 1 year, treat this as an initial run
            if last_init_run is None or (
                date.now() - last_init_run
            ) > datetime.timedelta(days=365):
                getSponsorableUsers(self.conn, True)
            # If time since last_init_run is older than 2 weeks, incremental collection
            elif elapsed > datetime.timedelta(weeks=2):
                getSponsorableUsers(self.conn, init_run)

            # Only reset the state if the worker completed an initial run prior
            if init_run == True:
                update_worker_state()

            check_auth = is_auth_expiring_soon()
            # If auth is close to expiration
            if check_auth is True:
                get_auth()

            # Check last_stale_check every 4 hours
            if time.time() - last_stale_check >= 14400:
                # Re-scrape users every week (if they have not been re-visited)
                enqueueStaleUsers(db=self.conn, days_old=7)
                last_stale_check = time.time()
                # Re-establish DB connection every 4 hours
                self.conn.close()
                self.conn = db_connection()
                logging.info(
                    "4 Hours Elapsed: Re-establishing Fresh Database Connection."
                )
            try:
                #  Fetch first user from queue
                data = getFirstInQueue(db=self.conn)

                # If all pending users have been scraped batch requeue all users
                if not data:
                    getSponsorableUsers(self.conn, init_run)
                    batchRequeue(db=self.conn)
                    continue

                github_id = data["github_id"]
                priority = data["priority"]

                log_header(f"SCRAPING CURRENT USER: Github ID {github_id} ")
                print(
                    f"\n\nProcessing user: Github ID {github_id} at priority: {priority}"
                )

                # Check if the user exists and if the user is enriched with REST API data
                identity = findUser(github_id=github_id, db=self.conn)
                # Safe unpacking with defaults
                user_id = identity.get("user_id")
                user_exists = bool(identity.get("user_exists", False))
                is_enriched = bool(identity.get("is_enriched", False))

                try:
                    # User exists in DB from previous sponsor relation
                    if user_exists and is_enriched == False:
                        # Enrich user metadata from Github API / gender inference
                        user = enrichUser(github_id, db=self.conn)
                        logging.info(
                            f"Processing User: Github ID {github_id} at priority: {priority}"
                        )
                    # User has already been scraped for their data once (prevents unwanted future updates)
                    elif user_exists and is_enriched == True:
                        user = enrichUser(
                            github_id,
                            db=self.conn,
                            enriched=is_enriched,
                            identity=identity,
                        )
                        logging.info(
                            f"User already enriched: Github ID {github_id} at priority: {priority}, Data has been refreshed."
                        )
                    # User does not exist in DB, create new user
                    elif not user_exists:
                        user, user_id = createUser(github_id, db=self.conn)
                        logging.info(
                            f"Creating User: Github ID {github_id} at priority: {priority}"
                        )
                except ValueError as e:
                    logging.warning(
                        "User has been deleted. They do not exist on github (sponsors if previously existed have been updated)"
                    )
                    continue

                # Defensive checks: ensure we actually have a user object and a DB user_id
                if user is None:
                    logging.warning(
                        f"No user data returned for Github ID {github_id}; skipping."
                    )
                    updateStatus(github_id=github_id, status="skipped", db=self.conn)
                    continue

                #  Crawl the user for sponsorship relations
                print("Getting Sponsorships from GraphQL API:")
                try:
                    sponsors, sponsoring, private_count, min_sponsor_tier = (
                        get_sponsorships(user.username, github_id, user.type)
                    )

                    # Only sync if we successfully got the FULL lists
                    syncSponsors(github_id, sponsors, self.conn)
                    syncSponsorships(github_id, sponsoring, self.conn)

                except Exception as e:
                    logging.error(
                        f"Skipping sync for {user.username} due to fetch error: {e}"
                    )
                    # Do NOT update last_scraped so it tries again later
                    continue

                # Create a list of only the unique github_ids
                # This is important if bi-directional sponsor relations exist
                unique_users = list(set(sponsors) | set(sponsoring))
                print(unique_users)

                # Batch create unique users who are not present in the table
                if unique_users:
                    # User was discovered with new users, increase priority of user
                    new_priority = min(int(priority) + 1, MAX_PRIORITY)

                    # Create placeholder users to conform to foreign key constraint
                    # Batch add users at a middle standing priority
                    batchCreateUser(unique_users, db=self.conn)
                    batchAddQueue(unique_users, priority=5, db=self.conn)

                    # Collect the user activity from the Github API ONLY if the specified user HAS a sponsor or is sponsoring
                    # Users without either dont need their user activity collected as they will not be shown in the dataset.
                    print(f"\nCollecting User Activity Data:")

                    # Checks if the user activity does not exist or is over 365 days old,
                    # otherwise skip this function due to it being quite resource intensive
                    refresh_activity = refreshActivityCheck(user_id, self.conn)
                    if refresh_activity:
                        getUserActivity(
                            github_id=github_id,
                            user_id=user_id,
                            user_type=user.type,
                            created_at=user.github_created_at,
                            db=self.conn,
                        )
                # If no new users were found, but existing sponsor/sponsoring relationships exist
                elif sponsors or sponsoring:
                    new_priority = priority
                # If no new users are found, and no sponsor relationships exist
                else:
                    # Decrement the priority for subsequent searches, with a floor of 1.
                    new_priority = max(int(priority) - 1, 1)

                # Update staus and priority of the crawled user
                updateStatus(
                    github_id=github_id,
                    status="completed",
                    db=self.conn,
                    priority=new_priority,
                )

                # Set last_scraped to the current time
                finalizeUserScrape(
                    github_id, private_count, min_sponsor_tier, db=self.conn
                )

                # Force commit to save the "completed" status immediately
                self.conn.commit()

                # Print the elapsed time taken to crawl the current user
                end = time.time()
                elapsed = end - start
                logging.info(
                    f"user Github ID {github_id} crawled: {elapsed:.2f} seconds elapsed"
                )
                time.sleep(1)  # Wait before checking queue again

            # Handle operational error thrown by DB
            except psycopg2.OperationalError as e:
                logging.warning(f"DB connection lost: {e}. Reconnecting...")
                self.conn = db_connection()
                continue
            # If another error occurs, log the error and stop the scraper
            except Exception as e:
                logging.error(f"Unhandled exception: {e}", exc_info=True)
                time.sleep(10)
                break


if __name__ == "__main__":
    worker = IngestWorker()
    worker.run()
