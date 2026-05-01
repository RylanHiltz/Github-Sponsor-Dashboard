from flask import Blueprint, jsonify
from sqlalchemy.exc import OperationalError

from backend.api.graph_service import (
    MissingGraphLayoutError,
    build_sponsorship_graph_snapshot,
)
from backend.db.sqlalchemy import SessionLocal


graph_bp = Blueprint("graph", __name__)


@graph_bp.route("/api/graph/sponsorships/snapshot", methods=["GET"])
def get_sponsorship_graph_snapshot():
    session = SessionLocal()
    try:
        return jsonify(build_sponsorship_graph_snapshot(session)), 200
    except MissingGraphLayoutError as exc:
        return (
            jsonify(
                {
                    "error": "Sponsorship graph layout has not been precomputed.",
                    "detail": str(exc),
                    "missing_nodes": exc.missing_count,
                    "node_count": exc.node_count,
                }
            ),
            503,
        )
    except OperationalError:
        return (
            jsonify(
                {
                    "error": "Database unavailable while loading sponsorship graph.",
                    "detail": "Check database connectivity, then rerun the graph request.",
                }
            ),
            503,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        session.close()
