"""Institutional immutable source versions, review state machine and scoped reads."""
import hashlib
import uuid
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .chunking import chunk_manifest
from .api_auth import current_principal
from .db import db_connection
from .knowledge_schemas import CatalogEntry, CreateVersion, TransitionRequest
from .openai_client import embed_texts, require_openai_api_key


class KnowledgeError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def organization_principal(roles=None):
    principal = current_principal.get()
    if principal is None or not principal.organization_id:
        raise KnowledgeError("An authenticated organization account is required", 403)
    if roles and principal.role not in roles:
        raise KnowledgeError("This role cannot perform the requested action", 403)
    return principal


def check_scopes(principal, scopes):
    if any(s.branch_id not in principal.branch_ids or s.department_id not in principal.department_ids for s in scopes):
        raise KnowledgeError("Scope is outside the account grants", 403)


def eligible_version_sql(principal, branch_id, department_id, at):
    """Shared predicate used before vector ranking and by citation reads."""
    return """
        d.organization_id = %s AND v.status = 'approved'
        AND v.effective_from <= %s AND (v.effective_until IS NULL OR v.effective_until > %s)
        AND %s = ANY(v.allowed_roles)
        AND (cardinality(v.allowed_users) = 0 OR %s = ANY(v.allowed_users))
        AND EXISTS (SELECT 1 FROM document_version_scopes s WHERE s.version_id = v.id
                    AND s.branch_id = %s AND s.department_id = %s)
    """, [principal.organization_id, at, at, principal.role, principal.name, branch_id, department_id]


def staff_version_sql(principal):
    # Readers see only current approved versions; authorized staff may review drafts/history.
    return """
        d.organization_id = %s AND %s = ANY(v.allowed_roles)
        AND (cardinality(v.allowed_users) = 0 OR %s = ANY(v.allowed_users))
        AND EXISTS (SELECT 1 FROM document_version_scopes s WHERE s.version_id = v.id
                    AND s.branch_id = ANY(%s) AND s.department_id = ANY(%s))
    """, [principal.organization_id, principal.role, principal.name, list(principal.branch_ids), list(principal.department_ids)]


def visible_version(cur, version_id, principal, *, lock=False):
    where, params = staff_version_sql(principal)
    if principal.role == "user":
        where += " AND v.status = 'approved' AND v.effective_from <= now() AND (v.effective_until IS NULL OR v.effective_until > now())"
    cur.execute(f"SELECT v.* FROM document_versions v JOIN knowledge_documents d ON d.id=v.document_id WHERE v.id=%s AND {where}" + (" FOR UPDATE OF v" if lock else ""), [version_id, *params])
    row = cur.fetchone()
    if not row:
        raise KnowledgeError("Document version not found or inaccessible", 404)
    return row


def serialize_version(cur, row, *, include_content=True):
    row = dict(row)
    row["id"], row["document_id"] = str(row["id"]), str(row["document_id"])
    for key in ("effective_from", "effective_until", "created_at", "approved_at"):
        if row[key] is not None:
            row[key] = row[key].isoformat()
    cur.execute("SELECT branch_id, department_id FROM document_version_scopes WHERE version_id=%s ORDER BY branch_id, department_id", (row["id"],))
    row["scopes"] = [dict(scope) for scope in cur.fetchall()]
    if not include_content:
        row.pop("content", None)
    return row


def catalog():
    principal = organization_principal()
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, name FROM hospital_branches WHERE id=ANY(%s) ORDER BY id", (list(principal.branch_ids),))
        branches = cur.fetchall()
        cur.execute("SELECT id, name FROM departments WHERE id=ANY(%s) ORDER BY id", (list(principal.department_ids),))
        departments = cur.fetchall()
    return {"organization_id": principal.organization_id, "principal": principal.name, "role": principal.role,
            "branches": branches, "departments": departments}


