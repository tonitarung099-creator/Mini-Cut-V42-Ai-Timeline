import subprocess
import tempfile
import unittest
from pathlib import Path

from minicut_agent.evidence_packets import SubtitleCue
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.v42_1b2 import V42BlockSpec, V42OneB2Plan, V42UnitSpec
from minicut_agent.v42_narration import (
    FFmpegSilenceDetector,
    NarrationAudioTiming,
    NarrationTimingSet,
    build_narration_audio_plan,
    NarrationCueMapping,
    NarrationMappingError,
    SilenceInterval,
    map_narration_cues,
    parse_narration_script_text,
    parse_silencedetect,
    refine_safe_padding,
)


class NarrationMappingTests(unittest.TestCase):
    def plan(self):
        return V42OneB2Plan(
            source_path="1b2.json",
            source_sha256="hash",
            blocks={
                "B-001": V42BlockSpec(
                    id="B-001",
                    display_order=["N-001", "J-001", "N-002"],
                    unit_ids=["N-001", "J-001", "N-002"],
                )
            },
            units={
                "N-001": V42UnitSpec("N-001", "narration", "B-001"),
                "J-001": V42UnitSpec("J-001", "anchor", "B-001"),
                "N-002": V42UnitSpec("N-002", "narration", "B-001"),
            },
        )

    def script(self):
        return parse_narration_script_text(
            """BAGIAN A TEKNIS
N-001: versi teknis lama
NASKAH BERSIH FINAL — SUMBER AUDIO NARASI
N-001: Pada pagi hari Toni masuk ke kantor.
J-001
D-001: Halo.
N-002
Kemudian ia membuka berkas rahasia di meja.
"""
        )

    def test_final_section_only_is_parsed(self):
        script = self.script()
        self.assertEqual(
            script.units["N-001"].text,
            "Pada pagi hari Toni masuk ke kantor.",
        )
        self.assertEqual(
            script.units["N-002"].text,
            "Kemudian ia membuka berkas rahasia di meja.",
        )
        self.assertNotIn("versi teknis lama", script.units["N-001"].text)

    def test_missing_final_section_is_rejected(self):
        with self.assertRaises(NarrationMappingError):
            parse_narration_script_text("N-001: teks tanpa final section")

    def test_explicit_srt_ids_map_directly(self):
        cues = [
            SubtitleCue(1000, 3000, "N-001: Pada pagi hari Toni masuk ke kantor.", 1),
            SubtitleCue(4000, 7000, "N-002: Kemudian ia membuka berkas rahasia di meja.", 2),
        ]
        mapped = map_narration_cues(self.script(), cues, self.plan())
        self.assertEqual([item.unit_id for item in mapped], ["N-001", "N-002"])
        self.assertTrue(all(item.method == "explicit-id" for item in mapped))
        self.assertEqual((mapped[0].core_start_ms, mapped[0].core_end_ms), (1000, 3000))

    def test_explicit_id_segment_includes_unlabeled_continuation_cues(self):
        cues = [
            SubtitleCue(1000, 1700, "N-001: Pada pagi hari", 1),
            SubtitleCue(1700, 3000, "Toni masuk ke kantor.", 2),
            SubtitleCue(4000, 5200, "N-002: Kemudian ia membuka", 3),
            SubtitleCue(5200, 7000, "berkas rahasia di meja.", 4),
        ]
        mapped = map_narration_cues(self.script(), cues, self.plan())
        self.assertEqual([item.cue_indexes for item in mapped], [[1, 2], [3, 4]])
        self.assertTrue(all(item.method == "explicit-id" for item in mapped))
        self.assertEqual(mapped[0].core_end_ms, 3000)
        self.assertEqual(mapped[1].core_end_ms, 7000)

    def test_unlabeled_srt_is_grouped_monotonically_by_text(self):
        cues = [
            SubtitleCue(1000, 1800, "Pada pagi hari", 1),
            SubtitleCue(1800, 3000, "Toni masuk ke kantor.", 2),
            SubtitleCue(4000, 5200, "Kemudian ia membuka", 3),
            SubtitleCue(5200, 7000, "berkas rahasia di meja.", 4),
        ]
        mapped = map_narration_cues(self.script(), cues, self.plan())
        self.assertEqual([item.cue_indexes for item in mapped], [[1, 2], [3, 4]])
        self.assertTrue(all(item.similarity > 0.8 for item in mapped))

    def test_unrelated_srt_is_rejected(self):
        cues = [
            SubtitleCue(0, 1000, "cuaca cerah sekali", 1),
            SubtitleCue(1000, 2000, "mobil melaju cepat", 2),
        ]
        with self.assertRaises(NarrationMappingError):
            map_narration_cues(self.script(), cues, self.plan())

    def test_silencedetect_parser_makes_absolute_intervals(self):
        log = """
[silencedetect] silence_start: 0.1
[silencedetect] silence_end: 0.42 | silence_duration: 0.32
[silencedetect] silence_start: 2.0
[silencedetect] silence_end: 2.5 | silence_duration: 0.5
"""
        intervals = parse_silencedetect(
            log,
            window_start_ms=1000,
            window_end_ms=5000,
        )
        self.assertEqual(
            [(item.start_ms, item.end_ms) for item in intervals],
            [(1100, 1420), (3000, 3500)],
        )

    def test_safe_padding_uses_waveform_silence(self):
        mapping = NarrationCueMapping(
            "N-001",
            "teks",
            [1],
            1500,
            3000,
            0.95,
            "monotonic-text",
        )
        timing = refine_safe_padding(
            mapping,
            [
                SilenceInterval(1000, 1450),
                SilenceInterval(3050, 3600),
            ],
            lower_bound=800,
            upper_bound=4000,
            before_padding_ms=250,
            after_padding_ms=350,
        )
        self.assertEqual(timing.source_in_ms, 1200)
        self.assertEqual(timing.source_out_ms, 3400)
        self.assertEqual(timing.pre_padding_ms, 300)
        self.assertEqual(timing.post_padding_ms, 400)
        self.assertEqual(
            timing.boundary_method,
            "waveform-silence/waveform-silence",
        )

    def test_a2_audio_plan_uses_authoritative_timing_and_region(self):
        doc = TimelineDocument.default()
        timing_set = NarrationTimingSet(
            audio_path="narration.wav",
            audio_fingerprint="audio-fp",
            narration_srt_path="narration.srt",
            narration_srt_sha256="srt",
            script_sha256="script",
            timings={
                "N-001": NarrationAudioTiming(
                    unit_id="N-001",
                    source_in_ms=900,
                    source_out_ms=4100,
                    core_start_ms=1100,
                    core_end_ms=3800,
                    pre_padding_ms=200,
                    post_padding_ms=300,
                    mapping_similarity=0.95,
                    mapping_method="monotonic-text",
                    boundary_method="waveform-silence/waveform-silence",
                )
            },
        )
        payload = build_narration_audio_plan(
            plan=self.plan(),
            timing_set=timing_set,
            document=doc,
            unit_id="N-001",
            expected_revision=3,
        )
        self.assertEqual(payload["expected_revision"], 3)
        insert = payload["actions"][-1]
        self.assertEqual(insert["tool"], "insert_clip")
        self.assertEqual(insert["args"]["track_id"], "A2")
        self.assertEqual(insert["args"]["source_in_ms"], 900)
        self.assertEqual(insert["args"]["source_out_ms"], 4100)
        self.assertEqual(insert["args"]["timeline_start_ms"], 0)
        self.assertEqual(insert["args"]["origin"], "narration_audio")

    def test_a2_audio_plan_reflows_later_anchor(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=10000,
            source_out_ms=12000,
            timeline_start_ms=0,
            group_id="j",
            unit_id="J-001",
            block_id="B-001",
            origin="gemini_verified",
        )
        doc.insert_clip(
            source="film.mp4",
            track_id="A1",
            source_in_ms=10000,
            source_out_ms=12000,
            timeline_start_ms=0,
            group_id="j",
            unit_id="J-001",
            block_id="B-001",
            origin="gemini_verified",
        )
        timing_set = NarrationTimingSet(
            audio_path="narration.wav",
            audio_fingerprint="audio-fp",
            narration_srt_path="narration.srt",
            narration_srt_sha256="srt",
            script_sha256="script",
            timings={
                "N-001": NarrationAudioTiming(
                    "N-001", 0, 5000, 200, 4700, 200, 300,
                    0.9, "monotonic-text", "waveform-silence/waveform-silence"
                )
            },
        )
        payload = build_narration_audio_plan(
            plan=self.plan(),
            timing_set=timing_set,
            document=doc,
            unit_id="N-001",
            expected_revision=2,
        )
        self.assertEqual(payload["actions"][0]["tool"], "move_clip")
        self.assertEqual(payload["actions"][0]["args"]["timeline_start_ms"], 5000)
        self.assertEqual(payload["actions"][-1]["args"]["timeline_start_ms"], 0)

    def test_detector_scans_only_local_window(self):
        commands = []

        def fake_runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr=(
                    "[silencedetect] silence_start: 0.0\n"
                    "[silencedetect] silence_end: 0.2 | silence_duration: 0.2\n"
                ),
            )

        detector = FFmpegSilenceDetector(
            ffmpeg_path="ffmpeg",
            runner=fake_runner,
        )
        intervals = detector.detect("narration.wav", 5000, 9000)
        command = commands[0]
        self.assertEqual(command[command.index("-ss") + 1], "5.000")
        self.assertEqual(command[command.index("-t") + 1], "4.000")
        self.assertEqual((intervals[0].start_ms, intervals[0].end_ms), (5000, 5200))


if __name__ == "__main__":
    unittest.main()
