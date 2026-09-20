import unittest

from minicut_agent.timeline_history import TimelineHistory
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.timeline_tools import TimelineToolRegistry


class TimelineToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.document = TimelineDocument.default()
        self.history = TimelineHistory(self.document)
        self.tools = TimelineToolRegistry(self.document, self.history)

    def test_insert_clip_increments_revision(self):
        result = self.tools.execute(
            "insert_clip",
            {
                "source": "film.mp4",
                "track_id": "V1",
                "source_in_ms": 0,
                "source_out_ms": 5000,
                "timeline_start_ms": 1000,
                "expected_revision": 0,
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["revision"], 1)
        self.assertEqual(len(self.document.clips), 1)

    def test_insert_clip_passes_v42_metadata(self):
        result = self.tools.execute(
            "insert_clip",
            {
                "source": "film.mp4",
                "track_id": "V2",
                "source_in_ms": 1000,
                "source_out_ms": 3000,
                "timeline_start_ms": 0,
                "unit_id": "N-001",
                "block_id": "B-001",
                "origin": "gemini_verified",
            },
        )
        self.assertTrue(result["ok"])
        clip = self.document.clips[0]
        self.assertEqual(clip.unit_id, "N-001")
        self.assertEqual(clip.block_id, "B-001")
        self.assertEqual(clip.origin, "gemini_verified")

    def test_stale_revision_is_rejected_without_mutation(self):
        result = self.tools.execute(
            "insert_clip",
            {
                "source": "film.mp4",
                "track_id": "V1",
                "source_in_ms": 0,
                "source_out_ms": 5000,
                "timeline_start_ms": 0,
                "expected_revision": 99,
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "stale_revision")
        self.assertEqual(self.document.clips, [])
        self.assertEqual(self.tools.revision, 0)

    def test_atomic_batch_rolls_back_if_one_action_fails(self):
        result = self.tools.execute_batch(
            [
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": "film.mp4",
                        "track_id": "V1",
                        "source_in_ms": 0,
                        "source_out_ms": 5000,
                        "timeline_start_ms": 0,
                        "group_id": "g1",
                    },
                },
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": "film.mp4",
                        "track_id": "NOT_A_TRACK",
                        "source_in_ms": 0,
                        "source_out_ms": 5000,
                        "timeline_start_ms": 0,
                        "group_id": "g1",
                    },
                },
            ],
            expected_revision=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(self.document.clips, [])
        self.assertEqual(self.tools.revision, 0)
        self.assertFalse(self.history.can_undo)

    def test_linked_speed_change_and_undo(self):
        batch = self.tools.execute_batch(
            [
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": "film.mp4",
                        "track_id": "V1",
                        "source_in_ms": 0,
                        "source_out_ms": 10000,
                        "timeline_start_ms": 0,
                        "group_id": "g1",
                    },
                },
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": "film.mp4",
                        "track_id": "A1",
                        "source_in_ms": 0,
                        "source_out_ms": 10000,
                        "timeline_start_ms": 0,
                        "group_id": "g1",
                    },
                },
            ]
        )
        self.assertTrue(batch["ok"])
        video = next(c for c in self.document.clips if c.track_id == "V1")

        speed = self.tools.execute(
            "set_speed",
            {
                "clip_id": video.id,
                "speed": 2.0,
                "expected_revision": 1,
            },
        )
        self.assertTrue(speed["ok"])
        self.assertEqual({c.speed for c in self.document.clips}, {2.0})

        undo = self.tools.execute("undo", {"expected_revision": 2})
        self.assertTrue(undo["ok"])
        self.assertEqual({c.speed for c in self.document.clips}, {1.0})

    def test_failed_mutation_preserves_existing_redo_chain(self):
        inserted = self.tools.execute(
            "insert_clip",
            {
                "source": "film.mp4",
                "track_id": "V1",
                "source_in_ms": 0,
                "source_out_ms": 5000,
                "timeline_start_ms": 0,
            },
        )
        self.assertTrue(inserted["ok"])
        self.assertTrue(
            self.tools.execute(
                "undo",
                {"expected_revision": self.tools.revision},
            )["ok"]
        )
        self.assertTrue(self.history.can_redo)

        failed = self.tools.execute(
            "insert_clip",
            {
                "source": "bad.mp4",
                "track_id": "NOT_A_TRACK",
                "source_in_ms": 0,
                "source_out_ms": 1000,
                "timeline_start_ms": 0,
                "expected_revision": self.tools.revision,
            },
        )
        self.assertFalse(failed["ok"])
        self.assertTrue(self.history.can_redo)

        redone = self.tools.execute(
            "redo",
            {"expected_revision": self.tools.revision},
        )
        self.assertTrue(redone["ok"])
        self.assertEqual(len(self.document.clips), 1)

    def test_locked_track_rejects_move_and_does_not_add_history(self):
        inserted = self.tools.execute(
            "insert_clip",
            {
                "source": "film.mp4",
                "track_id": "V1",
                "source_in_ms": 0,
                "source_out_ms": 5000,
                "timeline_start_ms": 0,
            },
        )
        clip_id = inserted["result"]["id"]
        lock = self.tools.execute(
            "set_track_lock",
            {"track_id": "V1", "locked": True},
        )
        self.assertTrue(lock["ok"])
        before_revision = self.tools.revision

        move = self.tools.execute(
            "move_clip",
            {
                "clip_id": clip_id,
                "track_id": "V1",
                "timeline_start_ms": 1000,
                "expected_revision": before_revision,
            },
        )
        self.assertFalse(move["ok"])
        self.assertEqual(move["error"]["code"], "validation_error")
        self.assertEqual(self.tools.revision, before_revision)
        self.assertEqual(self.document.clip(clip_id).timeline_start_ms, 0)


if __name__ == "__main__":
    unittest.main()
