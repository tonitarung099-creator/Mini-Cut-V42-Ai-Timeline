import unittest

from minicut_agent.ai_plan import TimelinePlanManager
from minicut_agent.timeline_history import TimelineHistory
from minicut_agent.timeline_model import TimelineDocument
from minicut_agent.timeline_tools import TimelineToolRegistry


class TimelinePlanManagerTests(unittest.TestCase):
    def setUp(self):
        self.doc = TimelineDocument.default()
        self.history = TimelineHistory(self.doc)
        self.registry = TimelineToolRegistry(self.doc, self.history)
        self.manager = TimelinePlanManager(self.registry)

    def _plan(self, **overrides):
        payload = {
            "title": "Insert candidate visual",
            "expected_revision": self.registry.revision,
            "unit_id": "N-001",
            "block_id": "B-001",
            "actions": [
                {
                    "tool": "insert_clip",
                    "args": {
                        "source": "film.mp4",
                        "track_id": "V1",
                        "source_in_ms": 1000,
                        "source_out_ms": 5000,
                        "timeline_start_ms": 0,
                        "label": "SHOT-01",
                    },
                }
            ],
        }
        payload.update(overrides)
        return payload

    def test_propose_does_not_mutate_timeline(self):
        result = self.manager.propose(self._plan())
        self.assertTrue(result["ok"])
        self.assertEqual(self.doc.clips, [])
        self.assertEqual(self.registry.revision, 0)
        self.assertIsNotNone(self.manager.pending)

    def test_apply_uses_atomic_registry_batch(self):
        self.manager.propose(self._plan())
        result = self.manager.apply()
        self.assertTrue(result["ok"])
        self.assertEqual(len(self.doc.clips), 1)
        self.assertEqual(self.registry.revision, 1)
        self.assertIsNone(self.manager.pending)

    def test_stale_plan_rejected_before_pending(self):
        payload = self._plan(expected_revision=0)
        self.registry.execute(
            "insert_clip",
            {
                "source": "other.mp4",
                "track_id": "V1",
                "source_in_ms": 0,
                "source_out_ms": 1000,
                "timeline_start_ms": 0,
            },
        )
        result = self.manager.propose(payload)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "stale_revision")
        self.assertIsNone(self.manager.pending)

    def test_pending_plan_cannot_be_silently_replaced(self):
        self.assertTrue(self.manager.propose(self._plan())["ok"])
        second = self.manager.propose(
            self._plan(title="Second", expected_revision=self.registry.revision)
        )
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"]["code"], "pending_plan_exists")

    def test_invalid_tool_is_rejected(self):
        result = self.manager.propose(
            self._plan(
                actions=[{"tool": "run_shell", "args": {"command": "whoami"}}]
            )
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_plan")

    def test_apply_revalidates_plan_before_mutation(self):
        allowed = {"film.mp4"}

        def validator(tool, args):
            if tool == "insert_clip" and args.get("source") not in allowed:
                return "source tidak lagi diizinkan"
            return None

        manager = TimelinePlanManager(
            self.registry,
            action_validator=validator,
        )
        self.assertTrue(manager.propose(self._plan())["ok"])
        allowed.clear()

        result = manager.apply()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "plan_revalidation_failed")
        self.assertEqual(self.doc.clips, [])
        self.assertEqual(self.registry.revision, 0)
        self.assertIsNotNone(manager.pending)

    def test_whole_plan_validator_runs_on_propose_and_apply(self):
        allowed = {"ok": True}
        calls = []

        def plan_validator(plan):
            calls.append(plan.id)
            if not allowed["ok"]:
                return "whole plan stale"
            return None

        manager = TimelinePlanManager(
            self.registry,
            plan_validator=plan_validator,
        )
        proposed = manager.propose(self._plan())
        self.assertTrue(proposed["ok"])
        self.assertEqual(len(calls), 1)

        allowed["ok"] = False
        applied = manager.apply()
        self.assertFalse(applied["ok"])
        self.assertEqual(applied["error"]["code"], "plan_revalidation_failed")
        self.assertEqual(self.doc.clips, [])
        self.assertIsNotNone(manager.pending)
        self.assertEqual(len(calls), 2)

    def test_whole_plan_validator_can_reject_proposal(self):
        manager = TimelinePlanManager(
            self.registry,
            plan_validator=lambda plan: "unsafe aggregate",
        )
        result = manager.propose(self._plan())
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "plan_validation_failed")
        self.assertIsNone(manager.pending)

    def test_cancel_keeps_timeline_untouched(self):
        self.manager.propose(self._plan())
        result = self.manager.cancel()
        self.assertTrue(result["ok"])
        self.assertEqual(self.doc.clips, [])
        self.assertIsNone(self.manager.pending)


if __name__ == "__main__":
    unittest.main()
