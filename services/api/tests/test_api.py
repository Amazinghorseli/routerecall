from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from routerecall.main import app


class ApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_and_complete_recovery_case(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(200, health.status_code)
        self.assertEqual({"status": "ok", "mode": "demo"}, health.json())

        created = self.client.post("/v1/demo/cases", params={"memory_enabled": True})
        self.assertEqual(200, created.status_code)
        case_id = created.json()["id"]

        completed = self.client.post(f"/v1/cases/{case_id}/run")
        self.assertEqual(200, completed.status_code)
        self.assertEqual("COMPLETED", completed.json()["status"])
        self.assertEqual("offer-ba286", completed.json()["context"]["plan"]["selected_offer_id"])

        inspected = self.client.get(f"/v1/cases/{case_id}")
        self.assertEqual(200, inspected.status_code)
        self.assertGreaterEqual(len(inspected.json()["actions"]), 3)


if __name__ == "__main__":
    unittest.main()
