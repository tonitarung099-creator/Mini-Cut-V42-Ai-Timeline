import unittest

from minicut_agent.timeline_history import TimelineHistory
from minicut_agent.timeline_model import TimelineDocument


class TimelineDocumentTests(unittest.TestCase):
    def test_default_tracks(self):
        doc = TimelineDocument.default()
        self.assertEqual([t.id for t in doc.tracks], ["V2", "V1", "A2", "A1", "SUB"])

    def test_insert_and_duration(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            speed=0.5,
        )
        self.assertEqual(clip.timeline_duration_ms, 20000)
        self.assertEqual(clip.timeline_end_ms, 25000)
        self.assertEqual(doc.duration_ms, 25000)

    def test_move_rejects_negative_start(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
        )
        with self.assertRaises(ValueError):
            doc.move_clip(clip.id, timeline_start_ms=-1)

    def test_move_rejects_cross_kind_track(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
        )
        with self.assertRaises(ValueError):
            doc.move_clip(clip.id, track_id="A1")

    def test_linked_move_preserves_av_sync(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=10000,
            timeline_start_ms=1000,
            group_id="g1",
        )
        audio = doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=0,
            source_out_ms=10000,
            timeline_start_ms=1000,
            group_id="g1",
        )
        doc.move_linked(video.id, timeline_start_ms=4000, track_id="V2")
        self.assertEqual(video.timeline_start_ms, 4000)
        self.assertEqual(audio.timeline_start_ms, 4000)
        self.assertEqual(video.track_id, "V2")
        self.assertEqual(audio.track_id, "A1")

    def test_split_linked_splits_video_and_audio(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            group_id="g1",
        )
        doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            group_id="g1",
        )

        created = doc.split_linked_at(video.id, 9000)
        self.assertEqual(len(created), 2)
        self.assertEqual(len(doc.clips), 4)
        left_video = doc.clip(video.id)
        right_video = next(c for c in created if c.track_id == "V1")
        self.assertEqual(left_video.source_out_ms, 5000)
        self.assertEqual(right_video.source_in_ms, 5000)
        self.assertEqual(right_video.timeline_start_ms, 9000)
        self.assertNotEqual(left_video.group_id, right_video.group_id)

    def test_remove_linked_removes_av_pair(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
            group_id="g1",
        )
        doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
            group_id="g1",
        )
        removed = doc.remove_linked(video.id)
        self.assertEqual(len(removed), 2)
        self.assertEqual(doc.clips, [])

    def test_linked_left_trim_keeps_video_audio_aligned(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            speed=2.0,
            group_id="g1",
        )
        audio = doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            speed=2.0,
            group_id="g1",
        )
        doc.trim_linked(video.id, edge="left", timeline_ms=7000)
        self.assertEqual(video.timeline_start_ms, 7000)
        self.assertEqual(audio.timeline_start_ms, 7000)
        self.assertEqual(video.source_in_ms, 5000)
        self.assertEqual(audio.source_in_ms, 5000)

    def test_linked_right_trim_keeps_video_audio_aligned(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            group_id="g1",
        )
        audio = doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=1000,
            source_out_ms=11000,
            timeline_start_ms=5000,
            group_id="g1",
        )
        doc.trim_linked(video.id, edge="right", timeline_ms=9000)
        self.assertEqual(video.source_out_ms, 5000)
        self.assertEqual(audio.source_out_ms, 5000)
        self.assertEqual(video.timeline_end_ms, 9000)
        self.assertEqual(audio.timeline_end_ms, 9000)

    def test_trim_rejects_position_outside_clip(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=1000,
        )
        with self.assertRaises(ValueError):
            doc.trim_linked(clip.id, edge="right", timeline_ms=7000)

    def test_preview_maps_timeline_to_trimmed_source_time(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=10000,
            source_out_ms=30000,
            timeline_start_ms=5000,
            speed=2.0,
        )
        self.assertEqual(clip.source_position_at(5000), 10000)
        self.assertEqual(clip.source_position_at(9000), 18000)
        self.assertIs(doc.video_clip_at(9000), clip)

    def test_preview_prefers_top_video_track(self):
        doc = TimelineDocument.default()
        lower = doc.insert_clip(
            source="lower.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=10000,
            timeline_start_ms=0,
        )
        upper = doc.insert_clip(
            source="upper.mp4",
            track_id="V2",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=2000,
        )
        self.assertIs(doc.video_clip_at(1000), lower)
        self.assertIs(doc.video_clip_at(3000), upper)
        self.assertIs(doc.video_clip_at(8000), lower)

    def test_hidden_video_track_is_not_previewed(self):
        doc = TimelineDocument.default()
        upper = doc.insert_clip(
            source="upper.mp4",
            track_id="V2",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=0,
        )
        lower = doc.insert_clip(
            source="lower.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=0,
        )
        doc.track("V2").visible = False
        self.assertIs(doc.video_clip_at(1000), lower)
        self.assertIsNot(doc.video_clip_at(1000), upper)

    def test_track_controls_toggle_state(self):
        doc = TimelineDocument.default()
        self.assertTrue(doc.toggle_track_lock("V1"))
        self.assertFalse(doc.toggle_track_visibility("V1"))
        self.assertTrue(doc.toggle_track_mute("A1"))
        self.assertTrue(doc.track("V1").locked)
        self.assertFalse(doc.track("V1").visible)
        self.assertTrue(doc.track("A1").muted)

    def test_muted_linked_audio_is_resolved_for_preview(self):
        doc = TimelineDocument.default()
        video = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=0,
            group_id="g1",
        )
        doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=0,
            group_id="g1",
        )
        self.assertFalse(doc.audio_muted_for_video_clip(video.id, 1000))
        doc.toggle_track_mute("A1")
        self.assertTrue(doc.audio_muted_for_video_clip(video.id, 1000))

    def test_locked_track_rejects_trim(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=5000,
            timeline_start_ms=0,
        )
        doc.toggle_track_lock("V1")
        with self.assertRaises(ValueError):
            doc.trim_linked(clip.id, edge="right", timeline_ms=3000)

    def test_history_cancel_checkpoint_removes_rejected_operation(self):
        doc = TimelineDocument.default()
        history = TimelineHistory(doc)
        history.checkpoint()
        self.assertTrue(history.can_undo)
        self.assertTrue(history.cancel_checkpoint())
        self.assertFalse(history.can_undo)

    def test_history_undo_redo_preserves_document_identity(self):
        doc = TimelineDocument.default()
        history = TimelineHistory(doc)
        original_id = id(doc)

        history.checkpoint()
        doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
        )
        self.assertEqual(len(doc.clips), 1)

        self.assertTrue(history.undo())
        self.assertEqual(len(doc.clips), 0)
        self.assertEqual(id(doc), original_id)

        self.assertTrue(history.redo())
        self.assertEqual(len(doc.clips), 1)
        self.assertEqual(id(doc), original_id)


if __name__ == "__main__":
    unittest.main()
