"""Initialize and verify a RouteRecall CockroachDB Cloud cluster.

Reads DATABASE_URL from the process environment or the repository's private
.env file. The connection string is never printed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import certifi
import psycopg


ROOT = Path(__file__).resolve().parents[1]


def database_url() -> str:
    if value := os.getenv("DATABASE_URL"):
        return value
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                value = line.partition("=")[2].strip()
                if value:
                    return value
    raise RuntimeError("DATABASE_URL is missing; set it in .env or the environment")


def sql_statements(path: Path) -> list[str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")]
    source = "\n".join(lines)
    statements: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(source):
        character = source[index]
        if quote:
            buffer.append(character)
            if character == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    buffer.append(source[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            buffer.append(character)
        elif character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(character)
        index += 1
    if statement := "".join(buffer).strip():
        statements.append(statement)
    return statements


def main() -> None:
    url = database_url()
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("PGSSLROOTCERT", certifi.where())

    with psycopg.connect(url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            for path in (ROOT / "database/migrations/001_initial.sql", ROOT / "database/seed.sql"):
                statements = sql_statements(path)
                print(f"Applying {path.name} ({len(statements)} statements)", flush=True)
                for number, statement in enumerate(statements, start=1):
                    operation = " ".join(statement.split()[:4])
                    print(f"  {number}/{len(statements)} {operation}", flush=True)
                    cursor.execute(statement)

            cursor.execute("SELECT version()")
            server = str(cursor.fetchone()[0]).split(" ", 2)[:2]
            cursor.execute("SHOW INDEXES FROM agent_memories")
            indexes = sorted({str(row[1]) for row in cursor.fetchall()})

    from routerecall.fixtures import DISRUPTION, PASSENGER
    from routerecall.runtime import build_runtime_engine

    print("Seeding embedded memories and offers", flush=True)
    engine, repository, mode = build_runtime_engine()
    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM recovery_cases WHERE id LIKE 'RR-CLOUD-%' AND status = 'COMPLETED' ORDER BY created_at LIMIT 1"
        )
        existing_case = cursor.fetchone()

    if existing_case:
        case_id = str(existing_case[0])
        print(f"Reusing completed cloud recovery case {case_id}", flush=True)
        completed = repository.get_case(case_id)
    else:
        case_id = f"RR-CLOUD-{uuid4().hex[:8].upper()}"
        print(f"Running cloud recovery case {case_id}", flush=True)
        case = engine.start_case(PASSENGER.id, DISRUPTION, memory_enabled=True, case_id=case_id)
        completed = engine.run(case.id)

    with psycopg.connect(url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM workflow_checkpoints WHERE case_id = %s", (case_id,))
        checkpoint_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM action_ledger WHERE recovery_case_id = %s", (case_id,))
        action_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT count(*) FROM agent_memories WHERE passenger_id = %s AND embedding IS NOT NULL", (PASSENGER.id,))
        embedded_memory_count = int(cursor.fetchone()[0])

    result = {
        "connected": True,
        "server": " ".join(server),
        "runtime_mode": mode,
        "case_id": case_id,
        "case_status": completed.status,
        "selected_offer_id": completed.context["plan"]["selected_offer_id"],
        "similar_memory_ids": completed.context.get("similar_memory_ids", []),
        "checkpoints": checkpoint_count,
        "actions": action_count,
        "embedded_memories": embedded_memory_count,
        "memory_indexes": indexes,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
