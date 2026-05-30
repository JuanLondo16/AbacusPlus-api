CREATE TABLE IF NOT EXISTS document_statuses (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);
INSERT INTO document_statuses (id, name) VALUES
    (0, 'Error'), (100, 'Procesado'), (200, 'Causado'),
    (300, 'Aprobado'), (400, 'Contabilizada')
ON CONFLICT (id) DO NOTHING;
DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name='documents' AND column_name='status') = 'character varying' THEN
        ALTER TABLE documents ALTER COLUMN status TYPE INTEGER USING
            CASE status
                WHEN 'Procesado'      THEN 100
                WHEN 'procesado'      THEN 100
                WHEN 'processed'      THEN 100
                WHEN 'Causado'        THEN 200
                WHEN 'causado'        THEN 200
                WHEN 'Aprobado'       THEN 300
                WHEN 'aprobado'       THEN 300
                WHEN 'Contabilizada'  THEN 400
                WHEN 'contabilizada'  THEN 400
                ELSE 0
            END;
    END IF;
END $$;
ALTER TABLE processing_logs ADD COLUMN IF NOT EXISTS xml_filename VARCHAR(255);
ALTER TABLE processing_logs ADD COLUMN IF NOT EXISTS accounting_status VARCHAR(20);
ALTER TABLE processing_logs ADD COLUMN IF NOT EXISTS accounting_error TEXT;
ALTER TABLE documents ALTER COLUMN issuer_phone TYPE VARCHAR(100), ALTER COLUMN receiver_phone TYPE VARCHAR(100);
ALTER TABLE issuers ADD COLUMN IF NOT EXISTS tipo_contribuyente VARCHAR(50);
-- Eliminar campo provider de integration_chart_accounts (plan de cuentas es agnóstico al proveedor)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='integration_chart_accounts' AND column_name='provider'
    ) THEN
        ALTER TABLE integration_chart_accounts DROP CONSTRAINT IF EXISTS uq_chart_account_provider_key_code;
        ALTER TABLE integration_chart_accounts DROP COLUMN provider;
        ALTER TABLE integration_chart_accounts DROP CONSTRAINT IF EXISTS uq_chart_account_key_code;
        ALTER TABLE integration_chart_accounts DROP COLUMN account_key;
        ALTER TABLE integration_chart_accounts
            ADD CONSTRAINT uq_chart_account_code UNIQUE (code);
    END IF;
END $$;
