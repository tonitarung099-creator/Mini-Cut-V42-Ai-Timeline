import unittest

from minicut_agent.evidence_packets import ShotEvidence, UnitEvidencePacket
from minicut_agent.gemini_client import (
    GeminiBatchResult,
    GeminiShotDecision,
    GeminiUnitVerification,
)
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.v42_1b2 import V42OneB2Plan, V42UnitSpec
from minicut_agent.v42_prompt3_revision import (
    Prompt3RevisionError,
    build_prompt3_visual_replacement_plan,
)


def verification(decisions):
    return GeminiUnitVerification(
        unit_id="N-001",
        model="test",
        batches=[
            GeminiBatchResult(
                batch_index=1,
                model="test",
                key_id="key",
                decisions=decisions,
            )
        ],
    )


class Prompt3TargetedRevisionTests(unittest.TestCase):
    def plan(self):
        return V42OneB2Plan(
            source_path="1b2.json",
            source_sha256="hash",
            units={
                "N-001": V42UnitSpec(
                    id="N-001",
                    kind="narration",
                    block_id="B-001",
                )
            },
        )

    def packet(self):
        return UnitEvidencePacket(
            unit_id="N-001",
            source="film.mp4",
            source_fingerprint="fp",
            one_b2_source_sha256="hash",
            shots=[
                ShotEvidence(0, 1000, 0, 9000),
                ShotEvidence(1500, 2500, 0, 9000),
                ShotEvidence(3000, 4000, 0, 9000),
                ShotEvidence(4500, 5500, 0, 9000),
                ShotEvidence(6000, 7000, 0, 9000),
            ],
        )

    def decisions(self):
        return [
            GeminiShotDecision(1, "keep", 0.9, "awal"),
            GeminiShotDecision(2, "keep", 0.8, "alternatif A"),
            GeminiShotDecision(3, "keep", 0.95, "clip lama"),
            GeminiShotDecision(4, "keep", 0.85, "alternatif B"),
            GeminiShotDecision(5, "keep", 0.9, "akhir"),
        ]

    def document(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="film.mp4",
            track_id="V2",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
            speed=0.5,
            muted=True,
            unit_id="N-001",
            block_id="B-001",
            origin="prompt3_visual",
            clip_id="before",
        )
        selected = doc.insert_clip(
            source="film.mp4",
            track_id="V2",
            source_in_ms=3000,
            source_out_ms=4000,
            timeline_start_ms=2000,
            speed=0.5,
            muted=True,
            unit_id="N-001",
            block_id="B-001",
            origin="prompt3_visual",
            clip_id="bad",
        )
        doc.insert_clip(
            source="film.mp4",
            track_id="V2",
            source_in_ms=6000,
            source_out_ms=7000,
            timeline_start_ms=4000,
            speed=0.5,
            muted=True,
            unit_id="N-001",
            block_id="B-001",
            origin="prompt3_visual",
            clip_id="after",
        )
        return doc, selected

    def test_replaces_only_selected_clip_and_preserves_local_duration(self):
        doc, selected = self.document()
        payload = build_prompt3_visual_replacement_plan(
            plan=self.plan(),
            packet=self.packet(),
            verification=verification(self.decisions()),
            document=doc,
            clip_id=selected.id,
            expected_revision=7,
        )
        self.assertEqual(payload["expected_revision"], 7)
        self.assertEqual(payload["created_by"], "prompt3-visual-revision")
        self.assertEqual(payload["actions"][0], {
            "tool": "delete_clip",
            "args": {"clip_id": "bad"},
        })
        inserts = payload["actions"][1:]
        self.assertTrue(inserts)
        self.assertTrue(all(a["args"]["timeline_start_ms"] >= 2000 for a in inserts))
        total = sum(
            round(
                (a["args"]["source_out_ms"] - a["args"]["source_in_ms"])
                / a["args"]["speed"]
            )
            for a in inserts
        )
        self.assertEqual(total, selected.timeline_duration_ms)
        self.assertEqual(inserts[0]["args"]["timeline_start_ms"], 2000)
        self.assertTrue(all(a["args"]["origin"] == "prompt3_visual_revision" for a in inserts))
        self.assertEqual(len(doc.clips), 3)

    def test_replacement_candidates_stay_between_neighbor_source_ranges(self):
        doc, selected = self.document()
        payload = build_prompt3_visual_replacement_plan(
            plan=self.plan(),
            packet=self.packet(),
            verification=verification(self.decisions()),
            document=doc,
            clip_id=selected.id,
            expected_revision=0,
        )
        inserts = payload["actions"][1:]
        self.assertTrue(
            all(
                1000 <= a["args"]["source_in_ms"]
                and a["args"]["source_out_ms"] <= 6000
                for a in inserts
            )
        )
        self.assertTrue(
            all(
                not (
                    a["args"]["source_in_ms"] < 4000
                    and a["args"]["source_out_ms"] > 3000
                )
                for a in inserts
            )
        )

    def test_no_safe_alternative_is_revision(self):
        doc, selected = self.document()
        decisions = [
            GeminiShotDecision(1, "keep", 0.9, "awal"),
            GeminiShotDecision(2, "reject", 0.9, "no"),
            GeminiShotDecision(3, "keep", 0.95, "lama"),
            GeminiShotDecision(4, "reject", 0.9, "no"),
            GeminiShotDecision(5, "keep", 0.9, "akhir"),
        ]
        with self.assertRaisesRegex(Prompt3RevisionError, "PERLU REVISI"):
            build_prompt3_visual_replacement_plan(
                plan=self.plan(),
                packet=self.packet(),
                verification=verification(decisions),
                document=doc,
                clip_id=selected.id,
                expected_revision=0,
            )

    def test_non_prompt3_clip_is_rejected(self):
        doc = TimelineDocument.default()
        clip = doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=1000,
            timeline_start_ms=0,
        )
        with self.assertRaises(Prompt3RevisionError):
            build_prompt3_visual_replacement_plan(
                plan=self.plan(),
                packet=self.packet(),
                verification=verification(self.decisions()),
                document=doc,
                clip_id=clip.id,
                expected_revision=0,
            )


if __name__ == "__main__":
    unittest.main()
