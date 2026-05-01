from backend.utils.db_conn import db_connection
from flask import Blueprint, jsonify
from psycopg2.extras import RealDictCursor

# Endpoint for Users
stats_bp = Blueprint("stats", __name__)


# Fetch all users from the database
@stats_bp.route("/api/stats/brief", methods=["GET"])
def get_stats():
    try:
        # Establish connection to database
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
           WITH sponsored_counts AS (
    SELECT sponsored_id AS user_id, COUNT(DISTINCT sponsor_id) AS public_sponsors
    FROM sponsorship
    GROUP BY sponsored_id
),
sponsoring_counts AS (
    SELECT sponsor_id AS user_id, COUNT(DISTINCT sponsored_id) AS total_sponsoring
    FROM sponsorship
    GROUP BY sponsor_id
),
sponsorship_counts AS (
    SELECT 
        u.id AS user_id,
        COALESCE(sc.public_sponsors, 0) + COALESCE(u.private_sponsor_count, 0) AS total_sponsors,
        COALESCE(gc.total_sponsoring, 0) AS total_sponsoring
    FROM users u
    LEFT JOIN sponsored_counts sc ON u.id = sc.user_id
    LEFT JOIN sponsoring_counts gc ON u.id = gc.user_id
),
graph_edges_cte AS (
    SELECT s.sponsor_id, s.sponsored_id
    FROM sponsorship s
    JOIN users sponsor ON sponsor.id = s.sponsor_id
    JOIN users sponsored ON sponsored.id = s.sponsored_id
    WHERE sponsor.is_enriched IS TRUE
      AND sponsored.is_enriched IS TRUE
      AND s.sponsor_id IS NOT NULL
      AND s.sponsored_id IS NOT NULL
),
graph_users_cte AS (
    SELECT s.sponsor_id AS user_id
    FROM sponsorship s
    JOIN users u ON u.id = s.sponsor_id
    WHERE u.is_enriched IS TRUE
      AND s.sponsor_id IS NOT NULL

    UNION

    SELECT s.sponsored_id AS user_id
    FROM sponsorship s
    JOIN users u ON u.id = s.sponsored_id
    WHERE u.is_enriched IS TRUE
      AND s.sponsored_id IS NOT NULL
),
total_users_cte AS (
    SELECT COUNT(DISTINCT u.id) AS total_users
    FROM users u
    JOIN sponsorship_counts sc ON u.id = sc.user_id
    WHERE u.is_enriched IS TRUE
      AND (sc.total_sponsors > 0 OR sc.total_sponsoring > 0)
),
total_sponsorships_cte AS (
    SELECT COUNT(*) as total_sponsorships
    FROM sponsorship
),
top_sponsoring_cte AS (
    SELECT u.username, u.avatar_url, sc.total_sponsoring
    FROM sponsorship_counts sc
    JOIN users u ON u.id = sc.user_id
    ORDER BY sc.total_sponsoring DESC
    LIMIT 1
),
top_sponsored_cte AS (
    SELECT u.username, u.avatar_url, sc.total_sponsors
    FROM sponsorship_counts sc
    JOIN users u ON u.id = sc.user_id
    ORDER BY sc.total_sponsors DESC
    LIMIT 1
)
SELECT
    (SELECT total_users FROM total_users_cte) AS total_users,
    (SELECT total_sponsorships FROM total_sponsorships_cte) AS total_sponsorships,
    (SELECT COUNT(*) FROM graph_users_cte) AS graph_nodes,
    (SELECT COUNT(*) FROM graph_edges_cte) AS graph_sponsorships,
    (SELECT row_to_json(top_sponsoring_cte) FROM top_sponsoring_cte) AS top_sponsoring,
    (SELECT row_to_json(top_sponsored_cte) FROM top_sponsored_cte) AS top_sponsored;
            """
        )
        stats = cur.fetchone()
        cur.close()
        conn.close()

        return jsonify(stats), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stats_bp.route("/api/user-stats", methods=["GET"])
def get_location_dist():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH sponsored_user_ids AS (
                -- First, get a distinct list of all user IDs involved in sponsorships
                SELECT sponsored_id AS user_id FROM sponsorship
                UNION
                SELECT sponsor_id AS user_id FROM sponsorship
            ),
            user_gender_by_country AS (
                -- Then, join that list with the users table
                SELECT
                    u.location AS country,
                    -- Use the more efficient FILTER clause for conditional aggregation
                    COUNT(*) FILTER (WHERE u.gender = 'Male') AS male,
                    COUNT(*) FILTER (WHERE u.gender = 'Female') AS female,
                    COUNT(*) FILTER (WHERE u.gender = 'Other') AS other,
                    COUNT(*) FILTER (WHERE u.gender = 'Unknown' OR u.gender IS NULL) AS unknown
                FROM users u
                JOIN sponsored_user_ids s ON u.id = s.user_id
                WHERE u.location IS NOT NULL
                GROUP BY u.location
            )
            SELECT
                ug.country,
                json_build_object(
                    'male', ug.male,
                    'female', ug.female,
                    'other', ug.other,
                    'unknown', ug.unknown
                ) AS "genderData"
            FROM user_gender_by_country ug
            ORDER BY (ug.male + ug.female + ug.other + ug.unknown) DESC;
            """
        )
        stats = cur.fetchall()
        cur.close()
        conn.close()

        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Get Gender Distribution
