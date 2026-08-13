# Publishing checklist

## Complete

- [x] Original product thesis and recovery workflow
- [x] CockroachDB schema with distributed vector index
- [x] Durable checkpoints and optimistic case versioning
- [x] Serializable seat reservation and unique idempotency ledger
- [x] Local, reproducible feature-hashing embeddings
- [x] Optional live-flight search adapter with fixture fallback
- [x] Interactive memory on/off, kill/resume and last-seat race console
- [x] Python workflow and HTTP endpoint tests
- [x] Frontend lint, production build and server-render tests
- [x] MIT license, MCP guide, demo script and third-party notice

## Requires the project owner's CockroachDB Cloud access

- [ ] Create the cluster and apply `database/migrations/001_initial.sql`
- [ ] Run the cloud API once so demonstration memories receive embeddings
- [ ] Connect the CockroachDB Cloud managed MCP server with read-only authorization
- [ ] Run one cloud case and capture its checkpoint and action-ledger rows
- [ ] Publish the web console and record the short demo
- [ ] Publish the repository and add its URL to the project page
