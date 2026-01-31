from backend.utils.db_conn import db_connection
from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor
import json
import pandas as pd
from datetime import date

# Endpoint for Users
users_bp = Blueprint("users", __name__)

# Simple in-memory storage for rate limiting exports (IP -> {date, count})
daily_export_counts = {}


def _execute_user_query(request_args, limit, offset):
    """
    Shared helper to build and execute the user search/filter query.
    """
    conn = db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        search_query = request.args.get("search", "")
        # Filters passed in from the frontend to query the user data
        filters = {
            "gender": request.args.getlist("gender"),
            "type": request.args.getlist("type"),
            "location": request.args.getlist("location"),
        }
        sort_fields = request.args.getlist("sortField")
        sort_orders = request.args.getlist("sortOrder")

        # Data dictionary of sortable columns in the user data
        # keys mapped to actual DB columns
        sortable_fields_map = {
            "username": "u.username",
            "name": "u.name",
            "followers": "u.followers",
            "following": "u.following",
            "public_repos": "u.public_repos",
            "total_sponsors": "total_sponsors",
            "total_sponsoring": "total_sponsoring",
            "estimated_earnings": "estimated_earnings",
        }

        # Whitelist filter keys (defensive)
        allowed_filters = {"gender", "type", "location"}

        where_clauses = []
        order_parts = []
        params = []

        # Check if we are sorting by a calculated field
        calculated_fields = {"total_sponsors", "total_sponsoring", "estimated_earnings"}
        is_calculated_sort = any(field in calculated_fields for field in sort_fields)

        # Default sort is total_sponsors (calculated), so if no sort provided, treat as calculated
        if not sort_fields:
            is_calculated_sort = True

        # Handle search query (parameterized)
        if search_query:
            where_clauses.append(
                "to_tsvector('english', u.username || ' ' || u.name) @@ plainto_tsquery('english', %s)"
            )
            params.append(search_query)

            # If searching, we often prioritize rank, which is dynamic, but lets stick to logic
            if not sort_fields:
                # If search exists but no sort specified, usually we sort by rank (native-ish)
                # But existing logic forced total_sponsors. Let's keep existing logic structure roughly.
                pass

        # Handle filters
        for key, values in filters.items():
            if key not in allowed_filters:
                continue
            if not values:
                continue
            if "None" in values:
                values = [v for v in values if v != "None"]
                if values:
                    placeholders = ",".join(["%s"] * len(values))
                    where_clauses.append(
                        f"(u.{key} IN ({placeholders}) OR u.{key} IS NULL)"
                    )
                    params.extend(values)
                else:
                    where_clauses.append(f"u.{key} IS NULL")
            else:
                placeholders = ",".join(["%s"] * len(values))
                where_clauses.append(f"u.{key} IN ({placeholders})")
                params.extend(values)

        # Always require enriched users
        where_clauses.append("u.is_enriched IS TRUE")

        # Build ORDER BY clause parts
        if sort_fields and sort_orders:
            for field, order in zip(sort_fields, sort_orders):
                col_name = sortable_fields_map.get(field)
                if col_name:
                    direction = "DESC" if order == "descend" else "ASC"

                    # For search, we might want rank, but following existing pattern:
                    if field not in calculated_fields:
                        order_parts.append(f"{col_name} {direction}")
                    else:
                        order_parts.append(f"{field} {direction}")

        # Tiebreaker
        order_parts.append("u.id ASC")

        # Base WHERE for users table
        base_where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # The condition that requires joining sponsorship:
        # (sc.total_sponsors > 0 OR sc.total_sponsoring > 0)
        # We can rewrite this as EXISTS subqueries for the Native path.
        exists_condition = """
        (
            COALESCE(u.private_sponsor_count, 0) > 0 
            OR EXISTS (SELECT 1 FROM sponsorship s_check WHERE s_check.sponsored_id = u.id)
            OR EXISTS (SELECT 1 FROM sponsorship s_check WHERE s_check.sponsor_id = u.id)
        )
        """

        if not is_calculated_sort:
            # === FAST PATH: Native Column Sort (Name, Followers, etc) ===
            # 1. Filter and Sort IDs on `users` table only
            # 2. Limit/Offset
            # 3. Join logic ONLY for the resulting subset

            # Add strict search ordering if applicable
            full_order_clause = "ORDER BY "
            if search_query:
                full_order_clause += f"ts_rank_cd(to_tsvector('english', u.username || ' ' || u.name), plainto_tsquery('english', %s)) DESC, "

            full_order_clause += ", ".join(order_parts)

            # NOTE: We need to inject search param again for the rank order if it exists
            final_params = list(params)
            if search_query:
                # Add search param for the Rank Order clause
                # params structure: [search_where, filters..., search_rank, limit, offset]
                final_params.append(search_query)

            # Combine WHERE
            if base_where:
                final_where = f"{base_where} AND {exists_condition}"
            else:
                final_where = f"WHERE {exists_condition}"

            data_query = f"""
            WITH median_cost AS (
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY min_sponsor_cost) AS value
                FROM users WHERE min_sponsor_cost > 0
            ),
            subset_users AS (
                SELECT u.id, COUNT(*) OVER() as total_count
                FROM users u
                {final_where}
                {full_order_clause}
                LIMIT %s OFFSET %s
            )
            SELECT 
                u.id, u.name, u.username, u.type, u.avatar_url, u.profile_url,
                u.gender, u.location, u.public_repos, u.public_gists,
                u.followers, u.following, u.hireable, u.min_sponsor_cost, 
                -- Calculate counts purely for this page of users
                (COALESCE(u.private_sponsor_count, 0) + 
                 (SELECT COUNT(DISTINCT s1.sponsor_id) FROM sponsorship s1 WHERE s1.sponsored_id = u.id)
                ) as total_sponsors,
                (SELECT COUNT(DISTINCT s2.sponsored_id) FROM sponsorship s2 WHERE s2.sponsor_id = u.id) as total_sponsoring,
                su.total_count
            FROM subset_users su
            JOIN users u ON u.id = su.id
            CROSS JOIN median_cost mc
            -- We need to re-apply order to ensure result set matches the CTE order
            {full_order_clause}
            """

            # Add limit/offset to params
            final_params.append(limit)
            final_params.append(offset)

            cur.execute(data_query, tuple(final_params))

        else:
            # === SLOW PATH: Calculated Column Sort (Total Sponsors, Earnings) ===
            # Fallback to existing logic but Optimized:
            # We push the base user filters INTO a specific user selection first
            # to avoid joining sponsorship for users who don't match gender/location.

            # Re-construct Order Clause for standard path
            full_order_clause = "ORDER BY "
            order_params_local = []
            if search_query:
                full_order_clause += f"ts_rank_cd(to_tsvector('english', u.username || ' ' || u.name), plainto_tsquery('english', %s)) DESC, "
                order_params_local.append(search_query)

            full_order_clause += ", ".join(order_parts)

            # Add the complex filter for showing only active users
            # This must be applied AFTER counts are known in the CTE strategy
            # or we use the logic below.

            # Optimized "Heavy" Query
            data_query = f"""
            WITH median_cost AS (
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY min_sponsor_cost) AS value
                FROM users WHERE min_sponsor_cost > 0
            ),
            sponsorship_counts AS (
                SELECT 
                    u.id,
                    COALESCE(COUNT(DISTINCT s1.sponsor_id), 0) + COALESCE(u.private_sponsor_count, 0) AS total_sponsors,
                    (SELECT COUNT(DISTINCT s2.sponsored_id) FROM sponsorship s2 WHERE s2.sponsor_id = u.id) AS total_sponsoring
                FROM users u
                LEFT JOIN sponsorship s1 ON s1.sponsored_id = u.id
                {base_where} -- PUSH FILTERS DOWN: Only calculate for relevant users
                GROUP BY u.id, u.private_sponsor_count
            )
            SELECT 
                u.id, u.name, u.username, u.type, u.avatar_url, u.profile_url,
                u.gender, u.location, u.public_repos, u.public_gists,
                u.followers, u.following, u.hireable, u.min_sponsor_cost, 
                sc.total_sponsors,
                sc.total_sponsoring,
                ( 
                LEAST(
                    (CASE WHEN u.min_sponsor_cost > 0 THEN u.min_sponsor_cost ELSE mc.value END), 
                    mc.value
                ) * sc.total_sponsors
                ) AS estimated_earnings,
                COUNT(*) OVER() AS total_count
            FROM users u
            JOIN sponsorship_counts sc ON sc.id = u.id
            CROSS JOIN median_cost mc
            WHERE (sc.total_sponsors > 0 OR sc.total_sponsoring > 0)
            {full_order_clause}
            LIMIT %s OFFSET %s;
            """

            # Params: [search?, filters..., search_param_for_rank?, limit, offset]
            final_params = list(params)
            final_params.extend(order_params_local)
            final_params.append(limit)
            final_params.append(offset)

            cur.execute(data_query, tuple(final_params))

        rows = cur.fetchall()

        total_count = 0
        ordered_users = []
        if rows:
            total_count = rows[0]["total_count"]

            # If estimated_earnings wasn't computed by the query (fast path),
            # compute median once so we can calculate earnings in Python.
            need_median = "estimated_earnings" not in rows[0]
            median_value = None
            if need_median:
                cur.execute(
                    "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY min_sponsor_cost) AS median "
                    "FROM users WHERE min_sponsor_cost > 0"
                )
                mrow = cur.fetchone()
                median_value = mrow["median"] if mrow else None

            for row in rows:
                est_earn = row.get("estimated_earnings")
                if est_earn is None and "total_sponsors" in row:
                    # compute a reasonable fallback using median and min_sponsor_cost
                    ms_cost = row.get("min_sponsor_cost")
                    effective_cost = (
                        ms_cost if ms_cost and ms_cost > 0 else (median_value or 0)
                    )
                    if median_value is not None:
                        effective_cost = min(effective_cost, median_value)
                    est_earn = (effective_cost or 0) * (row.get("total_sponsors") or 0)
                # Reconstruct Dict
                user_obj = {
                    "id": row["id"],
                    "name": row["name"],
                    "username": row["username"],
                    "type": row["type"],
                    "gender": row["gender"],
                    "hireable": row["hireable"],
                    "location": row["location"],
                    "avatar_url": row["avatar_url"],
                    "profile_url": row["profile_url"],
                    "following": row["following"],
                    "followers": row["followers"],
                    "public_repos": row["public_repos"],
                    "public_gists": row["public_gists"],
                    "total_sponsors": row["total_sponsors"],
                    "total_sponsoring": row["total_sponsoring"],
                    "min_sponsor_cost": row["min_sponsor_cost"],
                    "estimated_earnings": est_earn,
                }
                ordered_users.append(user_obj)

        return {"total": total_count, "users": ordered_users}

    finally:
        cur.close()
        conn.close()


