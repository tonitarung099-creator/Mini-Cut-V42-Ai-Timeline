import unittest

from minicut_agent.v42_prompt3_fit import (
    PROMPT3_MAX_SPEED,
    PROMPT3_MIN_PIECE_MS,
    Prompt3Candidate,
    Prompt3FitError,
    fit_prompt3_visuals,
)


class Prompt3VisualFitTests(unittest.TestCase):
    def c(self, index, start, end, confidence=0.9, decision="keep"):
        return Prompt3Candidate(
            shot_index=index,
            start_ms=start,
            end_ms=end,
            confidence=confidence,
            reason="sesuai",
            decision=decision,
        )

    def test_exact_default_half_speed(self):
        result = fit_prompt3_visuals(
            [self.c(1, 0, 2000), self.c(2, 3000, 5000)],
            target_duration_ms=8000,
        )
        self.assertEqual(result.timeline_duration_ms, 8000)
        self.assertEqual([round(p.speed, 6) for p in result.pieces], [0.5, 0.5])
        self.assertEqual([p.timeline_duration_ms for p in result.pieces], [4000, 4000])

    def test_slows_below_half_to_fill_audio_exactly(self):
        result = fit_prompt3_visuals(
            [self.c(1, 0, 2000), self.c(2, 3000, 5000)],
            target_duration_ms=10000,
        )
        self.assertEqual(result.timeline_duration_ms, 10000)
        self.assertTrue(all(0 < piece.speed <= PROMPT3_MAX_SPEED for piece in result.pieces))
        self.assertEqual([p.timeline_duration_ms for p in result.pieces], [5000, 5000])
        self.assertAlmostEqual(result.pieces[0].speed, 0.4)

    def test_short_source_piece_is_slowed_to_minimum_two_seconds(self):
        result = fit_prompt3_visuals(
            [self.c(1, 0, 500)],
            target_duration_ms=2000,
        )
        self.assertEqual(result.pieces[0].timeline_duration_ms, PROMPT3_MIN_PIECE_MS)
        self.assertAlmostEqual(result.pieces[0].speed, 0.25)

    def test_target_below_two_seconds_is_revision(self):
        with self.assertRaisesRegex(Prompt3FitError, "DURASI N DI BAWAH"):
            fit_prompt3_visuals(
                [self.c(1, 0, 500)],
                target_duration_ms=1999,
            )

    def test_subset_keeps_high_confidence_candidates_and_source_order(self):
        result = fit_prompt3_visuals(
            [
                self.c(1, 0, 2000, 0.7),
                self.c(2, 3000, 5000, 0.95, "trim"),
                self.c(3, 6000, 8000, 0.8),
            ],
            target_duration_ms=8000,
        )
        self.assertEqual([p.shot_index for p in result.pieces], [2, 3])
        self.assertEqual(result.omitted_shot_indexes, [1])
        self.assertEqual(result.timeline_duration_ms, 8000)

    def test_no_candidate_can_fit_is_revision_not_speed_violation(self):
        with self.assertRaisesRegex(Prompt3FitError, "jalankan verifikasi Gemini ulang"):
            fit_prompt3_visuals(
                [self.c(1, 0, 4000)],
                target_duration_ms=6000,
            )

    def test_overlapping_source_is_revision(self):
        with self.assertRaisesRegex(Prompt3FitError, "overlap"):
            fit_prompt3_visuals(
                [self.c(1, 0, 2000), self.c(2, 1500, 2500)],
                target_duration_ms=8000,
            )

    def test_very_slow_speed_is_flagged_for_naturalness_review(self):
        result = fit_prompt3_visuals(
            [self.c(1, 0, 1000)],
            target_duration_ms=10000,
        )
        self.assertAlmostEqual(result.pieces[0].speed, 0.1)
        self.assertTrue(any("naturalness" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
