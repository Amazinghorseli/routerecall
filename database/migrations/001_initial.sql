-- RouteRecall CockroachDB schema.
-- Apply with: cockroach sql --url "$DATABASE_URL" --file database/migrations/001_initial.sql

SET CLUSTER SETTING feature.vector_index.enabled = true;

CREATE TABLE IF NOT EXISTS passengers (
    id STRING PRIMARY KEY,
    name STRING NOT NULL,
    home_region STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_memories (
    id STRING PRIMARY KEY,
    passenger_id STRING NOT NULL REFERENCES passengers (id),
    memory_type STRING NOT NULL,
    content STRING NOT NULL,
    importance FLOAT8 NOT NULL CHECK (importance BETWEEN 0 AND 1),
    embedding VECTOR(1024),
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX memories_by_passenger (passenger_id, importance DESC, created_at DESC),
    VECTOR INDEX memory_vector_idx (passenger_id, embedding vector_cosine_ops)
);

CREATE TABLE IF NOT EXISTS flight_offers (
    id STRING PRIMARY KEY,
    airline STRING NOT NULL,
    flight_number STRING NOT NULL,
    origin STRING NOT NULL,
    destination STRING NOT NULL,
    departure_at STRING NOT NULL,
    arrival_at STRING NOT NULL,
    stops INT2 NOT NULL,
    duration_minutes INT4 NOT NULL,
    fare_difference_usd INT4 NOT NULL,
    reliability FLOAT8 NOT NULL,
    is_red_eye_departure BOOL NOT NULL,
    window_seats JSONB NOT NULL DEFAULT '[]'::JSONB,
    source STRING NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX offers_by_route (origin, destination)
);

CREATE TABLE IF NOT EXISTS seat_inventory (
    offer_id STRING NOT NULL REFERENCES flight_offers (id),
    seat_number STRING NOT NULL,
    status STRING NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'HELD')),
    recovery_case_id STRING,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (offer_id, seat_number)
);

CREATE TABLE IF NOT EXISTS recovery_cases (
    id STRING PRIMARY KEY,
    passenger_id STRING NOT NULL REFERENCES passengers (id),
    disruption JSONB NOT NULL,
    memory_enabled BOOL NOT NULL DEFAULT true,
    current_step STRING NOT NULL,
    status STRING NOT NULL,
    version INT8 NOT NULL DEFAULT 0,
    context JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX cases_by_passenger (passenger_id, created_at DESC)
);

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    case_id STRING NOT NULL REFERENCES recovery_cases (id),
    step STRING NOT NULL,
    state JSONB NOT NULL,
    version INT8 NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, version)
);

CREATE TABLE IF NOT EXISTS action_ledger (
    id STRING PRIMARY KEY,
    recovery_case_id STRING NOT NULL REFERENCES recovery_cases (id),
    action_type STRING NOT NULL,
    idempotency_key STRING NOT NULL UNIQUE,
    status STRING NOT NULL,
    input JSONB NOT NULL,
    output JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX actions_by_case (recovery_case_id, created_at)
);

CREATE TABLE IF NOT EXISTS mcp_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recovery_case_id STRING,
    tool_name STRING NOT NULL,
    query_fingerprint STRING,
    readonly BOOL NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    INDEX audit_by_case (recovery_case_id, created_at DESC)
);
