from __future__ import annotations

import json

from .fixtures import DISRUPTION, PASSENGER, build_demo_engine


def main() -> None:
    engine, _ = build_demo_engine()
    case = engine.start_case(PASSENGER.id, DISRUPTION, memory_enabled=True, case_id="RR-LOCAL-DEMO")
    completed = engine.run(case.id)
    print(json.dumps(completed.context["plan"], indent=2))


if __name__ == "__main__":
    main()
