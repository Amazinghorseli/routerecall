from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStep(StrEnum):
    RECEIVE_DISRUPTION = "RECEIVE_DISRUPTION"
    LOAD_PASSENGER_MEMORY = "LOAD_PASSENGER_MEMORY"
    RECALL_SIMILAR_CASES = "RECALL_SIMILAR_CASES"
    SEARCH_ALTERNATIVES = "SEARCH_ALTERNATIVES"
    BUILD_RECOVERY_PLAN = "BUILD_RECOVERY_PLAN"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    RESERVE_SEAT = "RESERVE_SEAT"
    GENERATE_REPORT = "GENERATE_REPORT"
    LEARN_FROM_OUTCOME = "LEARN_FROM_OUTCOME"
    COMPLETE = "COMPLETE"


WORKFLOW_ORDER = [
    WorkflowStep.RECEIVE_DISRUPTION,
    WorkflowStep.LOAD_PASSENGER_MEMORY,
    WorkflowStep.RECALL_SIMILAR_CASES,
    WorkflowStep.SEARCH_ALTERNATIVES,
    WorkflowStep.BUILD_RECOVERY_PLAN,
    WorkflowStep.WAIT_FOR_APPROVAL,
    WorkflowStep.RESERVE_SEAT,
    WorkflowStep.GENERATE_REPORT,
    WorkflowStep.LEARN_FROM_OUTCOME,
    WorkflowStep.COMPLETE,
]


@dataclass(slots=True, frozen=True)
class Passenger:
    id: str
    name: str
    home_region: str


@dataclass(slots=True, frozen=True)
class Memory:
    id: str
    passenger_id: str
    memory_type: str
    content: str
    importance: float
    embedding: tuple[float, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class Disruption:
    id: str
    flight_number: str
    origin: str
    destination: str
    final_destination: str
    reason: str
    meeting_deadline: str
    travel_date: str


@dataclass(slots=True, frozen=True)
class FlightOffer:
    id: str
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_at: str
    arrival_at: str
    stops: int
    duration_minutes: int
    fare_difference_usd: int
    reliability: float
    is_red_eye_departure: bool
    window_seats: tuple[str, ...]
    source: str = "fallback"


@dataclass(slots=True, frozen=True)
class RankedOffer:
    offer: FlightOffer
    score: float
    reasons: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RecoveryPlan:
    selected_offer_id: str
    ranked_offers: tuple[RankedOffer, ...]
    explanation: str
    memories_used: tuple[str, ...]


@dataclass(slots=True)
class RecoveryCase:
    id: str
    passenger_id: str
    disruption: Disruption
    memory_enabled: bool
    current_step: WorkflowStep = WorkflowStep.RECEIVE_DISRUPTION
    status: str = "RUNNING"
    version: int = 0
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class Checkpoint:
    case_id: str
    step: WorkflowStep
    state: dict[str, Any]
    version: int
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class ActionRecord:
    id: str
    case_id: str
    action_type: str
    idempotency_key: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        case_id: str,
        action_type: str,
        idempotency_key: str,
        input: dict[str, Any],
        output: dict[str, Any],
        status: str = "SUCCEEDED",
    ) -> "ActionRecord":
        return cls(str(uuid4()), case_id, action_type, idempotency_key, status, input, output)


@dataclass(slots=True, frozen=True)
class ReservationResult:
    action: ActionRecord
    duplicate_prevented: bool


@dataclass(slots=True, frozen=True)
class RaceResult:
    committed_case_id: str
    replanned_case_id: str
    oversold_seats: int
    duplicate_actions: int
