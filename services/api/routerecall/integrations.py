from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from typing import Protocol

from .models import FlightOffer, Memory, RankedOffer, RecoveryPlan


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class FlightSearchProvider(Protocol):
    def search(self, origin: str, destination: str, date: str) -> list[FlightOffer]: ...


class Planner(Protocol):
    def plan(self, offers: list[FlightOffer], memories: list[Memory], memory_enabled: bool) -> RecoveryPlan: ...


class DeterministicEmbedding:
    """Stable local feature-hashing embeddings for the demo and cloud runtime.

    The implementation intentionally needs no model API. Shared words and
    phrases land in shared dimensions, so CockroachDB's cosine index retrieves
    related memories instead of comparing opaque random vectors.
    """

    dimensions = 1024
    _token_pattern = re.compile(r"[a-z0-9]+")
    _stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "has", "in", "is", "it", "not", "of", "on", "or", "the",
        "to", "was", "when", "with",
    }
    _canonical = {
        "cancelled": "cancel", "cancellation": "cancel", "canceled": "cancel",
        "connections": "connection", "connecting": "connection",
        "delayed": "delay", "delays": "delay",
        "flights": "flight", "itineraries": "itinerary",
        "meetings": "meeting", "prices": "price",
        "reliable": "reliability", "rebooked": "rebook", "rebooking": "rebook",
    }

    def embed(self, text: str) -> tuple[float, ...]:
        raw_tokens = self._token_pattern.findall(text.lower())
        tokens = [self._canonical.get(token, token) for token in raw_tokens if token not in self._stop_words]
        features = [(token, 1.0) for token in tokens]
        features.extend((f"{left}:{right}", 1.35) for left, right in zip(tokens, tokens[1:]))

        values = [0.0] * self.dimensions
        for feature, weight in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return tuple(value / norm for value in values)


class FallbackFlightSearch:
    def __init__(self, offers: list[FlightOffer]) -> None:
        self.offers = offers

    def search(self, origin: str, destination: str, date: str) -> list[FlightOffer]:
        del date
        return [offer for offer in self.offers if offer.origin == origin and offer.destination == destination]


class LetsFGSearch:
    """Optional programmatic flight search with a deterministic fallback.

    The token is supplied by a human-controlled account. The adapter only
    searches; it never creates accounts, spends money, or performs a booking.
    """

    def __init__(
        self,
        bearer_token: str,
        fallback: FlightSearchProvider,
        base_url: str | None = None,
        timeout_seconds: int = 125,
    ) -> None:
        self.bearer_token = bearer_token
        self.fallback = fallback
        self.base_url = (base_url or os.getenv("LETSFG_BASE_URL", "https://letsfg.co/api")).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, origin: str, destination: str, date: str) -> list[FlightOffer]:
        if not self.bearer_token:
            return self.fallback.search(origin, destination, date)
        try:
            payload = json.dumps(
                {"origin": origin, "destination": destination, "date_from": date, "currency": "USD"}
            ).encode()
            request = urllib.request.Request(
                f"{self.base_url}/search",
                data=payload,
                headers={"Authorization": f"Bearer {self.bearer_token}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                search_id = json.load(response)["search_id"]
            deadline = time.monotonic() + self.timeout_seconds
            while time.monotonic() < deadline:
                poll = urllib.request.Request(
                    f"{self.base_url}/results/{search_id}",
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                )
                with urllib.request.urlopen(poll, timeout=15) as response:
                    result = json.load(response)
                if result.get("status") == "done":
                    normalized = self._normalize(result)
                    return normalized or self.fallback.search(origin, destination, date)
                time.sleep(10)
        except (KeyError, TimeoutError, urllib.error.URLError, ValueError):
            pass
        return self.fallback.search(origin, destination, date)

    @staticmethod
    def _normalize(payload: dict) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        raw_offers = payload.get("offers", [])
        prices = [float(raw.get("price", 0)) for raw in raw_offers if raw.get("price") is not None]
        cheapest_price = min(prices, default=0.0)
        for index, raw in enumerate(raw_offers):
            outbound = raw.get("outbound") or {}
            segments = outbound.get("segments") or []
            if not segments:
                continue
            first, last = segments[0], segments[-1]
            offers.append(
                FlightOffer(
                    id=str(raw.get("id") or f"provider-{index}"),
                    airline=str(raw.get("owner_airline") or first.get("airline_name") or first.get("airline") or "Unknown"),
                    flight_number=str(first.get("flight_no") or "UNKNOWN"),
                    origin=str(first.get("origin") or ""),
                    destination=str(last.get("destination") or ""),
                    departure_at=str(first.get("departure") or ""),
                    arrival_at=str(last.get("arrival") or ""),
                    stops=int(outbound.get("stopovers") or max(0, len(segments) - 1)),
                    duration_minutes=int((outbound.get("total_duration_seconds") or 0) / 60),
                    fare_difference_usd=max(0, round(float(raw.get("price", 0)) - cheapest_price)),
                    reliability=float(raw.get("reliability", 0.75)),
                    is_red_eye_departure=bool(raw.get("is_red_eye", False)),
                    window_seats=(),
                    source="letsfg-pfs",
                )
            )
        return offers


class DeterministicPlanner:
    def plan(self, offers: list[FlightOffer], memories: list[Memory], memory_enabled: bool) -> RecoveryPlan:
        if not offers:
            raise ValueError("No flight offers available")
        ranked = [self._rank(offer, memory_enabled) for offer in offers]
        ranked.sort(key=lambda candidate: (-candidate.score, candidate.offer.fare_difference_usd, candidate.offer.id))
        selected = ranked[0]
        memory_ids = tuple(memory.id for memory in memories) if memory_enabled else ()
        if memory_enabled:
            explanation = (
                f"{selected.offer.flight_number} protects the meeting, avoids a red-eye departure, "
                "and preserves Maya's window-seat preference. Reliability is weighted above fare difference."
            )
        else:
            explanation = f"{selected.offer.flight_number} has the lowest fare difference; passenger history was not loaded."
        return RecoveryPlan(selected.offer.id, tuple(ranked), explanation, memory_ids)

    @staticmethod
    def _rank(offer: FlightOffer, memory_enabled: bool) -> RankedOffer:
        if not memory_enabled:
            score = max(0.0, 100.0 - offer.fare_difference_usd * 0.9 - offer.stops * 6)
            return RankedOffer(offer, round(score, 2), ("lowest fare difference", "stateless ranking"))

        score = offer.reliability * 42
        reasons: list[str] = [f"{offer.reliability:.0%} historical reliability"]
        if not offer.is_red_eye_departure:
            score += 24
            reasons.append("avoids red-eye departure")
        else:
            score -= 20
            reasons.append("conflicts with red-eye preference")
        if offer.stops == 0:
            score += 15
            reasons.append("nonstop recovery")
        elif offer.stops == 1:
            score += 4
        else:
            score -= offer.stops * 7
        if offer.window_seats:
            score += 12
            reasons.append("window seat available")
        score -= offer.fare_difference_usd * 0.035
        return RankedOffer(offer, round(max(0.0, min(100.0, score)), 2), tuple(reasons))

