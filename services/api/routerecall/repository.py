from __future__ import annotations

import json
import math
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Protocol

from .models import (
    ActionRecord,
    Checkpoint,
    FlightOffer,
    Memory,
    Passenger,
    RecoveryCase,
    ReservationResult,
    WorkflowStep,
    utc_now,
)


class SeatUnavailable(RuntimeError):
    pass


class Repository(Protocol):
    def add_passenger(self, passenger: Passenger) -> None: ...
    def add_memory(self, memory: Memory) -> None: ...
    def add_offer(self, offer: FlightOffer) -> None: ...
    def create_case(self, case: RecoveryCase) -> None: ...
    def get_case(self, case_id: str) -> RecoveryCase: ...
    def save_case(self, case: RecoveryCase) -> None: ...
    def list_memories(self, passenger_id: str) -> list[Memory]: ...
    def similar_memories(self, passenger_id: str, embedding: tuple[float, ...], limit: int = 3) -> list[Memory]: ...
    def save_checkpoint(self, checkpoint: Checkpoint) -> None: ...
    def latest_checkpoint(self, case_id: str) -> Checkpoint | None: ...
    def append_action(self, action: ActionRecord) -> ActionRecord: ...
    def list_actions(self, case_id: str) -> list[ActionRecord]: ...
    def reserve_seat(self, case_id: str, offer_id: str, seat: str, idempotency_key: str) -> ReservationResult: ...


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class InMemoryRepository:
    """Deterministic repository for tests and the credential-free demo mode."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.passengers: dict[str, Passenger] = {}
        self.memories: dict[str, Memory] = {}
        self.offers: dict[str, FlightOffer] = {}
        self.cases: dict[str, RecoveryCase] = {}
        self.checkpoints: dict[str, list[Checkpoint]] = {}
        self.actions: dict[str, ActionRecord] = {}
        self.actions_by_key: dict[str, str] = {}
        self.seat_owner: dict[tuple[str, str], str] = {}

    def add_passenger(self, passenger: Passenger) -> None:
        with self._lock:
            self.passengers[passenger.id] = passenger

    def add_memory(self, memory: Memory) -> None:
        with self._lock:
            self.memories[memory.id] = memory

    def add_offer(self, offer: FlightOffer) -> None:
        with self._lock:
            self.offers[offer.id] = offer

    def create_case(self, case: RecoveryCase) -> None:
        with self._lock:
            self.cases[case.id] = deepcopy(case)

    def get_case(self, case_id: str) -> RecoveryCase:
        with self._lock:
            return deepcopy(self.cases[case_id])

    def save_case(self, case: RecoveryCase) -> None:
        with self._lock:
            case.version += 1
            case.updated_at = utc_now()
            self.cases[case.id] = deepcopy(case)

    def list_memories(self, passenger_id: str) -> list[Memory]:
        with self._lock:
            return [memory for memory in self.memories.values() if memory.passenger_id == passenger_id]

    def similar_memories(self, passenger_id: str, embedding: tuple[float, ...], limit: int = 3) -> list[Memory]:
        candidates = self.list_memories(passenger_id)
        candidates.sort(key=lambda item: cosine_similarity(item.embedding, embedding) * item.importance, reverse=True)
        return candidates[:limit]

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._lock:
            self.checkpoints.setdefault(checkpoint.case_id, []).append(deepcopy(checkpoint))

    def latest_checkpoint(self, case_id: str) -> Checkpoint | None:
        with self._lock:
            items = self.checkpoints.get(case_id, [])
            return deepcopy(items[-1]) if items else None

    def append_action(self, action: ActionRecord) -> ActionRecord:
        with self._lock:
            existing_id = self.actions_by_key.get(action.idempotency_key)
            if existing_id:
                return self.actions[existing_id]
            self.actions[action.id] = action
            self.actions_by_key[action.idempotency_key] = action.id
            return action

    def list_actions(self, case_id: str) -> list[ActionRecord]:
        with self._lock:
            return [action for action in self.actions.values() if action.case_id == case_id]

    def reserve_seat(self, case_id: str, offer_id: str, seat: str, idempotency_key: str) -> ReservationResult:
        with self._lock:
            existing_id = self.actions_by_key.get(idempotency_key)
            if existing_id:
                return ReservationResult(self.actions[existing_id], duplicate_prevented=True)

            seat_key = (offer_id, seat)
            owner = self.seat_owner.get(seat_key)
            if owner and owner != case_id:
                raise SeatUnavailable(f"Seat {seat} on {offer_id} is already held")

            self.seat_owner[seat_key] = case_id
            action = ActionRecord.create(
                case_id,
                "RESERVE_SEAT",
                idempotency_key,
                {"offer_id": offer_id, "seat": seat},
                {"offer_id": offer_id, "seat": seat, "reservation_status": "HELD"},
            )
            self.actions[action.id] = action
            self.actions_by_key[idempotency_key] = action.id
            return ReservationResult(action, duplicate_prevented=False)


class CockroachRepository:
    """CockroachDB Cloud implementation used by the persistent runtime.

    psycopg is imported lazily so unit tests and the local demo need no cloud
    credentials or native database client.
    """

    def __init__(self, database_url: str, max_retries: int = 5) -> None:
        try:
            import psycopg  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in cloud image
            raise RuntimeError("Install psycopg[binary] to use CockroachRepository") from exc
        self._psycopg = psycopg
        self.database_url = database_url
        self.max_retries = max_retries

    def _connect(self):
        return self._psycopg.connect(self.database_url, autocommit=False)

    @staticmethod
    def _vector_literal(values: tuple[float, ...]) -> str:
        return "[" + ",".join(f"{value:.10f}" for value in values) + "]"

    def add_passenger(self, passenger: Passenger) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO passengers (id, name, home_region)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name,
                    home_region = excluded.home_region,
                    updated_at = now()
                """,
                (passenger.id, passenger.name, passenger.home_region),
            )

    def add_memory(self, memory: Memory) -> None:
        vector = self._vector_literal(memory.embedding) if memory.embedding else None
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_memories
                    (id, passenger_id, memory_type, content, importance, embedding, metadata, created_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s::VECTOR, %s::JSONB, %s)
                ON CONFLICT (id) DO UPDATE SET
                    content = excluded.content,
                    importance = excluded.importance,
                    embedding = excluded.embedding,
                    metadata = excluded.metadata
                """,
                (
                    memory.id,
                    memory.passenger_id,
                    memory.memory_type,
                    memory.content,
                    memory.importance,
                    vector,
                    json.dumps(memory.metadata),
                    memory.created_at,
                ),
            )

    def add_offer(self, offer: FlightOffer) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO flight_offers
                    (id, airline, flight_number, origin, destination, departure_at,
                     arrival_at, stops, duration_minutes, fare_difference_usd,
                     reliability, is_red_eye_departure, window_seats, source)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::JSONB, %s)
                ON CONFLICT (id) DO UPDATE SET
                    departure_at = excluded.departure_at,
                    arrival_at = excluded.arrival_at,
                    fare_difference_usd = excluded.fare_difference_usd,
                    reliability = excluded.reliability,
                    window_seats = excluded.window_seats,
                    source = excluded.source
                """,
                (
                    offer.id,
                    offer.airline,
                    offer.flight_number,
                    offer.origin,
                    offer.destination,
                    offer.departure_at,
                    offer.arrival_at,
                    offer.stops,
                    offer.duration_minutes,
                    offer.fare_difference_usd,
                    offer.reliability,
                    offer.is_red_eye_departure,
                    json.dumps(list(offer.window_seats)),
                    offer.source,
                ),
            )
            for seat in offer.window_seats or ("2F",):
                cursor.execute(
                    """
                    INSERT INTO seat_inventory (offer_id, seat_number, status)
                    VALUES (%s, %s, 'AVAILABLE')
                    ON CONFLICT (offer_id, seat_number) DO NOTHING
                    """,
                    (offer.id, seat),
                )

    def create_case(self, case: RecoveryCase) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO recovery_cases
                    (id, passenger_id, disruption, memory_enabled, current_step,
                     status, version, context, created_at, updated_at)
                VALUES (%s, %s, %s::JSONB, %s, %s, %s, %s, %s::JSONB, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    case.id,
                    case.passenger_id,
                    json.dumps(asdict(case.disruption)),
                    case.memory_enabled,
                    case.current_step.value,
                    case.status,
                    case.version,
                    json.dumps(case.context, default=str),
                    case.created_at,
                    case.updated_at,
                ),
            )

    def get_case(self, case_id: str) -> RecoveryCase:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::STRING, passenger_id::STRING, disruption, memory_enabled,
                       current_step, status, version, context, created_at, updated_at
                FROM recovery_cases WHERE id = %s
                """,
                (case_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise KeyError(f"Unknown recovery case: {case_id}")
            disruption_data = self._json_value(row[2])
            return RecoveryCase(
                id=str(row[0]),
                passenger_id=str(row[1]),
                disruption=self._disruption_from_dict(disruption_data),
                memory_enabled=bool(row[3]),
                current_step=WorkflowStep(row[4]),
                status=row[5],
                version=int(row[6]),
                context=self._json_value(row[7]),
                created_at=row[8],
                updated_at=row[9],
            )

    def save_case(self, case: RecoveryCase) -> None:
        previous_version = case.version
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE recovery_cases SET
                    current_step = %s,
                    status = %s,
                    version = version + 1,
                    context = %s::JSONB,
                    updated_at = now()
                WHERE id = %s AND version = %s
                RETURNING version, updated_at
                """,
                (
                    case.current_step.value,
                    case.status,
                    json.dumps(case.context, default=str),
                    case.id,
                    previous_version,
                ),
            )
            row = cursor.fetchone()
            if not row:
                raise RuntimeError(f"Concurrent update detected for recovery case {case.id}")
            case.version = int(row[0])
            case.updated_at = row[1]

    def list_memories(self, passenger_id: str) -> list[Memory]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id::STRING, passenger_id::STRING, memory_type, content, importance, embedding::STRING, metadata, created_at FROM agent_memories WHERE passenger_id = %s ORDER BY importance DESC",
                (passenger_id,),
            )
            return [self._memory_from_row(row) for row in cursor.fetchall()]

    def similar_memories(self, passenger_id: str, embedding: tuple[float, ...], limit: int = 3) -> list[Memory]:
        vector = self._vector_literal(embedding)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id::STRING, passenger_id::STRING, memory_type, content, importance, embedding::STRING, metadata, created_at FROM agent_memories WHERE passenger_id = %s AND embedding IS NOT NULL ORDER BY embedding <=> %s::VECTOR LIMIT %s",
                (passenger_id, vector, limit),
            )
            return [self._memory_from_row(row) for row in cursor.fetchall()]

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO workflow_checkpoints
                    (case_id, step, state, version, created_at)
                VALUES (%s, %s, %s::JSONB, %s, %s)
                ON CONFLICT (case_id, version) DO NOTHING
                """,
                (
                    checkpoint.case_id,
                    checkpoint.step.value,
                    json.dumps(checkpoint.state, default=str),
                    checkpoint.version,
                    checkpoint.created_at,
                ),
            )

    def latest_checkpoint(self, case_id: str) -> Checkpoint | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT case_id::STRING, step, state, version, created_at
                FROM workflow_checkpoints
                WHERE case_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (case_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Checkpoint(str(row[0]), WorkflowStep(row[1]), self._json_value(row[2]), int(row[3]), row[4])

    def append_action(self, action: ActionRecord) -> ActionRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO action_ledger
                    (id, recovery_case_id, action_type, idempotency_key, status, input, output, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::JSONB, %s::JSONB, %s)
                ON CONFLICT (idempotency_key) DO UPDATE SET
                    idempotency_key = excluded.idempotency_key
                RETURNING id::STRING, recovery_case_id::STRING, action_type,
                          idempotency_key, status, input, output, created_at
                """,
                (
                    action.id,
                    action.case_id,
                    action.action_type,
                    action.idempotency_key,
                    action.status,
                    json.dumps(action.input, default=str),
                    json.dumps(action.output, default=str),
                    action.created_at,
                ),
            )
            return self._action_from_row(cursor.fetchone())

    def list_actions(self, case_id: str) -> list[ActionRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::STRING, recovery_case_id::STRING, action_type,
                       idempotency_key, status, input, output, created_at
                FROM action_ledger
                WHERE recovery_case_id = %s
                ORDER BY created_at
                """,
                (case_id,),
            )
            return [self._action_from_row(row) for row in cursor.fetchall()]

    def reserve_seat(self, case_id: str, offer_id: str, seat: str, idempotency_key: str) -> ReservationResult:
        for attempt in range(self.max_retries):
            try:
                with self._connect() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id::STRING, recovery_case_id::STRING, action_type, idempotency_key, status, input, output, created_at FROM action_ledger WHERE idempotency_key = %s",
                        (idempotency_key,),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        connection.rollback()
                        return ReservationResult(self._action_from_row(existing), duplicate_prevented=True)

                    cursor.execute(
                        "SELECT status, recovery_case_id::STRING FROM seat_inventory WHERE offer_id = %s AND seat_number = %s FOR UPDATE",
                        (offer_id, seat),
                    )
                    inventory = cursor.fetchone()
                    if not inventory or (inventory[0] == "HELD" and inventory[1] != case_id):
                        connection.rollback()
                        raise SeatUnavailable(f"Seat {seat} on {offer_id} is already held")

                    cursor.execute(
                        "UPDATE seat_inventory SET status = 'HELD', recovery_case_id = %s, updated_at = now() WHERE offer_id = %s AND seat_number = %s",
                        (case_id, offer_id, seat),
                    )
                    action = ActionRecord.create(case_id, "RESERVE_SEAT", idempotency_key, {"offer_id": offer_id, "seat": seat}, {"reservation_status": "HELD", "offer_id": offer_id, "seat": seat})
                    cursor.execute(
                        "INSERT INTO action_ledger (id, recovery_case_id, action_type, idempotency_key, status, input, output) VALUES (%s, %s, %s, %s, %s, %s::JSONB, %s::JSONB)",
                        (action.id, case_id, action.action_type, idempotency_key, action.status, json.dumps(action.input), json.dumps(action.output)),
                    )
                    connection.commit()
                    return ReservationResult(action, duplicate_prevented=False)
            except self._psycopg.errors.SerializationFailure:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(0.025 * (2**attempt))
        raise RuntimeError("transaction retry loop exhausted")

    @staticmethod
    def _memory_from_row(row) -> Memory:
        vector_text = row[5].strip("[]") if row[5] else ""
        embedding = tuple(float(value) for value in vector_text.split(",") if value)
        return Memory(str(row[0]), str(row[1]), row[2], row[3], float(row[4]), embedding, CockroachRepository._json_value(row[6]), row[7])

    @staticmethod
    def _action_from_row(row) -> ActionRecord:
        return ActionRecord(str(row[0]), str(row[1]), row[2], row[3], row[4], CockroachRepository._json_value(row[5]), CockroachRepository._json_value(row[6]), row[7])

    @staticmethod
    def _json_value(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return json.loads(value)

    @staticmethod
    def _disruption_from_dict(value: dict[str, Any]):
        from .models import Disruption

        return Disruption(
            value["id"],
            value["flight_number"],
            value["origin"],
            value["destination"],
            value["final_destination"],
            value["reason"],
            value["meeting_deadline"],
            value["travel_date"],
        )
