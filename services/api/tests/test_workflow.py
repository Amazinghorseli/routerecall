from __future__ import annotations

import threading
import unittest

from routerecall.fixtures import DISRUPTION, PASSENGER, build_demo_engine
from routerecall.models import WorkflowStep
from routerecall.repository import SeatUnavailable
from routerecall.workflow import CrashInjected


class RecoveryWorkflowTests(unittest.TestCase):
    def test_memory_changes_the_selected_offer(self) -> None:
        engine, _ = build_demo_engine()
        remembered = engine.start_case(PASSENGER.id, DISRUPTION, memory_enabled=True, case_id="RR-MEMORY")
        stateless = engine.start_case(PASSENGER.id, DISRUPTION, memory_enabled=False, case_id="RR-STATELESS")

        remembered = engine.run(remembered.id)
        stateless = engine.run(stateless.id)

        self.assertEqual("offer-ba286", remembered.context["plan"]["selected_offer_id"])
        self.assertEqual("offer-ua930", stateless.context["plan"]["selected_offer_id"])
        self.assertGreater(len(remembered.context["plan"]["memories_used"]), 0)
        self.assertEqual([], stateless.context["plan"]["memories_used"])

    def test_crash_resume_uses_checkpoint_and_does_not_repeat_actions(self) -> None:
        engine, repository = build_demo_engine()
        case = engine.start_case(PASSENGER.id, DISRUPTION, memory_enabled=True, case_id="RR-RESUME")

        with self.assertRaises(CrashInjected):
            engine.run(case.id, crash_after=WorkflowStep.WAIT_FOR_APPROVAL)

        checkpoint = repository.latest_checkpoint(case.id)
        self.assertIsNotNone(checkpoint)
        self.assertEqual(WorkflowStep.WAIT_FOR_APPROVAL, checkpoint.step)

        resumed = engine.resume(case.id)
        self.assertEqual("COMPLETED", resumed.status)
        actions = repository.list_actions(case.id)
        self.assertEqual(1, len([action for action in actions if action.action_type == "APPROVE_PLAN"]))
        self.assertEqual(1, len([action for action in actions if action.action_type == "RESERVE_SEAT"]))

    def test_idempotency_returns_original_reservation(self) -> None:
        _, repository = build_demo_engine()
        first = repository.reserve_seat("RR-IDEMPOTENT", "offer-ba286", "1A", "same-key")
        second = repository.reserve_seat("RR-IDEMPOTENT", "offer-ba286", "1A", "same-key")
        self.assertFalse(first.duplicate_prevented)
        self.assertTrue(second.duplicate_prevented)
        self.assertEqual(first.action.id, second.action.id)

    def test_concurrent_agents_cannot_oversell_last_seat(self) -> None:
        engine, repository = build_demo_engine()
        result = engine.race_for_last_seat("RR-RACE-A", "RR-RACE-B", "offer-ba286", "1A")
        self.assertIn(result.committed_case_id, {"RR-RACE-A", "RR-RACE-B"})
        self.assertIn(result.replanned_case_id, {"RR-RACE-A", "RR-RACE-B"})
        self.assertNotEqual(result.committed_case_id, result.replanned_case_id)
        self.assertEqual(0, result.oversold_seats)
        self.assertEqual(0, result.duplicate_actions)


if __name__ == "__main__":
    unittest.main()
