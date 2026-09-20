import subprocess
import unittest

from minicut_agent.shot_detection import (
    FFmpegShotDetector,
    UnitShotAnalysis,
    analyze_unit_candidates,
    build_shots,
    candidate_ranges_for_unit,
    parse_showinfo_offsets_ms,
)
from minicut_agent.v42_1b2 import CandidateRange, V42BlockSpec, V42OneB2Plan, V42UnitSpec


class ShotDetectionTests(unittest.TestCase):
    def test_showinfo_parser_reads_relative_cut_times(self):
        log = """
[Parsed_showinfo_2] n: 0 pts: 1536 pts_time:1.500 pos: 0
[Parsed_showinfo_2] n: 1 pts: 3584 pts_time:3.500 pos: 0
[Parsed_showinfo_2] n: 2 pts: 3584 pts_time:3.500 pos: 0
"""
        self.assertEqual(parse_showinfo_offsets_ms(log), [1500, 3500])

    def test_build_shots_keeps_candidate_bounds(self):
        candidate = CandidateRange(
            start_ms=10000,
            end_ms=20000,
            location="Kantor",
            label="Kolam visual",
        )
        shots = build_shots(candidate, [1500, 5500], min_shot_ms=300)
        self.assertEqual(
            [(shot.start_ms, shot.end_ms) for shot in shots],
            [(10000, 11500), (11500, 15500), (15500, 20000)],
        )
        self.assertTrue(all(shot.location == "Kantor" for shot in shots))

    def test_build_shots_filters_micro_boundaries(self):
        candidate = CandidateRange(start_ms=0, end_ms=3000)
        shots = build_shots(candidate, [100, 500, 2850], min_shot_ms=300)
        self.assertEqual(
            [(shot.start_ms, shot.end_ms) for shot in shots],
            [(0, 500), (500, 3000)],
        )

    def test_representative_times_are_sparse_and_inside_shot(self):
        shot = build_shots(
            CandidateRange(start_ms=1000, end_ms=5000),
            [],
        )[0]
        points = shot.representative_times_ms()
        self.assertEqual(len(points), 3)
        self.assertTrue(all(shot.start_ms <= value < shot.end_ms for value in points))

    def test_detector_uses_only_requested_candidate_duration(self):
        commands = []

        def fake_runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="[showinfo] pts_time:2.000",
            )

        detector = FFmpegShotDetector(
            ffmpeg_path="ffmpeg",
            scene_threshold=0.25,
            runner=fake_runner,
        )
        candidate = CandidateRange(start_ms=60000, end_ms=68000)
        result = detector.detect("film.mp4", candidate)

        command = commands[0]
        self.assertEqual(command[command.index("-ss") + 1], "60.000")
        self.assertEqual(command[command.index("-t") + 1], "8.000")
        self.assertIn("scene,0.2500", command[command.index("-vf") + 1])
        self.assertEqual(
            [(shot.start_ms, shot.end_ms) for shot in result.shots],
            [(60000, 62000), (62000, 68000)],
        )

    def test_unit_analysis_prefers_unit_candidates(self):
        plan = V42OneB2Plan(
            source_path="",
            source_sha256="hash",
            blocks={
                "B-001": V42BlockSpec(
                    id="B-001",
                    candidate_ranges=[CandidateRange(1000, 9000)],
                )
            },
            units={
                "N-001": V42UnitSpec(
                    id="N-001",
                    kind="narration",
                    block_id="B-001",
                    candidate_ranges=[CandidateRange(2000, 6000)],
                )
            },
        )

        class FakeDetector:
            scene_threshold = 0.3
            min_shot_ms = 300

            def detect(self, source, candidate):
                from minicut_agent.shot_detection import CandidateShotAnalysis
                return CandidateShotAnalysis(
                    start_ms=candidate.start_ms,
                    end_ms=candidate.end_ms,
                    shots=build_shots(candidate, []),
                )

        result = analyze_unit_candidates(
            plan,
            "N-001",
            "film.mp4",
            detector=FakeDetector(),
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].start_ms, 2000)
        self.assertEqual(result.shot_count, 1)

    def test_unit_without_own_candidates_can_fallback_to_block(self):
        plan = V42OneB2Plan(
            source_path="",
            source_sha256="hash",
            blocks={
                "B-001": V42BlockSpec(
                    id="B-001",
                    candidate_ranges=[CandidateRange(1000, 9000)],
                )
            },
            units={
                "N-001": V42UnitSpec(
                    id="N-001",
                    kind="narration",
                    block_id="B-001",
                )
            },
        )
        ranges, warnings = candidate_ranges_for_unit(plan, "N-001")
        self.assertEqual([(r.start_ms, r.end_ms) for r in ranges], [(1000, 9000)])
        self.assertEqual(len(warnings), 1)

    def test_analysis_round_trip(self):
        result = UnitShotAnalysis(
            unit_id="N-001",
            source="film.mp4",
            scene_threshold=0.3,
            min_shot_ms=300,
        )
        restored = UnitShotAnalysis.from_dict(result.to_dict())
        self.assertEqual(restored.unit_id, "N-001")
        self.assertEqual(restored.source, "film.mp4")


if __name__ == "__main__":
    unittest.main()
