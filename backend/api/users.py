from backend.utils.db_conn import db_connection
from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor
import json
import pandas as pd

# Endpoint for Users
users_bp = Blueprint("users", __name__)


# Fetch all users from the database
@users_bp.route("/api/users", methods=["GET"])
def get_users():

    # Establish connection to database
    conn = db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get pagination parameters from query string, with defaults
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        offset = (page - 1) * per_page
        # Search field passed in from the frontend to preform database search
        search_query = request.args.get("search", "")
        # Filters passed in from the frontend to query the user data
        filters = {
            "gender": request.args.getlist("gender"),
            "type": request.args.getlist("type"),
            "location": request.args.getlist("location"),
        }
        # Sorters passed in from the frontend to sort user data
        sort_fields = request.args.getlist("sortField")
        sort_orders = request.args.getlist("sortOrder")

        # Data dictionary of sortable columns in the user data
        sortable_fields = {
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
        order_params = []

        # Handle search query (parameterized)
        if search_query:
            where_clauses.append(
                "to_tsvector('english', u.username || ' ' || u.name) @@ plainto_tsquery('english', %s)"
            )
            params.append(search_query)

            # Re-add search ranking to the front of the order list
            search_rank_expression = "ts_rank_cd(to_tsvector('english', u.username || ' ' || u.name), plainto_tsquery('english', %s))"
            order_parts.append(f"{search_rank_expression} DESC")
            order_params.append(search_query)

        # Handle filters (build explicit placeholders for IN-lists)
        for key, values in filters.items():
            if key not in allowed_filters:
                continue  # ignore unexpected filter keys
            if not values:
                continue
            # treat string "None" as a request for NULL values
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

        # Always require enriched users with sponsor activity
        where_clauses.append("u.is_enriched IS TRUE")
        where_clauses.append("(sc.total_sponsors > 0 OR sc.total_sponsoring > 0)")
        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Build ORDER BY clause
        if sort_fields and sort_orders:
            for field, order in zip(sort_fields, sort_orders):
                col_name = sortable_fields.get(field)
                if col_name:
                    direction = "DESC" if order == "descend" else "ASC"
                    order_parts.append(f"{col_name} {direction}")

        # Always add id as the final tiebreaker for stable pagination
        order_parts.append("u.id ASC")
        order_clause = "ORDER BY " + ", ".join(order_parts)

        # Optizimed query to fetch all necessary data, while handling filtering and searching via the backend
        data_query = f"""
        -- Handles counting bi-directional sponsorships for each user who is enriched
        WITH sponsorship_counts AS (
            SELECT 
            u.id AS user_id,
            COALESCE(COUNT(DISTINCT s1.sponsor_id), 0) + 
            COALESCE(u.private_sponsor_count, 0) AS total_sponsors,
            COALESCE((
                SELECT COUNT(DISTINCT s2.sponsored_id)
                FROM sponsorship s2
                WHERE s2.sponsor_id = u.id
            ), 0) AS total_sponsoring
            FROM users u
            LEFT JOIN sponsorship s1 ON s1.sponsored_id = u.id
            GROUP BY u.id, u.private_sponsor_count
        ),
        
        -- Grabs the median minimum sponsorship cost from the users table for calculation of estimated earnings 
        median_cost AS (
            SELECT 
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY min_sponsor_cost) AS value
            FROM users
            WHERE min_sponsor_cost > 0
        )
        
        -- Selects all attributes to be displayed in the leaderboard from the users table
        SELECT 
            u.id, u.name, u.username, u.type, u.avatar_url, u.profile_url,
            u.gender, u.location, u.public_repos, u.public_gists,
            u.followers, u.following, u.hireable, u.min_sponsor_cost, 
            sc.total_sponsors,
            sc.total_sponsoring,
            ( 
            
            -- Checks if the users minimum sponsorship price is greater than 0, if so use that value, else use median
            -- If the users minimum sponsorship price is greater than the median, the median is substituted for the price
            -- This is multiplied by the total # of sponsors to get the estimated MINIMUM monthly earnings the user earns
            LEAST(
                (CASE WHEN u.min_sponsor_cost > 0 THEN u.min_sponsor_cost ELSE mc.value END), 
                mc.value
            ) * sc.total_sponsors
            ) AS estimated_earnings,
            COUNT(*) OVER() AS total_count
            FROM users u
            JOIN sponsorship_counts sc ON sc.user_id = u.id
            CROSS JOIN median_cost mc
            {where_clause}
            {order_clause}
        LIMIT %s OFFSET %s;
        """

        # Inject request params + order params + pagination params
        final_params = params + order_params + [per_page, offset]
        cur.execute(data_query, tuple(final_params))
        rows = cur.fetchall()

        total_count = 0
        ordered_users = []
        if rows:
            # The total_count is the same for every row, so we can grab it from the first one.
            total_count = rows[0]["total_count"]
            for row in rows:
                ordered_users.append(
                    {
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
                        "estimated_earnings": row["estimated_earnings"],
                    }
                )
        response_data = {
            "total": total_count,
            "users": ordered_users,
        }
        return jsonify(response_data), 200

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
