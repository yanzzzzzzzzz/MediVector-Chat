CREATE TABLE IF NOT EXISTS query_traces (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL,
    owner_id TEXT NOT NULL,
    question_sha256 TEXT NOT NULL,
    answer_sha256 TEXT NOT NULL,
    references_metadata JSONB NOT NULL,
    applied_filters JSONB NOT NULL,
    snapshot JSONB NOT NULL,
    elapsed_ms DOUBLE PRECISION NOT NULL CHECK(elapsed_ms >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS release_reviews (
    id UUID PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES education_drafts(id),
    revision_number INT NOT NULL,
    report JSONB NOT NULL,
    report_sha256 TEXT NOT NULL,
    snapshot JSONB NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS query_traces_immutable ON query_traces;
CREATE TRIGGER query_traces_immutable BEFORE UPDATE OR DELETE ON query_traces
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
DROP TRIGGER IF EXISTS release_reviews_immutable ON release_reviews;
CREATE TRIGGER release_reviews_immutable BEFORE UPDATE OR DELETE ON release_reviews
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
ALTER TABLE knowledge_feedback ADD COLUMN IF NOT EXISTS query_trace_id UUID REFERENCES query_traces(id);

-- Audit IDs survive the normal deletion of raw conversation content; no source text is retained here.
ALTER TABLE query_traces DROP CONSTRAINT IF EXISTS query_traces_conversation_id_fkey;
ALTER TABLE knowledge_feedback DROP CONSTRAINT IF EXISTS knowledge_feedback_conversation_id_fkey;
ALTER TABLE education_revisions ADD COLUMN IF NOT EXISTS generation_snapshot JSONB;
