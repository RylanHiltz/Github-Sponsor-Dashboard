from backend.db.queries.users import batchGetUserId
from psycopg2.extras import execute_values
import logging

# This module provides functions for managing sponsorship relationships between users in the database.


# Batch create a sponsored relations for a specific user
def createSponsors(sponsored, sponsor_arr, db):
    entries = [(sponsor, sponsored) for sponsor in sponsor_arr]

    with db.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sponsorship (sponsor_id, sponsored_id)
            VALUES (%s, %s)
            ON CONFLICT (sponsor_id, sponsored_id) DO NOTHING
            """,
            entries,
        )
    db.commit()
    cur.close()
    return


# Batch create all sponsoring relations for a specific user
def createSponsoring(sponsor, sponsored_arr, db):

    entries = [(sponsor, sponsored) for sponsored in sponsored_arr]

    with db.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sponsorship (sponsor_id, sponsored_id)
            VALUES (%s, %s)
            ON CONFLICT (sponsor_id, sponsored_id) DO NOTHING
            """,
            entries,
        )
    db.commit()
    cur.close()
    return


def _ensure_users_exist(db, github_ids: list[int]):
    ids = list({i for i in github_ids if i is not None})
    if not ids:
        return
    with db.cursor() as cur:
        tuples = [(gid,) for gid in ids]
        execute_values(
            cur,
            """
            INSERT INTO users (github_id)
            VALUES %s
            ON CONFLICT (github_id) DO NOTHING
            """,
            tuples,
        )
    db.commit()


# Handles comparison logic between old sponsors and newly crawled, removing where applicable
def syncSponsors(user_id, latest_sponsor_ids, db):
    """
    user_id: GitHub ID of the sponsored user
    latest_sponsor_ids: iterable of GitHub IDs of sponsors
    """
    # Ensure both ends exist as users
    _ensure_users_exist(db, list(latest_sponsor_ids) + [user_id])

    # Map GitHub IDs -> internal users.id
    # batchGetUserId should return a list of users.id in the same order
    sponsored_row_id = batchGetUserId([user_id], db)[0]
    latest_sponsor_row_ids = set(batchGetUserId(list(latest_sponsor_ids), db))

    # Read existing edges using internal IDs
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT s.sponsor_id
            FROM sponsorship s
            WHERE s.sponsored_id = %s
            """,
            (sponsored_row_id,),
        )
        existing_sponsor_row_ids = {row[0] for row in cur.fetchall()}

    sponsors_to_remove = existing_sponsor_row_ids - latest_sponsor_row_ids
    sponsors_to_add = latest_sponsor_row_ids - existing_sponsor_row_ids

    if sponsors_to_remove:
        with db.cursor() as cur:
            # Insert into History
            cur.execute(
                """
                INSERT INTO sponsorship_history (sponsor_id, sponsored_id, started_at, ended_at)
                SELECT sponsor_id, sponsored_id, created_at, NOW()
                FROM sponsorship
                WHERE sponsored_id = %s AND sponsor_id = ANY(%s)
                """,
                (sponsored_row_id, list(sponsors_to_remove)),
            )

            # Delete from Active
            cur.execute(
                """
                DELETE FROM sponsorship
                WHERE sponsored_id = %s AND sponsor_id = ANY(%s)
            """,
                (sponsored_row_id, list(sponsors_to_remove)),
            )

    if sponsors_to_add:
        createSponsors(sponsored_row_id, sponsor_arr=list(sponsors_to_add), db=db)
        logging.info("Created Sponsor Relations")
    db.commit()
    return


def syncSponsorships(user_id, latest_sponsored_ids, db):
    """
    user_id: GitHub ID of the sponsor
    latest_sponsored_ids: iterable of GitHub IDs of users they sponsor
    """
    # Ensure both ends exist as users
    _ensure_users_exist(db, list(latest_sponsored_ids) + [user_id])

    # Map GitHub IDs -> internal users.id
    sponsor_row_id = batchGetUserId([user_id], db)[0]
    latest_sponsored_row_ids = set(batchGetUserId(list(latest_sponsored_ids), db))

    with db.cursor() as cur:
        cur.execute(
            """
            SELECT s.sponsored_id
            FROM sponsorship s
            WHERE s.sponsor_id = %s
            """,
            (sponsor_row_id,),
        )
        existing_sponsored_row_ids = {row[0] for row in cur.fetchall()}

    sponsoring_to_remove = existing_sponsored_row_ids - latest_sponsored_row_ids
    sponsoring_to_add = latest_sponsored_row_ids - existing_sponsored_row_ids

    if sponsoring_to_remove:
        with db.cursor() as cur:
            # Insert into History
            cur.execute(
                """
                INSERT INTO sponsorship_history (sponsor_id, sponsored_id, started_at, ended_at)
                SELECT sponsor_id, sponsored_id, created_at, NOW()
                FROM sponsorship
                WHERE sponsor_id = %s AND sponsored_id = ANY(%s)
                """,
                (sponsor_row_id, list(sponsoring_to_remove)),
            )
            # Delete from Active
            cur.execute(
                """
                DELETE FROM sponsorship
                WHERE sponsor_id = %s AND sponsored_id = ANY(%s)
                """,
                (sponsor_row_id, list(sponsoring_to_remove)),
            )

    if sponsoring_to_add:
        createSponsoring(sponsor_row_id, sponsored_arr=list(sponsoring_to_add), db=db)
        logging.info("Created Sponsoring Relations")
    db.commit()
    return
