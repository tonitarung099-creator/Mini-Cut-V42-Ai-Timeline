import unittest

from minicut_agent.v42_state import V42WorkflowState


class V42WorkflowStateTests(unittest.TestCase):
    def test_unit_and_checkpoint_round_trip(self):
        state = V42WorkflowState(active_block="B-001", active_unit="N-001")
        state.set_unit_status(
            "N-001",
            "working",
            block_id="B-001",
            timeline_revision=4,
        )
        state.record_checkpoint(
            "after-N-001",
            timeline_revision=5,
            block_id="B-001",
            unit_id="N-001",
            payload={"candidate": "SHOT-03"},
        )

        restored = V42WorkflowState.from_dict(state.to_dict())
        self.assertEqual(restored.active_block, "B-001")
        self.assertEqual(restored.units["N-001"]["timeline_revision"], 4)
        self.assertEqual(
            restored.checkpoints["after-N-001"]["payload"]["candidate"],
            "SHOT-03",
        )

    def test_invalid_status_rejected(self):
        state = V42WorkflowState()
        with self.assertRaises(ValueError):
            state.set_unit_status("N-001", "done-ish")


if __name__ == "__main__":
    unittest.main()
