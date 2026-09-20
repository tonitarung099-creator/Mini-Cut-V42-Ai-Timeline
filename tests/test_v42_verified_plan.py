import unittest

from minicut_agent.evidence_packets import ShotEvidence, UnitEvidencePacket
from minicut_agent.gemini_client import (
    GeminiBatchResult,
    GeminiShotDecision,
    GeminiUnitVerification,
)
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.v42_1b2 import V42OneB2Plan, V42UnitSpec
from minicut_agent.v42_verified_plan import (
    V42PlanBuildError,
    build_verified_timeline_plan,
    select_verified_ranges,
)


def verification(unit_id, decisions):
    return GeminiUnitVerification(
        unit_id=unit_id,
        model="gemini-test",
        batches=[
            GeminiBatchResult(
                batch_index=1,
                model="gemini-test",
                key_id="gk-test",
                decisions=decisions,
            )
        ],
    )


class VerifiedTimelinePlanTests(unittest.TestCase):
    def packet(self, unit_id="N-001"):
        return UnitEvidencePacket(
            unit_id=unit_id,
            source="film.mp4",
            source_fingerprint="fp",
            one_b2_source_sha256="hash",
            shots=[
                ShotEvidence(1000, 4000, 1000, 10000),
                ShotEvidence(4000, 8000, 1000, 10000),
                ShotEvidence(8000, 10000, 1000, 10000),
            ],
        )

    def plan(self, unit_id="N-001", kind="narration"):
        return V42OneB2Plan(
            source_path="1b2.json",
            source_sha256="hash",
            units={
                unit_id: V42UnitSpec(
                    id=unit_id,
                    kind=kind,
                    block_id="B-001",
                )
            },
        )

    def decisions(self):
        return [
            GeminiShotDecision(1, "keep", 0.8, "sesuai"),
            GeminiShotDecision(2, "trim", 0.9, "ambil bagian inti", 5000, 7000),
            GeminiShotDecision(3, "reject", 0.7, "tidak relevan"),
        ]

    def test_narration_builds_video_only_review_plan(self):
        doc = TimelineDocument.default()
        payload = build_verified_timeline_plan(
            plan=self.plan(),
            packet=self.packet(),
            verification=verification("N-001", self.decisions()),
            document=doc,
            expected_revision=4,
        )
        self.assertEqual(payload["expected_revision"], 4)
        self.assertEqual(payload["unit_id"], "N-001")
        self.assertEqual(len(payload["actions"]), 2)
        first, second = payload["actions"]
        self.assertEqual(first["args"]["track_id"], "V2")
        self.assertTrue(first["args"]["muted"])
        self.assertEqual(first["args"]["source_in_ms"], 1000)
        self.assertEqual(first["args"]["source_out_ms"], 4000)
        self.assertEqual(first["args"]["timeline_start_ms"], 0)
        self.assertEqual(second["args"]["source_in_ms"], 5000)
        self.assertEqual(second["args"]["source_out_ms"], 7000)
        self.assertEqual(second["args"]["timeline_start_ms"], 3000)
        self.assertEqual(first["args"]["unit_id"], "N-001")
        self.assertEqual(first["args"]["origin"], "gemini_verified")
        self.assertEqual(doc.clips, [])

    def test_anchor_builds_linked_video_audio_pairs(self):
        doc = TimelineDocument.default()
        packet = self.packet("J-001")
        chosen = [
            GeminiShotDecision(1, "keep", 0.9, "dialog"),
            GeminiShotDecision(2, "reject", 0.7, "tidak perlu"),
            GeminiShotDecision(3, "keep", 0.8, "reaksi"),
        ]
        payload = build_verified_timeline_plan(
            plan=self.plan("J-001", "anchor"),
            packet=packet,
            verification=verification("J-001", chosen),
            document=doc,
            expected_revision=0,
        )
        self.assertEqual(len(payload["actions"]), 4)
        video1, audio1, video2, audio2 = payload["actions"]
        self.assertEqual((video1["args"]["track_id"], audio1["args"]["track_id"]), ("V1", "A1"))
        self.assertEqual(video1["args"]["group_id"], audio1["args"]["group_id"])
        self.assertEqual(video1["args"]["speed"], 1.0)
        self.assertEqual(audio1["args"]["speed"], 1.0)
        self.assertEqual(video2["args"]["timeline_start_ms"], 3000)
        self.assertEqual(audio2["args"]["timeline_start_ms"], 3000)

    def test_default_placement_appends_after_existing_timeline(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="other.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=6000,
            timeline_start_ms=2000,
        )
        payload = build_verified_timeline_plan(
            plan=self.plan(),
            packet=self.packet(),
            verification=verification("N-001", self.decisions()),
            document=doc,
            expected_revision=0,
        )
        self.assertEqual(payload["actions"][0]["args"]["timeline_start_ms"], 8000)

    def test_existing_same_unit_refuses_duplicate_plan(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="film.mp4",
            track_id="V2",
            source_in_ms=1000,
            source_out_ms=2000,
            timeline_start_ms=0,
            unit_id="N-001",
            block_id="B-001",
            origin="gemini_verified",
        )
        with self.assertRaises(V42PlanBuildError):
            build_verified_timeline_plan(
                plan=self.plan(),
                packet=self.packet(),
                verification=verification("N-001", self.decisions()),
                document=doc,
                expected_revision=0,
            )

    def test_other_v42_unit_cannot_reuse_overlapping_source(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="film.mp4",
            track_id="V2",
            source_in_ms=1200,
            source_out_ms=2500,
            timeline_start_ms=0,
            unit_id="N-999",
            block_id="B-999",
            origin="gemini_verified",
        )
        with self.assertRaises(V42PlanBuildError):
            build_verified_timeline_plan(
                plan=self.plan(),
                packet=self.packet(),
                verification=verification("N-001", self.decisions()),
                document=doc,
                expected_revision=0,
            )

    def test_overlapping_selected_evidence_prefers_higher_confidence(self):
        packet = UnitEvidencePacket(
            unit_id="N-001",
            source="film.mp4",
            source_fingerprint="fp",
            one_b2_source_sha256="hash",
            shots=[
                ShotEvidence(1000, 5000, 1000, 7000),
                ShotEvidence(3000, 7000, 1000, 7000),
            ],
        )
        result = select_verified_ranges(
            packet,
            verification(
                "N-001",
                [
                    GeminiShotDecision(1, "keep", 0.6, "a"),
                    GeminiShotDecision(2, "keep", 0.9, "b"),
                ],
            ),
        )
        self.assertEqual([(item.shot_index, item.start_ms, item.end_ms) for item in result], [(2, 3000, 7000)])

    def test_mismatched_1b2_identity_is_rejected(self):
        packet = self.packet()
        packet.one_b2_source_sha256 = "old"
        with self.assertRaises(V42PlanBuildError):
            build_verified_timeline_plan(
                plan=self.plan(),
                packet=packet,
                verification=verification("N-001", self.decisions()),
                document=TimelineDocument.default(),
                expected_revision=0,
            )

    def test_all_rejected_has_no_plan(self):
        packet = self.packet()
        rejected = [
            GeminiShotDecision(index, "reject", 0.9, "no")
            for index in (1, 2, 3)
        ]
        with self.assertRaises(V42PlanBuildError):
            build_verified_timeline_plan(
                plan=self.plan(),
                packet=packet,
                verification=verification("N-001", rejected),
                document=TimelineDocument.default(),
                expected_revision=0,
            )


if __name__ == "__main__":
    unittest.main()
