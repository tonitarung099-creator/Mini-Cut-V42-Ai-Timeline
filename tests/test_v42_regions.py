import unittest

from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.v42_1b2 import V42BlockSpec, V42OneB2Plan, V42UnitSpec
from minicut_agent.v42_regions import (
    build_reflow_actions,
    compute_region_layout,
    display_sequence,
    infer_unit_duration_ms,
)


class V42RegionTests(unittest.TestCase):
    def plan(self):
        return V42OneB2Plan(
            source_path="1b2.json",
            source_sha256="hash",
            blocks={
                "B-001": V42BlockSpec(
                    id="B-001",
                    unit_ids=["N-001", "J-001"],
                    display_order=["N-001", "J-001"],
                    work_order=["J-001", "N-001"],
                ),
                "B-002": V42BlockSpec(
                    id="B-002",
                    unit_ids=["N-002"],
                    display_order=["N-002"],
                    work_order=["N-002"],
                ),
            },
            units={
                "N-001": V42UnitSpec("N-001", "narration", "B-001"),
                "J-001": V42UnitSpec("J-001", "anchor", "B-001"),
                "N-002": V42UnitSpec("N-002", "narration", "B-002"),
            },
            work_queue=["J-001", "N-001", "N-002"],
        )

    def test_display_order_is_independent_from_work_order(self):
        self.assertEqual(
            display_sequence(self.plan()),
            ["N-001", "J-001", "N-002"],
        )

    def test_manual_content_becomes_region_base(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="manual.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=4000,
            timeline_start_ms=1000,
        )
        layout = compute_region_layout(
            self.plan(),
            doc,
            duration_overrides={"N-001": 3000, "J-001": 2000, "N-002": 1000},
        )
        self.assertEqual(layout.base_start_ms, 5000)
        self.assertEqual(layout.region("N-001").start_ms, 5000)
        self.assertEqual(layout.region("J-001").start_ms, 8000)
        self.assertEqual(layout.region("N-002").start_ms, 10000)

    def test_late_earlier_unit_pushes_existing_later_unit(self):
        doc = TimelineDocument.default()
        doc.insert_clip(
            source="film.mp4",
            track_id="V1",
            source_in_ms=10000,
            source_out_ms=12000,
            timeline_start_ms=0,
            group_id="v42-J-001-0001",
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
            group_id="v42-J-001-0001",
            unit_id="J-001",
            block_id="B-001",
            origin="gemini_verified",
        )
        layout = compute_region_layout(
            self.plan(),
            doc,
            duration_overrides={"N-001": 5000},
        )
        self.assertEqual(layout.region("N-001").start_ms, 0)
        self.assertEqual(layout.region("J-001").start_ms, 5000)
        self.assertEqual(layout.region("J-001").duration_ms, 2000)

        actions = build_reflow_actions(doc, layout, exclude_unit_ids={"N-001"})
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "move_clip")
        self.assertEqual(actions[0]["args"]["timeline_start_ms"], 5000)

    def test_multiple_groups_keep_relative_offsets_when_reflowed(self):
        doc = TimelineDocument.default()
        for group, start in [("g1", 0), ("g2", 2000)]:
            doc.insert_clip(
                source="film.mp4",
                track_id="V2",
                source_in_ms=start,
                source_out_ms=start + 1000,
                timeline_start_ms=start,
                group_id=group,
                unit_id="N-001",
                block_id="B-001",
                origin="gemini_verified",
            )
        plan = self.plan()
        layout = compute_region_layout(
            plan,
            doc,
            duration_overrides={"N-001": 3000},
        )
        # Force this materialized unit to a 4s manual base.
        manual = doc.insert_clip(
            source="manual.mp4",
            track_id="V1",
            source_in_ms=0,
            source_out_ms=4000,
            timeline_start_ms=0,
        )
        layout = compute_region_layout(
            plan,
            doc,
            duration_overrides={"N-001": 3000},
        )
        actions = build_reflow_actions(doc, layout)
        starts = sorted(action["args"]["timeline_start_ms"] for action in actions)
        self.assertEqual(starts, [4000, 6000])

    def test_explicit_duration_field_can_seed_provisional_region(self):
        unit = V42UnitSpec(
            "N-001",
            "narration",
            "B-001",
            fields={"Durasi Narasi": "6.5 detik"},
        )
        self.assertEqual(infer_unit_duration_ms(unit), 6500)

    def test_unknown_duration_is_zero_and_warned(self):
        layout = compute_region_layout(self.plan(), TimelineDocument.default())
        self.assertEqual(layout.region("N-001").duration_ms, 0)
        self.assertGreaterEqual(len(layout.warnings), 1)


if __name__ == "__main__":
    unittest.main()
