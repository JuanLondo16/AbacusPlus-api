-- Habilitar extensión pgvector para soporte de columnas vectoriales
CREATE EXTENSION IF NOT EXISTS vector;

-- ── accounting-rules-service: tablas en DB default (refuerzo)
-- La creación real por-tenant ocurre vía lifespan + /internal/provision-tenant
CREATE TABLE IF NOT EXISTS accounting_rules (
    id                      SERIAL PRIMARY KEY,
    match_key_type          VARCHAR(20) NOT NULL,
    issuer_nit              VARCHAR(30),
    description_embedding   vector(768),
    ciiu_code               VARCHAR(10),
    item_keywords           TEXT[],
    suggested_debit_account  VARCHAR(20) NOT NULL,
    suggested_credit_account VARCHAR(20) NOT NULL,
    suggested_tax_accounts   JSONB NOT NULL DEFAULT '{}',
    suggested_cost_center   VARCHAR(50),
    confidence_score        FLOAT NOT NULL DEFAULT 0.60,
    approval_count          INTEGER NOT NULL DEFAULT 0,
    edit_count              INTEGER NOT NULL DEFAULT 0,
    last_approved_at        TIMESTAMP,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_accounting_rules_issuer_nit    ON accounting_rules (issuer_nit);
CREATE INDEX IF NOT EXISTS ix_accounting_rules_match_key_type ON accounting_rules (match_key_type);
CREATE INDEX IF NOT EXISTS ix_accounting_rules_is_active      ON accounting_rules (is_active);

CREATE TABLE IF NOT EXISTS rule_match_attempts (
    id                  SERIAL PRIMARY KEY,
    document_id         INTEGER NOT NULL,
    rule_id             INTEGER,
    match_level         VARCHAR(10) NOT NULL,
    match_key_type      VARCHAR(20),
    confidence_at_match FLOAT NOT NULL DEFAULT 0.0,
    llm_used_context    BOOLEAN NOT NULL DEFAULT FALSE,
    final_approved      BOOLEAN,
    suggested_payload   JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_rule_match_attempts_document_id ON rule_match_attempts (document_id);
