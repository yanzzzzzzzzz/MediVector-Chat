CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hospital_branches (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS departments (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES knowledge_documents(id),
    version_number INT NOT NULL CHECK (version_number > 0),
    version_label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'in_review', 'approved', 'superseded', 'archived')),
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_roles TEXT[] NOT NULL DEFAULT ARRAY['admin','reviewer','nurse','user'],
    allowed_users TEXT[] NOT NULL DEFAULT '{}',
    effective_from TIMESTAMPTZ NOT NULL,
    effective_until TIMESTAMPTZ,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    change_reason TEXT NOT NULL,
    legacy_import BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (document_id, version_number),
    CHECK (effective_until IS NULL OR effective_until > effective_from),
    CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS one_approved_document_version
    ON document_versions(document_id) WHERE status = 'approved';
CREATE TABLE IF NOT EXISTS document_version_scopes (
    version_id UUID NOT NULL REFERENCES document_versions(id),
    branch_id TEXT NOT NULL REFERENCES hospital_branches(id),
    department_id TEXT NOT NULL REFERENCES departments(id),
    PRIMARY KEY (version_id, branch_id, department_id)
);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS document_version_id UUID
    REFERENCES document_versions(id);
CREATE UNIQUE INDEX IF NOT EXISTS document_version_identity ON document_versions(id, document_id);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='articles_version_document_match'
                   AND conrelid='articles'::regclass) THEN
        ALTER TABLE articles ADD CONSTRAINT articles_version_document_match
            FOREIGN KEY(document_version_id, document_id) REFERENCES document_versions(id, document_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS articles_document_version_idx ON articles(document_version_id);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS owner_id TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS conversations_owner_idx ON conversations(owner_id);
CREATE TABLE IF NOT EXISTS knowledge_events (
    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id),
    version_id UUID NOT NULL REFERENCES document_versions(id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- No app API may update/delete events. Protect them from accidental application writes as well.
CREATE OR REPLACE FUNCTION prevent_knowledge_event_changes() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'knowledge events are append-only'; END $$;
DROP TRIGGER IF EXISTS knowledge_events_immutable ON knowledge_events;
CREATE TRIGGER knowledge_events_immutable BEFORE UPDATE OR DELETE ON knowledge_events
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
