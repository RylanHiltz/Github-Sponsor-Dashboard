import unittest
from unittest.mock import Mock, patch

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.graph import graph_bp
from backend.api.graph_service import build_sponsorship_graph_snapshot
from backend.db.sqlalchemy import Base
from backend.models.orm import Sponsorship, SponsorshipLayout, User


class SponsorshipGraphSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _add_user(self, user_id, username):
        self.session.add(
            User(
                id=user_id,
                username=username,
                profile_url=f"https://github.com/{username}",
                is_enriched=True,
            )
        )

    def test_snapshot_maps_edges_to_dense_indexes_and_degrees(self):
        self._add_user(10, "sponsor-a")
        self._add_user(20, "sponsored-b")
        self._add_user(30, "sponsor-c")
        self.session.add_all(
            [
                Sponsorship(id=1, sponsor_id=10, sponsored_id=20),
                Sponsorship(id=2, sponsor_id=30, sponsored_id=20),
                Sponsorship(id=3, sponsor_id=10, sponsored_id=30),
                Sponsorship(id=4, sponsor_id=None, sponsored_id=20),
                Sponsorship(id=5, sponsor_id=20, sponsored_id=None),
                SponsorshipLayout(user_id=10, x=1.0, y=2.0, z=3.0),
                SponsorshipLayout(user_id=20, x=4.0, y=5.0, z=6.0),
                SponsorshipLayout(user_id=30, x=7.0, y=8.0, z=9.0),
            ]
        )
        self.session.commit()

        snapshot = build_sponsorship_graph_snapshot(self.session)

        self.assertEqual(snapshot["nodeCount"], 3)
        self.assertEqual(snapshot["edgeCount"], 3)
        self.assertEqual(snapshot["ids"], [10, 20, 30])
        self.assertEqual(snapshot["usernames"], ["sponsor-a", "sponsored-b", "sponsor-c"])
        self.assertEqual(
            snapshot["profileUrls"],
            [
                "https://github.com/sponsor-a",
                "https://github.com/sponsored-b",
                "https://github.com/sponsor-c",
            ],
        )
        self.assertEqual(snapshot["src"], [0, 2, 0])
        self.assertEqual(snapshot["dst"], [1, 1, 2])
        self.assertEqual(snapshot["inDegree"], [0, 2, 1])
        self.assertEqual(snapshot["outDegree"], [2, 0, 1])
        self.assertTrue(all(0 <= value < snapshot["nodeCount"] for value in snapshot["src"]))
        self.assertTrue(all(0 <= value < snapshot["nodeCount"] for value in snapshot["dst"]))

    def test_missing_layout_omits_stale_nodes_instead_of_failing(self):
        self._add_user(1, "sponsor")
        self._add_user(2, "sponsored")
        self.session.add(Sponsorship(id=1, sponsor_id=1, sponsored_id=2))
        self.session.add(SponsorshipLayout(user_id=1, x=0.0, y=0.0, z=0.0))
        self.session.commit()

        snapshot = build_sponsorship_graph_snapshot(self.session)

        self.assertEqual(snapshot["nodeCount"], 1)
        self.assertEqual(snapshot["edgeCount"], 0)
        self.assertEqual(snapshot["omittedNodeCount"], 1)
        self.assertEqual(snapshot["ids"], [1])

    def test_empty_graph_returns_empty_arrays(self):
        snapshot = build_sponsorship_graph_snapshot(self.session)

        self.assertEqual(snapshot["nodeCount"], 0)
        self.assertEqual(snapshot["edgeCount"], 0)
        for key in ("ids", "usernames", "x", "y", "z", "size", "inDegree", "outDegree", "src", "dst"):
            self.assertEqual(snapshot[key], [])

    def test_snapshot_omits_unenriched_users_from_graph_nodes(self):
        self._add_user(1, "enriched-sponsor")
        self.session.add(
            User(
                id=2,
                username="unenriched-sponsored",
                profile_url="https://github.com/unenriched-sponsored",
                is_enriched=False,
            )
        )
        self.session.add(Sponsorship(id=1, sponsor_id=1, sponsored_id=2))
        self.session.add(SponsorshipLayout(user_id=1, x=0.0, y=0.0, z=0.0))
        self.session.commit()

        snapshot = build_sponsorship_graph_snapshot(self.session)

        self.assertEqual(snapshot["nodeCount"], 1)
        self.assertEqual(snapshot["edgeCount"], 0)
        self.assertEqual(snapshot["ids"], [1])


class SponsorshipGraphRouteTests(unittest.TestCase):
    def test_snapshot_route_returns_graph_payload(self):
        app = Flask(__name__)
        app.register_blueprint(graph_bp)
        fake_session = Mock()

        with patch("backend.api.graph.SessionLocal", return_value=fake_session), patch(
            "backend.api.graph.build_sponsorship_graph_snapshot",
            return_value={"nodeCount": 0, "edgeCount": 0, "omittedNodeCount": 2},
        ):
            response = app.test_client().get("/api/graph/sponsorships/snapshot")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["omittedNodeCount"], 2)
        fake_session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
