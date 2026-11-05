CREATE TABLE IF NOT EXISTS education_drafts (
    id UUID PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    branch_id TEXT NOT NULL REFERENCES hospital_branches(id),
    department_id TEXT NOT NULL REFERENCES departments(id),
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','in_review','published','archived')),
    revision_number INT NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS education_revisions (
    id UUID PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES education_drafts(id),
    revision_number INT NOT NULL,
    content TEXT NOT NULL,
    sources JSONB NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    diff TEXT NOT NULL,
    generated BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(draft_id,revision_number)
);
CREATE TABLE IF NOT EXISTS education_events (
    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    draft_id UUID NOT NULL REFERENCES education_drafts(id),
    revision_number INT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS knowledge_feedback (
    id UUID PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES document_versions(id),
    conversation_id UUID REFERENCES conversations(id),
    actor TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('inappropriate_answer','outdated_source','other')),
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS education_revisions_immutable ON education_revisions;
CREATE TRIGGER education_revisions_immutable BEFORE UPDATE OR DELETE ON education_revisions
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
DROP TRIGGER IF EXISTS education_events_immutable ON education_events;
CREATE TRIGGER education_events_immutable BEFORE UPDATE OR DELETE ON education_events
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
DROP TRIGGER IF EXISTS knowledge_feedback_immutable ON knowledge_feedback;
CREATE TRIGGER knowledge_feedback_immutable BEFORE UPDATE OR DELETE ON knowledge_feedback
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
