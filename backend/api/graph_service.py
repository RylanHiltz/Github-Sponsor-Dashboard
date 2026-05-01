from collections import Counter
from math import log1p
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.orm import Sponsorship, SponsorshipLayout, User


class MissingGraphLayoutError(RuntimeError):
    def __init__(self, missing_count: int, node_count: int):
        self.missing_count = missing_count
        self.node_count = node_count
        super().__init__(
            f"Precomputed graph layout is missing for {missing_count} of {node_count} nodes."
        )


def graph_node_size(in_degree: int) -> float:
    return max(1.0, min(12.0, log1p(in_degree) * 2.2))


def build_sponsorship_graph_snapshot(session: Session) -> dict[str, Any]:
    edge_rows = session.execute(
        select(Sponsorship.sponsor_id, Sponsorship.sponsored_id).where(
            Sponsorship.sponsor_id.is_not(None),
            Sponsorship.sponsored_id.is_not(None),
        )
    ).all()

    edges = [(int(sponsor_id), int(sponsored_id)) for sponsor_id, sponsored_id in edge_rows]
    node_ids = sorted({node_id for edge in edges for node_id in edge})

    if not node_ids:
        return {
            "nodeCount": 0,
            "edgeCount": 0,
            "ids": [],
            "usernames": [],
            "x": [],
            "y": [],
            "z": [],
            "size": [],
            "inDegree": [],
            "outDegree": [],
            "src": [],
            "dst": [],
        }

    layout_rows = session.execute(
        select(
            SponsorshipLayout.user_id,
            SponsorshipLayout.x,
            SponsorshipLayout.y,
            SponsorshipLayout.z,
        ).where(SponsorshipLayout.user_id.in_(node_ids))
    ).all()
    layout_by_user_id = {
        int(user_id): (float(x), float(y), float(z))
        for user_id, x, y, z in layout_rows
    }

    layout_node_ids = sorted(layout_by_user_id)
    missing_layout_count = len(node_ids) - len(layout_node_ids)
    if missing_layout_count:
        layout_node_id_set = set(layout_node_ids)
        edges = [
            (sponsor_id, sponsored_id)
            for sponsor_id, sponsored_id in edges
            if sponsor_id in layout_node_id_set and sponsored_id in layout_node_id_set
        ]
        node_ids = sorted({node_id for edge in edges for node_id in edge})

    user_rows = session.execute(
        select(User.id, User.username).where(User.id.in_(node_ids))
    ).all()
    usernames_by_id = {int(user_id): username for user_id, username in user_rows}

    dense_index_by_id = {user_id: index for index, user_id in enumerate(node_ids)}
    in_degrees = Counter(sponsored_id for _, sponsored_id in edges)
    out_degrees = Counter(sponsor_id for sponsor_id, _ in edges)

    x_values: list[float] = []
    y_values: list[float] = []
    z_values: list[float] = []
    sizes: list[float] = []
    in_degree_values: list[int] = []
    out_degree_values: list[int] = []
    usernames: list[str] = []

    for user_id in node_ids:
        x, y, z = layout_by_user_id[user_id]
        in_degree = in_degrees[user_id]
        out_degree = out_degrees[user_id]
        x_values.append(x)
        y_values.append(y)
        z_values.append(z)
        sizes.append(graph_node_size(in_degree))
        in_degree_values.append(in_degree)
        out_degree_values.append(out_degree)
        usernames.append(usernames_by_id.get(user_id) or f"user-{user_id}")

    return {
        "nodeCount": len(node_ids),
        "edgeCount": len(edges),
        "omittedNodeCount": missing_layout_count,
        "ids": node_ids,
        "usernames": usernames,
        "x": x_values,
        "y": y_values,
        "z": z_values,
        "size": sizes,
        "inDegree": in_degree_values,
        "outDegree": out_degree_values,
        "src": [dense_index_by_id[sponsor_id] for sponsor_id, _ in edges],
        "dst": [dense_index_by_id[sponsored_id] for _, sponsored_id in edges],
    }
