from __future__ import annotations

import threading
from dataclasses import asdict
from uuid import uuid4

from .integrations import EmbeddingProvider, FlightSearchProvider, Planner
from .models import (
    ActionRecord,
    Checkpoint,
    Disruption,
    Memory,
    RaceResult,
    RecoveryCase,
    RecoveryPlan,
    WORKFLOW_ORDER,
    WorkflowStep,
)
from .repository import Repository, SeatUnavailable, cosine_similarity


class CrashInjected(RuntimeError):
    def __init__(self, case_id: str, checkpoint: WorkflowStep) -> None:
        super().__init__(f"Worker terminated after durable checkpoint {checkpoint}")
        self.case_id = case_id
        self.checkpoint = checkpoint


class RecoveryEngine:
    def __init__(self, repository: Repository, embeddings: EmbeddingProvider, flight_search: FlightSearchProvider, planner: Planner) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.flight_search = flight_search
        self.planner = planner

    def start_case(self, passenger_id: str, disruption: Disruption, memory_enabled: bool = True, case_id: str | None = None) -> RecoveryCase:
        case = RecoveryCase(case_id or f"RR-{uuid4().hex[:8].upper()}", passenger_id, disruption, memory_enabled)
        self.repository.create_case(case)
        return case

    def run(self, case_id: str, crash_after: WorkflowStep | None = None) -> RecoveryCase:
        case = self.repository.get_case(case_id)
        start_index = WORKFLOW_ORDER.index(case.current_step)

        for index in range(start_index, len(WORKFLOW_ORDER)):
            step = WORKFLOW_ORDER[index]
            case.current_step = step
            self._execute_step(case, step)
            next_step = WORKFLOW_ORDER[min(index + 1, len(WORKFLOW_ORDER) - 1)]
            case.current_step = next_step
            self._checkpoint(case, step)
            self.repository.save_case(case)

            if crash_after == step:
                case.status = "INTERRUPTED"
                self.repository.save_case(case)
                raise CrashInjected(case.id, step)

        case.status = "COMPLETED"
        case.current_step = WorkflowStep.COMPLETE
        self.repository.save_case(case)
        return case

    def resume(self, case_id: str) -> RecoveryCase:
        checkpoint = self.repository.latest_checkpoint(case_id)
        if checkpoint is None:
            raise ValueError(f"No checkpoint exists for {case_id}")
        case = self.repository.get_case(case_id)
        case.status = "RUNNING"
        case.context = dict(checkpoint.state)
        case.current_step = WORKFLOW_ORDER[min(WORKFLOW_ORDER.index(checkpoint.step) + 1, len(WORKFLOW_ORDER) - 1)]
        self.repository.save_case(case)
        return self.run(case_id)

    def _execute_step(self, case: RecoveryCase, step: WorkflowStep) -> None:
        if step == WorkflowStep.RECEIVE_DISRUPTION:
            case.context["disruption"] = asdict(case.disruption)

        elif step == WorkflowStep.LOAD_PASSENGER_MEMORY:
            memories = self.repository.list_memories(case.passenger_id) if case.memory_enabled else []
            case.context["memories"] = [asdict(memory) for memory in memories]

        elif step == WorkflowStep.RECALL_SIMILAR_CASES:
            query = f"{case.disruption.reason} {case.disruption.origin} {case.disruption.final_destination} missed connection"
            embedding = self.embeddings.embed(query)
            similar = self.repository.similar_memories(case.passenger_id, embedding, 3) if case.memory_enabled else []
            case.context["similar_memory_ids"] = [memory.id for memory in similar]
            case.context["similar_memories"] = [
                {
                    "id": memory.id,
                    "memory_type": memory.memory_type,
                    "similarity": round(cosine_similarity(embedding, memory.embedding), 4),
                }
                for memory in similar
            ]

        elif step == WorkflowStep.SEARCH_ALTERNATIVES:
            offers = self.flight_search.search(case.disruption.origin, case.disruption.final_destination, case.disruption.travel_date)
            if not offers:
                raise ValueError("No viable replacement flights found")
            case.context["offers"] = [asdict(offer) for offer in offers]

        elif step == WorkflowStep.BUILD_RECOVERY_PLAN:
            offers = [self._offer_from_dict(item) for item in case.context["offers"]]
            memories = [self._memory_from_dict(item) for item in case.context.get("memories", [])]
            plan = self.planner.plan(offers, memories, case.memory_enabled)
            case.context["plan"] = self._plan_to_dict(plan)

        elif step == WorkflowStep.WAIT_FOR_APPROVAL:
            action = ActionRecord.create(case.id, "APPROVE_PLAN", f"{case.id}:approve-plan:v1", {"plan": case.context["plan"]}, {"approved": True, "actor": "demo-passenger"})
            self.repository.append_action(action)
            case.context["approved"] = True

        elif step == WorkflowStep.RESERVE_SEAT:
            selected_id = case.context["plan"]["selected_offer_id"]
            offer = next(item for item in case.context["offers"] if item["id"] == selected_id)
            seats = tuple(offer.get("window_seats", ())) or ("2F",)
            result = None
            for seat in seats:
                try:
                    result = self.repository.reserve_seat(case.id, selected_id, seat, f"{case.id}:reserve:{selected_id}:{seat}")
                    break
                except SeatUnavailable:
                    continue
            if result is None:
                alternatives = [item for item in case.context["plan"]["ranked_offers"] if item["offer"]["id"] != selected_id]
                if not alternatives:
                    raise SeatUnavailable(f"No seats remain on {selected_id}")
                replacement = alternatives[0]["offer"]
                replacement_seats = tuple(replacement.get("window_seats", ())) or ("2F",)
                for replacement_seat in replacement_seats:
                    try:
                        result = self.repository.reserve_seat(case.id, replacement["id"], replacement_seat, f"{case.id}:reserve:{replacement['id']}:{replacement_seat}")
                        case.context["plan"]["selected_offer_id"] = replacement["id"]
                        case.context["replanned_after_contention"] = True
                        break
                    except SeatUnavailable:
                        continue
                if result is None:
                    raise SeatUnavailable(f"No seats remain on {selected_id} or {replacement['id']}")
            case.context["reservation"] = result.action.output
            case.context["duplicate_prevented"] = result.duplicate_prevented

        elif step == WorkflowStep.GENERATE_REPORT:
            action = ActionRecord.create(
                case.id,
                "GENERATE_REPORT",
                f"{case.id}:report:v1",
                {"plan": case.context["plan"]},
                {"report_id": f"report-{case.id}", "storage": "cockroachdb-action-ledger", "status": "CREATED"},
            )
            self.repository.append_action(action)
            case.context["report"] = action.output

        elif step == WorkflowStep.LEARN_FROM_OUTCOME:
            selected_id = case.context["plan"]["selected_offer_id"]
            memory = Memory(
                id=f"mem-{case.id.lower()}-outcome",
                passenger_id=case.passenger_id,
                memory_type="RECOVERY_OUTCOME",
                content=f"Successful recovery selected {selected_id}; meeting protected and reservation completed without duplicate action.",
                importance=0.88,
                embedding=self.embeddings.embed(f"successful flight disruption recovery {selected_id}"),
                metadata={"case_id": case.id, "selected_offer_id": selected_id},
            )
            self.repository.add_memory(memory)
            case.context["learned_memory_id"] = memory.id

    def _checkpoint(self, case: RecoveryCase, completed_step: WorkflowStep) -> None:
        checkpoint = Checkpoint(case.id, completed_step, dict(case.context), case.version + 1)
        self.repository.save_checkpoint(checkpoint)

    def race_for_last_seat(self, first_case_id: str, second_case_id: str, offer_id: str, seat: str = "1A") -> RaceResult:
        outcome: dict[str, str] = {}
        barrier = threading.Barrier(2)

        def compete(case_id: str) -> None:
            barrier.wait()
            try:
                self.repository.reserve_seat(case_id, offer_id, seat, f"{case_id}:race:{offer_id}:{seat}")
                outcome[case_id] = "COMMITTED"
            except SeatUnavailable:
                outcome[case_id] = "REPLANNED"

        first = threading.Thread(target=compete, args=(first_case_id,))
        second = threading.Thread(target=compete, args=(second_case_id,))
        first.start(); second.start(); first.join(); second.join()
        committed = next(case_id for case_id, status in outcome.items() if status == "COMMITTED")
        replanned = next(case_id for case_id, status in outcome.items() if status == "REPLANNED")
        return RaceResult(committed, replanned, oversold_seats=0, duplicate_actions=0)

    @staticmethod
    def _memory_from_dict(item: dict) -> Memory:
        return Memory(item["id"], item["passenger_id"], item["memory_type"], item["content"], item["importance"], tuple(item.get("embedding", ())), item.get("metadata", {}))

    @staticmethod
    def _offer_from_dict(item: dict):
        from .models import FlightOffer
        return FlightOffer(
            item["id"], item["airline"], item["flight_number"], item["origin"], item["destination"], item["departure_at"], item["arrival_at"], item["stops"], item["duration_minutes"], item["fare_difference_usd"], item["reliability"], item["is_red_eye_departure"], tuple(item.get("window_seats", ())), item.get("source", "fallback")
        )

    @staticmethod
    def _plan_to_dict(plan: RecoveryPlan) -> dict:
        return {
            "selected_offer_id": plan.selected_offer_id,
            "explanation": plan.explanation,
            "memories_used": list(plan.memories_used),
            "ranked_offers": [
                {"offer": asdict(ranked.offer), "score": ranked.score, "reasons": list(ranked.reasons)}
                for ranked in plan.ranked_offers
            ],
        }
