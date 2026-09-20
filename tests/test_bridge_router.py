import unittest

from minicut_agent.ai_plan import TimelinePlanManager
from minicut_agent.bridge import BridgeRouter
from minicut_agent.timeline_history import TimelineHistory
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.timeline_tools import TimelineToolRegistry


class BridgeRouterTests(unittest.TestCase):
    def setUp(self):
        self.doc = TimelineDocument.default()
        self.history = TimelineHistory(self.doc)
        self.registry = TimelineToolRegistry(self.doc, self.history)
        self.mutations = 0
        self.plan_changes = 0
        self.playhead = 0
        self.plan_manager = TimelinePlanManager(self.registry)
        self.router = BridgeRouter(
            self.registry,
            state_provider=lambda: {"playhead_ms": self.playhead},
            seek_handler=self._seek,
            allowed_sources_provider=lambda: {"film.mp4"},
            mutation_callback=self._mutated,
            plan_manager=self.plan_manager,
            plan_callback=self._plan_changed,
        )

    def _mutated(self):
        self.mutations += 1

    def _plan_changed(self):
        self.plan_changes += 1

    def _seek(self, milliseconds):
        self.playhead = milliseconds
        return {"playhead_ms": milliseconds}

    def test_state_contains_timeline_revision_and_bridge_tools(self):
        state = self.router.state()
        self.assertEqual(state["revision"], 0)
        self.assertEqual(state["playhead_ms"], 0)
        self.assertIn("insert_clip", state["bridge_tools"])
        self.assertIn("batch", state["bridge_tools"])
        self.assertIn("propose_plan", state["bridge_tools"])

    def test_insert_rejects_unimported_source(self):
        result = self.router.execute(
            {
                "tool": "insert_clip",
                "args": {
                    "source": "secret.mp4",
                    "track_id": "V1",
                    "source_in_ms": 0,
                    "source_out_ms": 1000,
                    "timeline_start_ms": 0,
                },
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "source_not_allowed")
        self.assertEqual(self.doc.clips, [])

    def test_direct_external_mutation_requires_review(self):
        result = self.router.execute(
            {
                "tool": "insert_clip",
                "args": {
                    "source": "film.mp4",
                    "track_id": "V1",
                    "source_in_ms": 0,
                    "source_out_ms": 1000,
                    "timeline_start_ms": 0,
                    "expected_revision": 0,
                },
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "review_required")
        self.assertEqual(self.registry.revision, 0)
        self.assertEqual(self.mutations, 0)
        self.assertEqual(self.doc.clips, [])

    def test_seek_is_ui_command_not_timeline_revision(self):
        result = self.router.execute({"tool": "seek", "args": {"time_ms": 2500}})
        self.assertTrue(result["ok"])
        self.assertEqual(self.playhead, 2500)
        self.assertEqual(self.registry.revision, 0)
        self.assertEqual(self.mutations, 0)

    def test_plan_proposal_is_review_only(self):
        result = self.router.execute(
            {
                "tool": "propose_plan",
                "args": {
                    "title": "Use candidate",
                    "expected_revision": 0,
                    "unit_id": "N-001",
                    "actions": [
                        {
                            "tool": "insert_clip",
                            "args": {
                                "source": "film.mp4",
                                "track_id": "V1",
                                "source_in_ms": 0,
                                "source_out_ms": 1000,
                                "timeline_start_ms": 0,
                            },
                        }
                    ],
                },
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(self.doc.clips, [])
        self.assertEqual(self.registry.revision, 0)
        self.assertEqual(self.plan_changes, 1)
        self.assertIsNotNone(self.plan_manager.pending)

    def test_plan_cannot_reference_unimported_source(self):
        result = self.router.execute(
            {
                "tool": "propose_plan",
                "args": {
                    "title": "Bad candidate",
                    "expected_revision": 0,
                    "actions": [
                        {
                            "tool": "insert_clip",
                            "args": {
                                "source": "secret.mp4",
                                "track_id": "V1",
                                "source_in_ms": 0,
                                "source_out_ms": 1000,
                                "timeline_start_ms": 0,
                            },
                        }
                    ],
                },
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "source_not_allowed")
        self.assertIsNone(self.plan_manager.pending)

    def test_direct_external_batch_requires_review(self):
        result = self.router.batch(
            {
                "expected_revision": 0,
                "actions": [
                    {
                        "tool": "insert_clip",
                        "args": {
                            "source": "film.mp4",
                            "track_id": "V1",
                            "source_in_ms": 0,
                            "source_out_ms": 1000,
                            "timeline_start_ms": 0,
                        },
                    }
                ],
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "review_required")
        self.assertEqual(self.doc.clips, [])
        self.assertEqual(self.registry.revision, 0)


if __name__ == "__main__":
    unittest.main()
