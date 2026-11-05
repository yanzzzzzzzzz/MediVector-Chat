"""Idempotent additive migration. Legacy data is always unapproved and unscoped."""
import hashlib
from pathlib import Path


MIGRATION = Path(__file__).with_name("migrations") / "001_knowledge_governance.sql"


def initialize_governance(cur, organization_id="legacy"):
    cur.execute(MIGRATION.read_text())
    cur.execute(MIGRATION.with_name("002_source_attachments.sql").read_text())
    cur.execute(MIGRATION.with_name("003_education_workspace.sql").read_text())
    cur.execute(MIGRATION.with_name("004_quality_audit.sql").read_text())
    cur.execute("INSERT INTO organizations(id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (organization_id, organization_id))
    cur.execute("""
        SELECT document_id, string_agg(content, E'\\n\\n' ORDER BY chunk_index, id),
               max(title), max(source), max(version)
        FROM articles WHERE document_version_id IS NULL GROUP BY document_id
    """)
    for document_id, content, title, source, label in cur.fetchall():
        cur.execute("""INSERT INTO knowledge_documents(id, organization_id, created_by)
                       VALUES (%s, %s, 'legacy-migration') ON CONFLICT DO NOTHING""", (document_id, organization_id))
        # Stable migration identity survives repeated startups and does not grant approval.
        import uuid
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, f"medivector:legacy:{document_id}")
        cur.execute("""
            INSERT INTO document_versions
              (id, document_id, version_number, version_label, title, source, content,
               checksum, effective_from, created_by, change_reason, legacy_import)
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, now(), 'legacy-migration',
                    'Imported as unreviewed legacy data; scopes and license require review', true)
            ON CONFLICT DO NOTHING
        """, (version_id, document_id, label or "legacy-v1", title, source, content,
              hashlib.sha256(content.encode()).hexdigest()))
        cur.execute("UPDATE articles SET document_version_id = %s WHERE document_id = %s AND document_version_id IS NULL", (version_id, document_id))
