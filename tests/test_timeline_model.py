import unittest

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


if __name__ == "__main__":
    unittest.main()
