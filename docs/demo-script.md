# RouteRecall demo script (2:30 target)

## 0:00–0:20 — Problem and promise

“A cancelled flight is not one query. It is a long-running workflow with personal constraints, scarce inventory and side effects that must never run twice. RouteRecall is the recovery agent that remembers.”

Show the cancelled SFO–JFK connection and Maya's London meeting deadline. Click **Trigger disruption**.

## 0:20–0:55 — Memory changes the decision

Point to the recalled context: avoid a red-eye departure, prefer a window seat, protect the 08:30 meeting and prioritize reliability during disruption.

Toggle **Persistent memory** off. The policy chooses UA930 because it has the lowest fare. Toggle memory on. It chooses BA286 because passenger constraints outweigh the additional cost.

Say: “The embeddings and structured case state live together in CockroachDB. A passenger-prefixed cosine vector index retrieves the relevant memories.”

## 0:55–1:30 — Kill and resume

Wait until **Human gate**, then click **Kill agent**.

Say: “The process is gone, but its latest completed step is a durable CockroachDB checkpoint.”

Let auto-resume finish. Point to **Duplicate actions prevented: 1** and the single reservation entry.

## 1:30–2:00 — Race for the last seat

Click **Race for last seat**. Two workers contend for seat 1A. One commits and the other replans. Point to **Seats oversold: 0** and **Duplicate actions: 0**.

Say: “The seat update and action ledger share one serializable transaction. Agent intelligence cannot bypass database correctness.”

## 2:00–2:20 — MCP proof

Show the same case through the CockroachDB Cloud managed MCP connection:

- list the case and its version;
- list checkpoints in order;
- list the single reservation idempotency key;
- run the read-only semantic recall query from `docs/mcp-audit.md`.

## 2:20–2:30 — Close

“RouteRecall can stop and restart. CockroachDB makes it remember exactly where it was, what mattered and what it already did.”
