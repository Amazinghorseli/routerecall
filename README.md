# RouteRecall

**The flight-disruption recovery agent that remembers what matters — and survives its own crashes.**

RouteRecall turns a cancellation into a durable, explainable recovery workflow. It recalls passenger constraints, searches replacement flights, ranks them against remembered preferences, pauses at a human approval boundary, reserves exactly once, and learns from the result.

CockroachDB is the system of record for the agent: passenger memory, vector retrieval, workflow checkpoints, scarce-seat transactions and the idempotent action ledger all live in one database.

## What the demo proves

1. Trigger Maya Chen's cancelled SFO–JFK connection to London.
2. RouteRecall recalls her constraints: avoid red-eye departures, prefer a window seat, protect the 08:30 meeting and prioritize reliability during disruption.
3. Compare **Memory ON** (BA286, best policy fit) with **Memory OFF** (UA930, lowest fare).
4. Kill the agent after approval and resume it from the latest durable checkpoint.
5. Verify that one stable idempotency key produces one reservation, even after a retry.
6. Run **Race for last seat** and watch one worker commit while the other replans without overselling.

## CockroachDB integration

RouteRecall meaningfully uses two CockroachDB tools:

- **Distributed vector index:** each memory has a 1,024-dimensional local feature-hashing embedding. `agent_memories` uses a passenger prefix plus `vector_cosine_ops`, and the recovery workflow queries it with cosine distance. Vector and transactional state stay consistent because they share the same database.
- **CockroachDB Cloud managed MCP Server:** developers can inspect cases, checkpoints, recalled memory and the action ledger through the managed MCP endpoint. The recommended demo connection uses read-only authorization; see [docs/mcp-audit.md](docs/mcp-audit.md).

CockroachDB also provides the correctness boundary:

- `workflow_checkpoints` preserves completed steps across process failure.
- `action_ledger.idempotency_key` prevents duplicate external actions.
- seat inventory and its reservation ledger entry commit in one serializable transaction.
- optimistic case versions reject competing workflow updates.

The local embedding implementation needs no external model API. Shared tokens and phrases map to shared vector dimensions, giving the demo reproducible similarity results while exercising the real CockroachDB vector query path.

## Run locally

Requirements: Node.js 22+ and Python 3.12+.

Run the interactive console:

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. The console includes a deterministic fallback so every interaction remains usable without cloud credentials.

Run the workflow API:

```bash
python -m pip install -r services/api/requirements.txt
PYTHONPATH=services/api uvicorn routerecall.main:app --reload --port 8000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` before starting the web console to connect it to the API.

Run the command-line scenario:

```bash
PYTHONPATH=services/api python -m routerecall.demo
```

On Windows PowerShell, use `$env:PYTHONPATH="services/api"` before the Python commands.

## CockroachDB Cloud setup

1. Create a CockroachDB Cloud cluster and a SQL user.
2. From the cluster's **Connect** dialog, copy the PostgreSQL connection string. Keep it private.
3. Copy `.env.example` to `.env`, set `DATABASE_URL`, then run the secure bootstrap:

   ```bash
   python -m pip install -r services/api/requirements.txt
   PYTHONPATH=services/api python database/bootstrap_cloud.py
   ```

   The bootstrap retains `sslmode=verify-full`, uses a trusted CA bundle, creates the schema and vector index, seeds embedded memories, and runs or reuses one cloud verification case. Its output never prints the connection string.

4. Start the API. At startup, RouteRecall inserts the demonstration offers and backfills deterministic embeddings for seed memories.
5. The repository's `.vscode/mcp.json` contains the cluster-scoped managed MCP endpoint with no secret. In VS Code, start `cockroachdb-cloud`, authenticate with OAuth, and grant read-only access for demonstrations.

The database connection uses `sslmode=verify-full`. Do not commit `.env`, connection strings, passwords, API keys or MCP bearer tokens.

## Tests

```bash
python -m pip install -r services/api/requirements-dev.txt
PYTHONPATH=services/api python -m unittest discover -s services/api/tests -v
npm run lint
npm test
```

The test suite verifies memory-aware selection, meaningful local vector similarity, crash recovery, idempotent actions, concurrent seat contention, API behavior and the production web bundle.

## Repository map

```text
app/                         interactive reviewer console
services/api/routerecall/    workflow, memory and CockroachDB adapters
services/api/tests/          API, retrieval and resilience tests
database/                    CockroachDB migration and demonstration records
docs/                        MCP guide, demo script and project checklist
worker/                      web-console hosting entry point
```

Use [docs/demo-script.md](docs/demo-script.md) for the short walkthrough and [docs/submission-checklist.md](docs/submission-checklist.md) for the remaining publishing work.

## Safety and scope

This is a prototype, not an airline ticketing system. All bundled passenger details, itineraries, prices and inventory are fictional. The optional live-search adapter performs searches only; real purchase or exchange operations require an authorized airline API, explicit passenger approval and provider-specific validation.

## License

MIT — see [LICENSE](LICENSE).
