import subprocess
import tempfile
import unittest
from pathlib import Path

from minicut_agent.evidence_packets import (
    SparseFrameExtractor,
    UnitEvidencePacket,
    build_unit_evidence,
    compact_packet_for_model,
    overlapping_cues,
    parse_srt,
    parse_srt_timestamp,
)
from minicut_agent.shot_detection import (
    CandidateShotAnalysis,
    ShotSegment,
    UnitShotAnalysis,
)


class EvidencePacketTests(unittest.TestCase):
    def test_parse_srt_multiline_and_overlap(self):
        cues = parse_srt(
            """1
00:00:01,000 --> 00:00:03,000
Halo dunia

2
00:00:02.500 --> 00:00:05.000
Baris satu
Baris dua
"""
        )
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[1].text, "Baris satu\nBaris dua")
        overlap = overlapping_cues(cues, 2800, 3200)
        self.assertEqual([cue.index for cue in overlap], [1, 2])

    def test_srt_timestamp(self):
        self.assertEqual(parse_srt_timestamp("01:02:03,450"), 3723450)
        self.assertEqual(parse_srt_timestamp("00:00:02.5"), 2500)

    def test_frame_extractor_command_and_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "frame.jpg"
            commands = []

            def fake_runner(command, **kwargs):
                commands.append(command)
                Path(command[-1]).write_bytes(b"jpeg")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            extractor = SparseFrameExtractor(
                ffmpeg_path="ffmpeg",
                max_width=480,
                runner=fake_runner,
            )
            frame = extractor.extract("film.mp4", 12500, target)
            command = commands[0]
            self.assertEqual(command[command.index("-ss") + 1], "12.500")
            self.assertIn("min(480,iw)", command[command.index("-vf") + 1])
            self.assertEqual(frame.size_bytes, 4)

    def test_build_packet_extracts_three_frames_and_srt_context(self):
        analysis = UnitShotAnalysis(
            unit_id="N-001",
            source="film.mp4",
            scene_threshold=0.3,
            min_shot_ms=300,
            candidates=[
                CandidateShotAnalysis(
                    start_ms=1000,
                    end_ms=5000,
                    shots=[
                        ShotSegment(
                            start_ms=1000,
                            end_ms=5000,
                            candidate_start_ms=1000,
                            candidate_end_ms=5000,
                            location="Kantor",
                        )
                    ],
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            srt = temp_path / "film.srt"
            srt.write_text(
                "1\n00:00:02,000 --> 00:00:03,000\nDialog penting\n",
                encoding="utf-8",
            )

            class FakeExtractor:
                def extract(self, source, timestamp_ms, target):
                    from minicut_agent.evidence_packets import FrameEvidence
                    path = Path(target)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"x" * 10)
                    return FrameEvidence(timestamp_ms, str(path), 10)

            packet = build_unit_evidence(
                analysis,
                one_b2_source_sha256="abc",
                srt_path=srt,
                extractor=FakeExtractor(),
                cache_root=temp_path / "cache",
            )
            self.assertEqual(packet.frame_count, 3)
            self.assertEqual(packet.subtitle_cue_count, 1)
            self.assertEqual(packet.image_bytes, 30)
            self.assertEqual(packet.shots[0].subtitles[0].text, "Dialog penting")
            self.assertEqual(packet.one_b2_source_sha256, "abc")

    def test_packet_round_trip_and_compact_model_payload(self):
        packet = UnitEvidencePacket(
            unit_id="N-001",
            source="film.mp4",
            source_fingerprint="fp",
        )
        restored = UnitEvidencePacket.from_dict(packet.to_dict())
        self.assertEqual(restored.unit_id, "N-001")
        compact = compact_packet_for_model(restored)
        self.assertEqual(compact["unit_id"], "N-001")
        self.assertEqual(compact["summary"]["frames"], 0)


if __name__ == "__main__":
    unittest.main()