def upsert_catalog(kind: str, entry: CatalogEntry):
    principal = organization_principal({"admin"})
    table = {"branches": "hospital_branches", "departments": "departments"}[kind]
    grants = principal.branch_ids if kind == "branches" else principal.department_ids
    if entry.id not in grants:
        raise KnowledgeError("Catalog ID is outside the account grants", 403)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO {table}(id, organization_id, name) VALUES (%s, %s, %s) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name", (entry.id, principal.organization_id, entry.name))
    return entry.model_dump()


def validate_catalog_scopes(cur, principal, scopes):
    check_scopes(principal, scopes)
    for scope in scopes:
        cur.execute("SELECT 1 FROM hospital_branches b CROSS JOIN departments dep WHERE b.id=%s AND dep.id=%s AND b.organization_id=%s AND dep.organization_id=%s", (scope.branch_id, scope.department_id, principal.organization_id, principal.organization_id))
        if not cur.fetchone():
            raise KnowledgeError("Branch or department is not registered for this organization")


def create_version(payload: CreateVersion):
    principal = organization_principal({"admin", "nurse", "reviewer"})
    check_scopes(principal, payload.scopes)
    if principal.role not in payload.allowed_roles or (payload.allowed_users and principal.name not in payload.allowed_users):
        raise KnowledgeError("The creator must retain access to the submitted version")
    document_id = payload.document_id or uuid.uuid4()
    version_id = uuid.uuid4()
    # Validate ownership/catalog before paying for embeddings. Recheck in the write transaction.
    with db_connection() as conn, conn.cursor() as cur:
        validate_catalog_scopes(cur, principal, payload.scopes)
        if payload.document_id:
            where, params = staff_version_sql(principal)
            cur.execute(f"SELECT 1 FROM document_versions v JOIN knowledge_documents d ON d.id=v.document_id WHERE d.id=%s AND {where} LIMIT 1", [document_id, *params])
            if not cur.fetchone():
                raise KnowledgeError("Document not found or inaccessible", 404)
    manifest = chunk_manifest(payload.content, document_id=str(document_id), version=str(version_id), strategy=payload.chunk_strategy,
                              max_tokens=payload.max_tokens, overlap=payload.overlap_tokens)
    vectors = embed_texts(require_openai_api_key(), [c["content"] for c in manifest["chunks"]])
    if len(vectors) != len(manifest["chunks"]):
        raise KnowledgeError("Embedding response count does not match chunks")
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        validate_catalog_scopes(cur, principal, payload.scopes)
        cur.execute("INSERT INTO knowledge_documents(id, organization_id, created_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (document_id, principal.organization_id, principal.name))
        cur.execute("SELECT id FROM knowledge_documents WHERE id=%s AND organization_id=%s FOR UPDATE", (document_id, principal.organization_id))
        if not cur.fetchone():
            raise KnowledgeError("Document not found", 404)
        cur.execute("SELECT COALESCE(max(version_number),0)+1 AS next FROM document_versions WHERE document_id=%s", (document_id,))
        number = cur.fetchone()["next"]
        cur.execute("""
            INSERT INTO document_versions
             (id,document_id,version_number,version_label,title,source,source_url,license,audience,
              content,checksum,effective_from,effective_until,created_by,change_reason,allowed_roles,allowed_users)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """, (version_id, document_id, number, payload.version_label, payload.title, payload.source,
              payload.source_url, payload.license, payload.audience, payload.content, manifest["source_sha256"],
              payload.effective_from, payload.effective_until, principal.name, payload.change_reason,
              payload.allowed_roles, payload.allowed_users))
        row = cur.fetchone()
        for scope in {(s.branch_id, s.department_id) for s in payload.scopes}:
            cur.execute("INSERT INTO document_version_scopes VALUES (%s,%s,%s)", (version_id, *scope))
        for chunk, vector in zip(manifest["chunks"], vectors):
            metadata = {k: v for k, v in chunk.items() if k != "content"}
            metadata.update(source_sha256=manifest["source_sha256"], version_id=str(version_id), version_label=payload.version_label)
            cur.execute("""INSERT INTO articles(document_id,document_version_id,title,source,version,audience,
                           content,chunk_index,chunk_count,embedding,chunk_metadata)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (document_id, version_id, payload.title, payload.source, payload.version_label, payload.audience,
                         chunk["content"], chunk["chunk_index"], len(vectors), vector, Jsonb(metadata)))
        cur.execute("INSERT INTO knowledge_events(document_id,version_id,actor,action,to_status,reason) VALUES (%s,%s,%s,'create','draft',%s)", (document_id, version_id, principal.name, payload.change_reason))
        return serialize_version(cur, row)


def transition(version_id, request: TransitionRequest):
    reviewer_actions = {"approve", "return", "withdraw"}
    principal = organization_principal({"admin", "reviewer"} if request.action in reviewer_actions else {"admin", "reviewer", "nurse"})
    transitions = {"submit": ("draft", "in_review"), "approve": ("in_review", "approved"), "return": ("in_review", "draft")}
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = visible_version(cur, version_id, principal)
        # Serialize all transitions and version creation for a document; lock ordering is consistent.
        cur.execute("SELECT id FROM knowledge_documents WHERE id=%s FOR UPDATE", (row["document_id"],))
        row = visible_version(cur, version_id, principal, lock=True)
        from .knowledge_schemas import Scope
        cur.execute("""SELECT s.branch_id,s.department_id FROM document_version_scopes s
                       JOIN document_versions v ON v.id=s.version_id
                       WHERE v.id=%s OR (v.document_id=%s AND v.status='approved' AND %s)""", (version_id, row["document_id"], request.action == 'approve'))
        check_scopes(principal, [Scope(**scope) for scope in cur.fetchall()])
        before = row["status"]
        if request.action == "withdraw":
            if before not in {"approved", "superseded"}:
                raise KnowledgeError("Only approved or superseded versions can be withdrawn", 409)
            after = "archived"
        else:
            expected, after = transitions[request.action]
            if before != expected:
                raise KnowledgeError(f"Cannot {request.action} a {before} version", 409)
        if after == "approved":
            if not row["license"].strip():
                raise KnowledgeError("License must be recorded before approval", 409)
            if row["effective_from"] > datetime.now(timezone.utc):
                raise KnowledgeError("Future versions can be approved when their effective period starts", 409)
            cur.execute("SELECT 1 FROM document_versions WHERE document_id=%s AND version_number>%s AND approved_at IS NOT NULL LIMIT 1", (row["document_id"], row["version_number"]))
            if cur.fetchone():
                raise KnowledgeError("A newer version has already been approved; create a new revision instead", 409)
            if row["effective_until"] and row["effective_until"] <= datetime.now(timezone.utc):
                raise KnowledgeError("Cannot approve an expired version", 409)
            cur.execute("UPDATE document_versions SET status='superseded' WHERE document_id=%s AND status='approved' RETURNING id", (row["document_id"],))
            for old in cur.fetchall():
                cur.execute("INSERT INTO knowledge_events(document_id,version_id,actor,action,from_status,to_status,reason) VALUES (%s,%s,%s,'supersede','approved','superseded',%s)", (row["document_id"], old["id"], principal.name, request.reason))
            cur.execute("UPDATE document_versions SET status='approved',approved_by=%s,approved_at=now() WHERE id=%s RETURNING *", (principal.name, version_id))
        else:
            cur.execute("UPDATE document_versions SET status=%s WHERE id=%s RETURNING *", (after, version_id))
        row = cur.fetchone()
        cur.execute("INSERT INTO knowledge_events(document_id,version_id,actor,action,from_status,to_status,reason) VALUES (%s,%s,%s,%s,%s,%s,%s)", (row["document_id"], version_id, principal.name, request.action, before, after, request.reason))
        return serialize_version(cur, row)


def list_versions(document_id=None):
    principal = organization_principal()
    where, params = staff_version_sql(principal)
    if principal.role == "user":
        where += " AND v.status='approved' AND v.effective_from<=now() AND (v.effective_until IS NULL OR v.effective_until>now())"
    if document_id:
        where += " AND v.document_id=%s"
        params.append(document_id)
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT v.* FROM document_versions v JOIN knowledge_documents d ON d.id=v.document_id WHERE {where} ORDER BY v.created_at DESC,v.version_number DESC LIMIT 500", params)
        rows = cur.fetchall()
        return [serialize_version(cur, row, include_content=False) for row in rows]


def get_version(version_id):
    principal = organization_principal()
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        return serialize_version(cur, visible_version(cur, version_id, principal))


def history(document_id):
    principal = organization_principal({"admin", "reviewer", "nurse"})
    where, params = staff_version_sql(principal)
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT e.* FROM knowledge_events e JOIN document_versions v ON v.id=e.version_id JOIN knowledge_documents d ON d.id=v.document_id WHERE d.id=%s AND {where} ORDER BY e.sequence", [document_id, *params])
        return [dict(row) for row in cur.fetchall()]


def citation_chunk(chunk_id, branch_id, department_id):
    from .retrieval_context import context_for_request
    context = context_for_request(branch_id, department_id)
    if context is None:
        raise KnowledgeError("Institutional citation reads require an organization account", 403)
    where, params = eligible_version_sql(context.principal, context.branch_id, context.department_id, context.query_at)
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT a.id AS chunk_id,v.id AS document_version_id,v.document_id,
                        v.version_label,a.content,a.chunk_metadata,v.source,v.source_url,v.checksum,
                        v.approved_at,v.effective_from,v.effective_until
                        FROM articles a JOIN document_versions v ON v.id=a.document_version_id
                        JOIN knowledge_documents d ON d.id=v.document_id
                        WHERE a.id=%s AND {where}""", [chunk_id, *params])
        row = cur.fetchone()
        if not row:
            raise KnowledgeError("Citation not found, withdrawn, expired or inaccessible", 404)
        return {**dict(row), "applied_filters": context.payload()}


def redact_inaccessible_history(messages):
    principal = current_principal.get()
    if not principal or not principal.organization_id:
        return messages
    result = []
    for message in messages:
        redacted = False
        for ref in message.get("references", []):
            meta = ref.get("chunk_metadata", {})
            try:
                row = citation_chunk(uuid.UUID(ref["uuid"]), meta.get("branch_id"), meta.get("department_id"))
                if str(row["document_version_id"]) != ref.get("document_version_id"):
                    redacted = True
            except (KnowledgeError, ValueError, KeyError, TypeError):
                redacted = True
        result.append({"role": message["role"], "content": "此回覆引用的資料已撤回、過期或不再可存取；請重新查詢。", "references": []}
                      if redacted else message)
    return result


def corpus_manifest(branch_id, department_id):
    from .config import EMBEDDING_MODEL
    from .retrieval_context import context_for_request
    import json
    context = context_for_request(branch_id, department_id)
    if context is None:
        raise KnowledgeError("Corpus manifests require an organization account", 403)
    where, params = eligible_version_sql(context.principal, branch_id, department_id, context.query_at)
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT v.id::text AS version_id,v.document_id::text,v.version_label,v.version_number,
                            v.checksum,v.status,v.effective_from,v.effective_until,
                            array_agg(a.id::text ORDER BY a.chunk_index,a.id) AS chunk_ids
                         FROM document_versions v JOIN knowledge_documents d ON d.id=v.document_id
                         JOIN articles a ON a.document_version_id=v.id WHERE {where}
                         GROUP BY v.id ORDER BY v.document_id,v.version_number""", params)
        versions = []
        for row in cur.fetchall():
            item = dict(row)
            for key in ("effective_from", "effective_until"):
                item[key] = item[key].isoformat() if item[key] else None
            versions.append(item)
    frozen = {"format_version": 1, "organization_id": context.principal.organization_id,
              "branch_id": branch_id, "department_id": department_id, "embedding_model": EMBEDDING_MODEL,
              "versions": versions}
    return {**frozen, "query_at": context.query_at.isoformat(),
            "manifest_sha256": hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
