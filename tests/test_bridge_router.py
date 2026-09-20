import unittest

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
        self.playhead = 0
        self.router = BridgeRouter(
            self.registry,
            state_provider=lambda: {"playhead_ms": self.playhead},
            seek_handler=self._seek,
            allowed_sources_provider=lambda: {"film.mp4"},
            mutation_callback=self._mutated,
        )

    def _mutated(self):
        self.mutations += 1

    def _seek(self, milliseconds):
        self.playhead = milliseconds
        return {"playhead_ms": milliseconds}

    def test_state_contains_timeline_revision_and_bridge_tools(self):
        state = self.router.state()
        self.assertEqual(state["revision"], 0)
        self.assertEqual(state["playhead_ms"], 0)
        self.assertIn("insert_clip", state["bridge_tools"])
        self.assertIn("batch", state["bridge_tools"])

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

    def test_insert_allowed_source_mutates_registry(self):
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
        self.assertTrue(result["ok"])
        self.assertEqual(self.registry.revision, 1)
        self.assertEqual(self.mutations, 1)

    def test_seek_is_ui_command_not_timeline_revision(self):
        result = self.router.execute({"tool": "seek", "args": {"time_ms": 2500}})
        self.assertTrue(result["ok"])
        self.assertEqual(self.playhead, 2500)
        self.assertEqual(self.registry.revision, 0)
        self.assertEqual(self.mutations, 0)

    def test_batch_rejects_disallowed_source_before_mutation(self):
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
                    },
                    {
                        "tool": "insert_clip",
                        "args": {
                            "source": "not-imported.mp4",
                            "track_id": "A1",
                            "source_in_ms": 0,
                            "source_out_ms": 1000,
                            "timeline_start_ms": 0,
                        },
                    },
                ],
            }
        )
        self.assertFalse(result["ok"])
        self.assertEqual(self.doc.clips, [])
        self.assertEqual(self.registry.revision, 0)


if __name__ == "__main__":
    unittest.main()
