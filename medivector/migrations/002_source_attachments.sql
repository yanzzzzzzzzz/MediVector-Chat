CREATE TABLE IF NOT EXISTS source_attachments (
    version_id UUID PRIMARY KEY REFERENCES document_versions(id),
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK (content_type = 'application/pdf'),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    data BYTEA NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 8388608),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS source_attachment_immutable ON source_attachments;
CREATE TRIGGER source_attachment_immutable BEFORE UPDATE OR DELETE ON source_attachments
FOR EACH ROW EXECUTE FUNCTION prevent_knowledge_event_changes();
