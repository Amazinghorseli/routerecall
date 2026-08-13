"""Print a sanitized summary of RouteRecall cloud demonstration records."""

from __future__ import annotations

import json
import os

import certifi
import psycopg

from bootstrap_cloud import database_url


def main() -> None:
    os.environ.setdefault("PGSSLROOTCERT", certifi.where())
    with psycopg.connect(database_url(), connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status, context->'plan'->>'selected_offer_id',
                       context->'reservation'->>'seat'
                FROM recovery_cases
                WHERE id LIKE 'RR-CLOUD-%'
                ORDER BY created_at
                """
            )
            cases = [
                {"case_id": row[0], "status": row[1], "selected_offer_id": row[2], "seat": row[3]}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT recovery_case_id, action_type, idempotency_key
                FROM action_ledger
                WHERE recovery_case_id LIKE 'RR-CLOUD-%'
                ORDER BY created_at
                """
            )
            actions = [
                {"case_id": row[0], "action_type": row[1], "idempotency_key": row[2]}
                for row in cursor.fetchall()
            ]
    print(json.dumps({"cases": cases, "actions": actions}, indent=2))


if __name__ == "__main__":
    main()