# Fetch all users from the database (Standard Pagination)
@users_bp.route("/api/users", methods=["GET"])
def get_users():
    try:
        # Get pagination parameters from query string
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        offset = (page - 1) * per_page

        result = _execute_user_query(request.args, per_page, offset)
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Export users (Dedicated endpoint with start_row and rate limiting)
@users_bp.route("/api/users/export", methods=["GET"])
def get_export_users():
    try:
        # 2. Offset Calculation
        start_row = request.args.get("start_row", default=1, type=int)
        count = request.args.get("count", default=1000, type=int)

        # Ensure sensible limits (Strictly enforce 2000 max to match frontend)
        count = min(count, 2000)
        offset = max(0, start_row - 1)

        result = _execute_user_query(request.args, count, offset)
        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Endpoint to retrieve a list of unique country locations sorted alphabetically
@users_bp.route("/api/users/location", methods=["GET"])
def get_locations():
    """
    Fetches a distinct, sorted list of user locations.
    The database query planner should use a 'skip scan' on the index for efficiency.
    """
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        location_query = "SELECT DISTINCT location FROM users WHERE location IS NOT NULL ORDER BY location ASC;"
        cur.execute(location_query)
        location_list = [row["location"] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify(location_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


#
@users_bp.route("/api/user/<int:user_id>", methods=["GET"])
def get_user(user_id):

    # Establish connection to database
    conn = db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        data_query = """
        WITH user_details AS (
            SELECT * FROM users WHERE id = %s
        ),
        activity_summary AS (
            SELECT
                SUM((ua.activity_data->>'commits')::BIGINT) AS total_commits,
                SUM((ua.activity_data->>'pull_requests')::BIGINT) AS total_pull_requests,
                SUM((ua.activity_data->>'issues')::BIGINT) AS total_issues,
                SUM((ua.activity_data->>'reviews')::BIGINT) AS total_reviews,
                (
                    SELECT json_agg(
                        json_build_object(
                            'year', year,
                            'activity_data', activity_data
                        ) ORDER BY year DESC
                    )
                    FROM user_activity
                    WHERE user_id = ua.user_id
                ) AS yearly_activity_data
            FROM
                user_activity AS ua
            WHERE
                ua.user_id = %s
            GROUP BY
                ua.user_id
        ),
        sponsor_data AS (
            SELECT 
                u.id,
                COALESCE(COUNT(DISTINCT s1.sponsor_id), 0) + 
                COALESCE(u.private_sponsor_count, 0) AS total_sponsors,
                COALESCE((
                    SELECT COUNT(DISTINCT s2.sponsored_id)
                    FROM sponsorship s2
                    WHERE s2.sponsor_id = u.id
                ), 0) AS total_sponsoring
            FROM users u
            LEFT JOIN sponsorship s1 ON s1.sponsored_id = u.id
            WHERE u.id = %s
            GROUP BY u.id, u.private_sponsor_count
        )
        SELECT
            row_to_json(ud) AS user_data,
            row_to_json(as_sum) AS activity_data,
            row_to_json(sd) AS sponsor_data
        FROM
            user_details ud
        LEFT JOIN activity_summary as_sum ON true
        LEFT JOIN sponsor_data sd ON true;
        """
        cur.execute(data_query, (user_id, user_id, user_id))
        user_data = cur.fetchone()
        cur.close()
        conn.close()

        if user_data and user_data["user_data"]:
            response_data = user_data["user_data"]
            if user_data["activity_data"]:
                response_data.update(user_data["activity_data"])
            if user_data["sponsor_data"]:
                response_data.update(user_data["sponsor_data"])
            return jsonify(response_data), 200
        else:
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/api/user/<int:user_id>/sponsorship-history", methods=["GET"])
def get_sponsorship_history_route(user_id):
    conn = db_connection()
    try:
        # 1. Get Interval from Query Params (Default to 'W')
        interval_param = request.args.get("interval", "W").upper()
        # Map 'week'/'month' strings to Pandas frequency aliases if needed, or just strict check
        freq_alias = "ME" if interval_param == "M" else "W"
        # Note: Pandas 2.2+ prefers 'ME' (Month End) over 'M'. Use 'M' if on older pandas.

        with conn.cursor() as cur:
            # Union Query: Get both closed history and current active
            query = """
                SELECT h.started_at, h.ended_at
                FROM sponsorship_history h
                WHERE h.sponsored_id = %s
                UNION ALL
                SELECT s.created_at as started_at, NULL as ended_at
                FROM sponsorship s
                WHERE s.sponsored_id = %s
            """
            cur.execute(query, (user_id, user_id))
            rows = cur.fetchall()

        if not rows:
            return jsonify([]), 200

        # --- DATA PROCESSING WITH PANDAS ---
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=["started_at", "ended_at"])

        # FIX: Force UTC, then strip timezone info (.dt.tz_localize(None))
        # This ensures both columns are "timezone-naive" and can be joined/merged safely.
        df["started_at"] = pd.to_datetime(df["started_at"], utc=True).dt.tz_localize(
            None
        )
        df["ended_at"] = pd.to_datetime(df["ended_at"], utc=True).dt.tz_localize(None)

        # 2. Resample using the dynamic frequency
        new_sponsors = df.set_index("started_at").resample(freq_alias).size()
        lost_sponsors = (
            df[df["ended_at"].notnull()]
            .set_index("ended_at")
            .resample(freq_alias)
            .size()
        )

        # 3. Combine into one Timeline
        timeline = pd.DataFrame({"new": new_sponsors, "lost": lost_sponsors}).fillna(0)

        # 4. Calculate "Active Count" (Running Total)
        # Net change per week = New - Lost
        timeline["net_change"] = timeline["new"] - timeline["lost"]
        timeline["active_count"] = timeline["net_change"].cumsum()

        # 5. Format for JSON
        # Explicitly format the index to avoid Pylance inference errors with .dt accessor
        timeline.index = pd.to_datetime(timeline.index).strftime("%Y-%m-%d")

        # Reset index (which is now strings) to make 'date' a column
        final_df = timeline.reset_index()

        # Rename the first column (the index) to 'date' safely
        final_df.rename(columns={final_df.columns[0]: "date"}, inplace=True)

        # Ensure integers and handle negatives (vectorized clip)
        final_df["active_count"] = final_df["active_count"].clip(lower=0).astype(int)
        final_df["new"] = final_df["new"].astype(int)
        final_df["lost"] = final_df["lost"].astype(int)

        # Convert to list of dictionaries directly
        results = final_df[["date", "active_count", "new", "lost"]].to_dict(
            orient="records"
        )

        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
