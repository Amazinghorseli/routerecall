from __future__ import annotations

import os

from .fixtures import MEMORY_TEXTS, OFFERS, PASSENGER, build_demo_engine
from .integrations import (
    DeterministicEmbedding,
    DeterministicPlanner,
    FallbackFlightSearch,
    LetsFGSearch,
)
from .models import Memory
from .repository import CockroachRepository, Repository
from .workflow import RecoveryEngine


def build_runtime_engine() -> tuple[RecoveryEngine, Repository, str]:
    """Choose credential-free demo mode or the complete cloud runtime."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        engine, repository = build_demo_engine()
        return engine, repository, "demo"

    repository = CockroachRepository(database_url)
    embeddings = DeterministicEmbedding()
    repository.add_passenger(PASSENGER)
    for offer in OFFERS:
        repository.add_offer(offer)
    existing_memories = {memory.id: memory for memory in repository.list_memories(PASSENGER.id)}
    for memory_id, memory_type, content, importance in MEMORY_TEXTS:
        if memory_id in existing_memories and existing_memories[memory_id].embedding:
            continue
        repository.add_memory(
            Memory(
                memory_id,
                PASSENGER.id,
                memory_type,
                content,
                importance,
                embeddings.embed(content),
                {"seed": "routerecall-runtime"},
            )
        )

    fallback_search = FallbackFlightSearch(OFFERS)
    flight_search = LetsFGSearch(
        os.getenv("LETSFG_BEARER_TOKEN", ""),
        fallback_search,
        base_url=os.getenv("LETSFG_BASE_URL"),
    )
    planner = DeterministicPlanner()
    return RecoveryEngine(repository, embeddings, flight_search, planner), repository, "cloud"