@stats_bp.route("/api/gender-stats", methods=["GET"])
def get_gender_stats():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH active_users AS (
            SELECT sponsor_id AS user_id FROM sponsorship
            UNION
            SELECT sponsored_id AS user_id FROM sponsorship
            )
            SELECT 
            COALESCE(u.gender, 'Unknown') AS gender,
            COUNT(*) AS count
            FROM users u
            JOIN active_users au ON u.id = au.user_id
            WHERE (u.type = 'User') AND (u.has_pronouns = TRUE)
            GROUP BY COALESCE(u.gender, 'Unknown');
            """
        )
        stats = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stats_bp.route("/api/user-sponsorship-stats", methods=["GET"])
def get_sponsorship_stats():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH user_roles AS (
            SELECT 
                user_id,
                BOOL_OR(role = 'sponsor') AS is_sponsoring,
                BOOL_OR(role = 'sponsored') AS is_sponsored
            FROM (
                SELECT sponsor_id AS user_id, 'sponsor' AS role FROM sponsorship
                UNION ALL
                SELECT sponsored_id AS user_id, 'sponsored' AS role FROM sponsorship
                UNION ALL
                SELECT id AS user_id, 'sponsored' AS role FROM users WHERE private_sponsor_count > 0
            ) AS roles
            GROUP BY user_id
            )
            SELECT
            COUNT(*) FILTER (
                WHERE is_sponsoring AND NOT is_sponsored
                AND EXISTS (
                SELECT 1 FROM users u WHERE u.id = user_roles.user_id AND u.type = 'User'
                )
            ) AS sponsoring_only,
            COUNT(*) FILTER (
                WHERE is_sponsored AND NOT is_sponsoring
                AND EXISTS (
                SELECT 1 FROM users u WHERE u.id = user_roles.user_id AND u.type = 'User'
                )
            ) AS sponsored_only,
            COUNT(*) FILTER (
                WHERE is_sponsoring AND is_sponsored
                AND EXISTS (
                SELECT 1 FROM users u WHERE u.id = user_roles.user_id AND u.type = 'User'
                )
            ) AS both
            FROM user_roles;
            """
        )
        stats = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stats_bp.route("/api/brief-user-stats", methods=["GET"])
