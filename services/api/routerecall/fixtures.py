from __future__ import annotations

from .integrations import DeterministicEmbedding, DeterministicPlanner, FallbackFlightSearch
from .models import Disruption, FlightOffer, Memory, Passenger
from .repository import InMemoryRepository
from .workflow import RecoveryEngine


PASSENGER = Passenger("maya-chen", "Maya Chen", "us-west")

DISRUPTION = Disruption(
    id="disruption-ua1847",
    flight_number="UA1847",
    origin="SFO",
    destination="JFK",
    final_destination="LHR",
    reason="Mechanical cancellation causing missed transatlantic connection",
    meeting_deadline="2026-08-14T08:30:00+01:00",
    travel_date="2026-08-13",
)

OFFERS = [
    FlightOffer("offer-ba286", "British Airways", "BA286", "SFO", "LHR", "2026-08-13T13:15:00-07:00", "2026-08-14T07:40:00+01:00", 0, 625, 184, 0.91, False, ("1A",)),
    FlightOffer("offer-ua930", "United", "UA930", "SFO", "LHR", "2026-08-13T19:45:00-07:00", "2026-08-14T14:10:00+01:00", 0, 625, 42, 0.84, True, ()),
    FlightOffer("offer-ac742", "Air Canada", "AC742", "SFO", "LHR", "2026-08-13T12:05:00-07:00", "2026-08-14T10:40:00+01:00", 1, 875, 96, 0.78, False, ("2F",)),
]

MEMORY_TEXTS = [
    ("mem-red-eye", "PREFERENCE", "Avoid red-eye departures; an overnight arrival is acceptable but an overnight departure is not.", 0.96),
    ("mem-window", "PREFERENCE", "Prefer a window seat whenever one is available.", 0.82),
    ("mem-meeting", "TRIP_CONSTRAINT", "Protect the London meeting before 08:30 BST even when the fare difference is higher.", 1.0),
    ("mem-recovery-078", "RECOVERY_OUTCOME", "After a mechanical cancellation and missed connection in March, Maya accepted a more expensive nonstop itinerary because reliability mattered more than price.", 0.89),
]


def build_demo_engine() -> tuple[RecoveryEngine, InMemoryRepository]:
    repository = InMemoryRepository()
    embeddings = DeterministicEmbedding()
    repository.add_passenger(PASSENGER)
    for offer in OFFERS:
        repository.add_offer(offer)
    for memory_id, memory_type, content, importance in MEMORY_TEXTS:
        repository.add_memory(Memory(memory_id, PASSENGER.id, memory_type, content, importance, embeddings.embed(content)))
    engine = RecoveryEngine(repository, embeddings, FallbackFlightSearch(OFFERS), DeterministicPlanner())
    return engine, repository
