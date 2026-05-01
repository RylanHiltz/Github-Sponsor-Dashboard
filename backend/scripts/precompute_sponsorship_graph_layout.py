from collections import Counter, defaultdict, deque
from math import cos, pi, sin, sqrt

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from backend.db.sqlalchemy import Base, SessionLocal, get_engine
from backend.models.orm import Sponsorship, SponsorshipLayout


GOLDEN_ANGLE = pi * (3.0 - sqrt(5.0))


def _connected_components(edges: list[tuple[int, int]]) -> list[list[int]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for sponsor_id, sponsored_id in edges:
        adjacency[sponsor_id].add(sponsored_id)
        adjacency[sponsored_id].add(sponsor_id)

    seen: set[int] = set()
    components: list[list[int]] = []
    for node_id in sorted(adjacency):
        if node_id in seen:
            continue
        queue = deque([node_id])
        seen.add(node_id)
        component: list[int] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))

    return sorted(components, key=len, reverse=True)


def _layout_rows(edges: list[tuple[int, int]]) -> list[dict[str, float | int]]:
    in_degrees = Counter(sponsored_id for _, sponsored_id in edges)
    out_degrees = Counter(sponsor_id for sponsor_id, _ in edges)
    components = _connected_components(edges)
    rows: list[dict[str, float | int]] = []

    component_count = max(1, len(components))
    for component_index, component in enumerate(components):
        center_angle = component_index * GOLDEN_ANGLE
        center_radius = 260.0 * sqrt(component_index)
        center_x = center_radius * cos(center_angle)
        center_y = center_radius * sin(center_angle)
        center_z = (component_index - component_count / 2.0) * 16.0

        component_size = max(1, len(component))
        component_radius = 80.0 + 9.0 * sqrt(component_size)
        ordered_nodes = sorted(
            component,
            key=lambda user_id: (
                -(in_degrees[user_id] + out_degrees[user_id]),
                user_id,
            ),
        )

        for node_index, user_id in enumerate(ordered_nodes):
            angle = node_index * GOLDEN_ANGLE
            radius = component_radius * sqrt((node_index + 0.5) / component_size)
            degree_balance = out_degrees[user_id] - in_degrees[user_id]
            rows.append(
                {
                    "user_id": user_id,
                    "x": center_x + radius * cos(angle),
                    "y": center_y + radius * sin(angle),
                    "z": center_z + degree_balance * 4.0,
                }
            )

    return rows


def precompute_layout() -> int:
    Base.metadata.create_all(bind=get_engine(), tables=[SponsorshipLayout.__table__])
    session = SessionLocal()
    try:
        edge_rows = session.execute(
            select(Sponsorship.sponsor_id, Sponsorship.sponsored_id).where(
                Sponsorship.sponsor_id.is_not(None),
                Sponsorship.sponsored_id.is_not(None),
            )
        ).all()
        edges = [
            (int(sponsor_id), int(sponsored_id))
            for sponsor_id, sponsored_id in edge_rows
        ]
        rows = _layout_rows(edges)

        session.execute(delete(SponsorshipLayout))
        if rows:
            statement = insert(SponsorshipLayout).values(rows)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[SponsorshipLayout.user_id],
                    set_={
                        "x": statement.excluded.x,
                        "y": statement.excluded.y,
                        "z": statement.excluded.z,
                        "updated_at": func.now(),
                    },
                )
            )
        session.commit()
        return len(rows)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    count = precompute_layout()
    print(f"Precomputed sponsorship graph layout for {count} nodes.")