def get_user_brief_stats():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH user_type_users AS (
                SELECT id, username, avatar_url, location, private_sponsor_count
                FROM users
                WHERE type = 'User'
            ),
            sponsored_counts AS (
                SELECT sponsored_id AS user_id, COUNT(DISTINCT sponsor_id) AS public_sponsors
                FROM sponsorship
                GROUP BY sponsored_id
            ),
            sponsoring_counts AS (
                SELECT sponsor_id AS user_id, COUNT(DISTINCT sponsored_id) AS total_sponsoring
                FROM sponsorship
                GROUP BY sponsor_id
            ),
            sponsorship_counts AS (
                SELECT 
                    u.id AS user_id,
                    COALESCE(sc.public_sponsors, 0) + COALESCE(u.private_sponsor_count, 0) AS total_sponsors,
                    COALESCE(gc.total_sponsoring, 0) AS total_sponsoring
                FROM user_type_users u
                LEFT JOIN sponsored_counts sc ON u.id = sc.user_id
                LEFT JOIN sponsoring_counts gc ON u.id = gc.user_id
            ),
            top_sponsored AS (
                SELECT 
                    u.username,
                    u.avatar_url,
                    sc.total_sponsors
                FROM user_type_users u
                JOIN sponsorship_counts sc ON u.id = sc.user_id
                ORDER BY sc.total_sponsors DESC
                LIMIT 1
            ),
            top_sponsoring AS (
                SELECT 
                    u.username,
                    u.avatar_url,
                    sc.total_sponsoring
                FROM user_type_users u
                JOIN sponsorship_counts sc ON u.id = sc.user_id
                ORDER BY sc.total_sponsoring DESC
                LIMIT 1
            ),
            country_sponsored_counts AS (
                -- Include users who have public sponsors OR only private sponsors
                SELECT 
                    u.location AS country,
                    COUNT(DISTINCT u.id) AS sponsored_users
                FROM user_type_users u
                JOIN sponsorship_counts sc ON u.id = sc.user_id
                WHERE u.location IS NOT NULL
                AND sc.total_sponsors > 0
                GROUP BY u.location
            ),
            top_country AS (
                SELECT country, sponsored_users
                FROM country_sponsored_counts
                ORDER BY sponsored_users DESC
                LIMIT 1
            )
            SELECT
                (SELECT COUNT(DISTINCT u.id) 
                FROM user_type_users u
                JOIN sponsorship_counts sc ON u.id = sc.user_id
                WHERE sc.total_sponsors > 0 OR sc.total_sponsoring > 0) AS total_users,
                (SELECT row_to_json(top_sponsored) FROM top_sponsored) AS most_sponsored_user,
                (SELECT row_to_json(top_sponsoring) FROM top_sponsoring) AS most_sponsoring_user,
                (SELECT row_to_json(top_country) FROM top_country) AS top_country;
            """
        )
        results = cur.fetchall()
        stats = results[0] or None
        cur.close()
        conn.close()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stats_bp.route("/api/gender-distribution-table", methods=["GET"])
def get_gender_distribution_table():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH active_users AS (
                -- This CTE combines all logic to find every unique, enriched user involved in sponsorships.
                -- It is the definitive list of users we should analyze.
                SELECT s.sponsored_id AS user_id
                FROM public.sponsorship s
                JOIN public.users u ON s.sponsored_id = u.id
                WHERE u.is_enriched IS TRUE AND u.type = 'User'
                
                UNION
                
                SELECT s.sponsor_id AS user_id
                FROM public.sponsorship s
                JOIN public.users u ON s.sponsor_id = u.id
                WHERE u.is_enriched IS TRUE AND u.type = 'User'

                UNION

                SELECT id AS user_id
                FROM public.users
                WHERE private_sponsor_count > 0 AND is_enriched IS TRUE AND type = 'User'
            ),
            gender_counts AS (
                -- Now, join the definitive list of active users with the users table to get their gender data.
                SELECT
                    u.has_pronouns,
                    COUNT(*) AS total_in_group,
                    -- Use the more efficient FILTER clause for conditional aggregation
                    COUNT(*) FILTER (WHERE u.gender = 'Male') AS male_count,
                    COUNT(*) FILTER (WHERE u.gender = 'Female') AS female_count,
                    COUNT(*) FILTER (WHERE u.gender = 'Other') AS other_count,
                    COUNT(*) FILTER (WHERE u.gender = 'Unknown') AS unknown_count
                FROM
                    public.users u
                JOIN
                    active_users au ON u.id = au.user_id
                GROUP BY
                    u.has_pronouns
            )
            -- Final SELECT to format the data for the table, calculating percentages.
            SELECT
                -- Use a CASE statement to create a descriptive label for each row.
                CASE
                    WHEN has_pronouns = TRUE THEN 'Pronouns Specified'
                    WHEN has_pronouns = FALSE THEN 'Pronouns Not Specified (Inferred)'
                    ELSE 'Not Applicable'
                END AS "Category",
                
                -- Format each column as 'Count (Percentage%)'
                CONCAT(male_count, ' (', ROUND((male_count::numeric / total_in_group) * 100, 2), '%)') AS "Male",
                CONCAT(female_count, ' (', ROUND((female_count::numeric / total_in_group) * 100, 2), '%)') AS "Female",
                CONCAT(other_count, ' (', ROUND((other_count::numeric / total_in_group) * 100, 2), '%)') AS "Other",
                CONCAT(unknown_count, ' (', ROUND((unknown_count::numeric / total_in_group) * 100, 2), '%)') AS "Unknown",
                total_in_group AS "Total"
            FROM
                gender_counts
            ORDER BY
                has_pronouns DESC;
            """
        )
        stats = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stats_bp.route("/api/location-sponsorship-roles", methods=["GET"])
