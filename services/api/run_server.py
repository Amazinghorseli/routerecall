"""Run the RouteRecall API using the repository's private .env file."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[2]


def load_private_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


if __name__ == "__main__":
    load_private_env()
    uvicorn.run("routerecall.main:app", app_dir=str(ROOT / "services/api"), host="127.0.0.1", port=8000)
