from __future__ import annotations

import unittest

from routerecall.integrations import DeterministicEmbedding, LetsFGSearch
from routerecall.repository import cosine_similarity


class LetsFGAdapterTests(unittest.TestCase):
    def test_local_embeddings_preserve_keyword_similarity(self) -> None:
        embeddings = DeterministicEmbedding()
        query = embeddings.embed("mechanical cancellation caused a missed connection")
        related = embeddings.embed("previous cancellation recovery after a missed connection")
        unrelated = embeddings.embed("window seat preference for a morning departure")

        self.assertEqual(1024, len(query))
        self.assertGreater(cosine_similarity(query, related), cosine_similarity(query, unrelated))

    def test_normalizes_open_source_pfs_response_shape(self) -> None:
        payload = {
            "status": "done",
            "offers": [
                {
                    "id": "off-live-1",
                    "price": 184.9,
                    "currency": "USD",
                    "owner_airline": "British Airways",
                    "outbound": {
                        "stopovers": 0,
                        "total_duration_seconds": 37500,
                        "segments": [
                            {
                                "airline": "BA",
                                "airline_name": "British Airways",
                                "flight_no": "BA286",
                                "origin": "SFO",
                                "destination": "LHR",
                                "departure": "2026-08-13T13:15:00-07:00",
                                "arrival": "2026-08-14T07:40:00+01:00",
                            }
                        ],
                    },
                }
            ],
        }

        offers = LetsFGSearch._normalize(payload)

        self.assertEqual(1, len(offers))
        self.assertEqual("BA286", offers[0].flight_number)
        self.assertEqual("SFO", offers[0].origin)
        self.assertEqual("LHR", offers[0].destination)
        self.assertEqual(625, offers[0].duration_minutes)
        self.assertEqual("letsfg-pfs", offers[0].source)
