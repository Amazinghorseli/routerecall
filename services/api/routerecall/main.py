from __future__ import annotations

import os
from dataclasses import asdict

from .fixtures import DISRUPTION, PASSENGER
from .models import WorkflowStep
from .runtime import build_runtime_engine
from .workflow import CrashInjected

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install services/api/requirements.txt to run the HTTP API") from exc


app = FastAPI(title="RouteRecall API", version="0.1.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type", "authorization"],
)
engine, repository, runtime_mode = build_runtime_engine()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": runtime_mode}


@app.post("/v1/demo/cases")
def create_demo_case(memory_enabled: bool = True) -> dict:
    case = engine.start_case(PASSENGER.id, DISRUPTION, memory_enabled)
    return asdict(case)


@app.post("/v1/cases/{case_id}/run")
def run_case(case_id: str, crash_after: WorkflowStep | None = None) -> dict:
    try:
        return asdict(engine.run(case_id, crash_after))
    except CrashInjected as exc:
        return {"case_id": exc.case_id, "status": "INTERRUPTED", "checkpoint": exc.checkpoint}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recovery case not found") from exc


@app.post("/v1/cases/{case_id}/resume")
def resume_case(case_id: str) -> dict:
    try:
        return asdict(engine.resume(case_id))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/cases/{case_id}")
def get_case(case_id: str) -> dict:
    try:
        case = repository.get_case(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recovery case not found") from exc
    return {"case": asdict(case), "actions": [asdict(action) for action in repository.list_actions(case_id)]}
