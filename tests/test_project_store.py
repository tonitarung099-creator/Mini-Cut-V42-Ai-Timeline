import json
import tempfile
import unittest
from pathlib import Path

from minicut_agent.project_store import (
    apply_project,
    load_project,
    parse_project_data,
    save_project,
)
from minicut_agent.timeline_history import TimelineHistory
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.timeline_tools import TimelineToolRegistry


class ProjectStoreTests(unittest.TestCase):
    def _project(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            speed=0.5,
            group_id="g1",
            label="Film",
            unit_id="J-001",
            block_id="B-001",
            origin="gemini_verified",
        )
        doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            speed=0.5,
            group_id="g1",
            label="Film audio",
            unit_id="J-001",
            block_id="B-001",
            origin="gemini_verified",
        )
        return doc, video

    def test_round_trip_and_apply_preserves_document_identity(self):
        doc, _ = self._project()
        history = TimelineHistory(doc)
        registry = TimelineToolRegistry(doc, history)
        registry.restore_revision(7)
        workflow = {
            "schema_version": 1,
            "active_block": "B-001",
            "active_unit": "N-002",
            "units": {"N-002": {"status": "working"}},
            "checkpoints": {},
        }

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project.mcutv42.json"
            save_project(
                path,
                doc,
                revision=registry.revision,
                playhead_ms=6500,
                media=[{"source": "film.mp4", "duration_ms": 60000}],
                workflow=workflow,
            )
            snapshot = load_project(path)

        target = TimelineDocument.default()
        target_history = TimelineHistory(target)
        target_registry = TimelineToolRegistry(target, target_history)
        identity = id(target)
        target_history.checkpoint()
        target_history.commit_checkpoint()

        apply_project(
            snapshot,
            document=target,
            history=target_history,
            registry=target_registry,
        )

        self.assertEqual(id(target), identity)
        self.assertEqual(target_registry.revision, 7)
        self.assertEqual(snapshot.playhead_ms, 6500)
        self.assertEqual(len(target.clips), 2)
        self.assertFalse(target_history.can_undo)
        self.assertEqual(snapshot.workflow["active_unit"], "N-002")
        self.assertEqual(target.clips[0].unit_id, "J-001")
        self.assertEqual(target.clips[0].block_id, "B-001")
        self.assertEqual(target.clips[0].origin, "gemini_verified")

    def test_invalid_clip_track_is_rejected(self):
        raw = {
            "schema_version": 1,
            "timeline_revision": 0,
            "playhead_ms": 0,
            "tracks": [{"id": "V1", "name": "V1", "kind": "video"}],
            "clips": [{
                "id": "c1",
                "source": "film.mp4",
                "track_id": "A404",
                "source_in_ms": 0,
                "source_out_ms": 1000,
                "timeline_start_ms": 0,
            }],
            "media": [],
            "workflow": {},
        }
        with self.assertRaises(ValueError):
            parse_project_data(raw)

    def test_unknown_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_project_data({"schema_version": 99})

    def test_missing_media_is_reported_not_fatal(self):
        raw = {
            "schema_version": 1,
            "timeline_revision": 0,
            "playhead_ms": 0,
            "tracks": [{"id": "V1", "name": "V1", "kind": "video"}],
            "clips": [],
            "media": [{"source": "__definitely_missing_media__.mp4", "duration_ms": 10}],
            "workflow": {},
        }
        snapshot = parse_project_data(raw)
        self.assertIn("__definitely_missing_media__.mp4", snapshot.missing_sources)


if __name__ == "__main__":
    unittest.main()