def get_location_sponsorship_roles():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH sponsored_entities AS (
            -- All unique ENRICHED entities (users/orgs) being sponsored
            SELECT s.sponsored_id AS entity_id
            FROM public.sponsorship s
            JOIN public.users u ON s.sponsored_id = u.id
            WHERE u.is_enriched IS TRUE
            UNION
            SELECT id AS entity_id
            FROM public.users
            WHERE private_sponsor_count > 0 AND is_enriched IS TRUE
            ),
            sponsoring_entities AS (
            -- All unique ENRICHED entities (users/orgs) who are sponsoring
            SELECT DISTINCT s.sponsor_id AS entity_id
            FROM public.sponsorship s
            JOIN public.users u ON s.sponsor_id = u.id
            WHERE u.is_enriched IS TRUE
            ),
            both_roles_entities AS (
            -- ENRICHED entities that appear in both sets
            SELECT entity_id FROM sponsored_entities
            INTERSECT
            SELECT entity_id FROM sponsoring_entities
            ),
            active_entities AS (
                -- Create a definitive list of all entities we care about
                SELECT entity_id FROM sponsored_entities
                UNION 
                SELECT entity_id FROM sponsoring_entities
            ),
            location_role_counts AS (
            -- Categorize each entity by role and then aggregate by location only
            SELECT
                u.location,
                COUNT(*) FILTER (
                WHERE u.id IN (SELECT entity_id FROM sponsored_entities) AND u.id NOT IN (SELECT entity_id FROM both_roles_entities)
                ) AS sponsored_only,
                COUNT(*) FILTER (
                WHERE u.id IN (SELECT entity_id FROM sponsoring_entities) AND u.id NOT IN (SELECT entity_id FROM both_roles_entities)
                ) AS sponsoring_only,
                COUNT(*) FILTER (
                WHERE u.id IN (SELECT entity_id FROM both_roles_entities)
                ) AS both_roles
            FROM public.users u
            JOIN active_entities ae ON u.id = ae.entity_id
            WHERE u.location IS NOT NULL
            GROUP BY u.location
            )
            -- Final report assembly for the top 6 locations with combined totals
            SELECT
            location,
            sponsored_only,
            sponsoring_only,
            both_roles,
            (sponsored_only + sponsoring_only + both_roles) AS total_active
            FROM location_role_counts
            ORDER BY total_active DESC
            """
        )
        stats = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stats_bp.route("/api/sponsorship-roles-by-type", methods=["GET"])
def get_sponsorship_roles_by_type():
    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            WITH sponsored_users AS (
            -- All unique ENRICHED users/orgs being sponsored
            SELECT s.sponsored_id AS user_id
            FROM public.sponsorship s
            JOIN public.users u ON s.sponsored_id = u.id
            WHERE u.is_enriched IS TRUE
            UNION
            SELECT id AS user_id
            FROM public.users
            WHERE private_sponsor_count > 0 AND is_enriched IS TRUE
            ),
            sponsoring_users AS (
            -- All unique ENRICHED users/orgs who are sponsoring
            SELECT DISTINCT s.sponsor_id AS user_id
            FROM public.sponsorship s
            JOIN public.users u ON s.sponsor_id = u.id
            WHERE u.is_enriched IS TRUE
            ),
            both_roles_users AS (
            -- ENRICHED users/orgs that appear in both sets
            SELECT user_id FROM sponsored_users
            INTERSECT
            SELECT user_id FROM sponsoring_users
            ),
            -- Count users/orgs that are ONLY sponsored
            sponsored_only_counts AS (
            SELECT
                u.type,
                COUNT(su.user_id) AS total
            FROM sponsored_users su
            JOIN public.users u ON su.user_id = u.id
            WHERE su.user_id NOT IN (SELECT user_id FROM both_roles_users)
            GROUP BY u.type
            ),
            -- Count users/orgs that are ONLY sponsoring
            sponsoring_only_counts AS (
            SELECT
                u.type,
                COUNT(su.user_id) AS total
            FROM sponsoring_users su
            JOIN public.users u ON su.user_id = u.id
            WHERE su.user_id NOT IN (SELECT user_id FROM both_roles_users)
            GROUP BY u.type
            ),
            -- Count users/orgs that have BOTH roles
            both_roles_counts AS (
            SELECT
                u.type,
                COUNT(bu.user_id) AS total
            FROM both_roles_users bu
            JOIN public.users u ON bu.user_id = u.id
            GROUP BY u.type
            )
            -- Final report assembly
            SELECT
            'User' AS entity_type,
            COALESCE((SELECT total FROM sponsored_only_counts WHERE type = 'User'), 0) AS active_sponsored_only,
            COALESCE((SELECT total FROM sponsoring_only_counts WHERE type = 'User'), 0) AS active_sponsoring_only,
            COALESCE((SELECT total FROM both_roles_counts WHERE type = 'User'), 0) AS active_both
            UNION ALL
            SELECT
            'Organization' AS entity_type,
            COALESCE((SELECT total FROM sponsored_only_counts WHERE type = 'Organization'), 0),
            COALESCE((SELECT total FROM sponsoring_only_counts WHERE type = 'Organization'), 0),
            COALESCE((SELECT total FROM both_roles_counts WHERE type = 'Organization'), 0)
            UNION ALL
            SELECT
            'Overall Total' AS entity_type,
            (SELECT SUM(total) FROM sponsored_only_counts),
            (SELECT SUM(total) FROM sponsoring_only_counts),
            (SELECT SUM(total) FROM both_roles_counts);
            """
        )
        stats = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
