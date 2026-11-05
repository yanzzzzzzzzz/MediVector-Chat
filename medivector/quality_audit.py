"""Immutable, access-controlled query provenance and explicit publication review records."""
import uuid
from contextlib import nullcontext
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from . import config
from .db import db_connection
from .knowledge import KnowledgeError, organization_principal, eligible_version_sql
from .experiment_snapshot import build_snapshot, digest
from .quality_rules import evaluate_case
from .chat import chat_parameters


def source_catalog(cur, principal, branch, department, at):
    where, params = eligible_version_sql(principal, branch, department, at)
    cur.execute(f'''SELECT v.* FROM document_versions v JOIN knowledge_documents d ON d.id=v.document_id
                    WHERE {where} ORDER BY v.id''', params)
    rows = cur.fetchall()
    catalog = {}
    for row in rows:
        cur.execute('SELECT branch_id,department_id FROM document_version_scopes WHERE version_id=%s ORDER BY branch_id,department_id', (row['id'],))
        scopes = [dict(s) for s in cur.fetchall()]
        cur.execute('SELECT id,embedding IS NOT NULL AS indexed FROM articles WHERE document_version_id=%s ORDER BY chunk_index,id', (row['id'],))
        chunks = cur.fetchall()
        catalog[str(row['id'])] = {'document_id': str(row['document_id']), 'organization_id': principal.organization_id,
                                 'version_label': row['version_label'], 'checksum': row['checksum'], 'status': row['status'],
                                 'effective_from': row['effective_from'].isoformat(), 'effective_until': row['effective_until'].isoformat() if row['effective_until'] else None,
                                 'allowed_roles': row['allowed_roles'], 'allowed_users': row['allowed_users'], 'scopes': scopes,
                                 'chunk_ids': [str(c['id']) for c in chunks], 'indexed': bool(chunks) and all(c['indexed'] for c in chunks)}
    return catalog


def query_snapshot(context):
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        catalog = source_catalog(cur, context.principal, context.branch_id, context.department_id, context.query_at)
    # Snapshot only the fully indexed corpus that can enter formal retrieval.
    catalog = {key: value for key, value in catalog.items() if value['indexed']}
    return build_snapshot(catalog, chat_model=config.CHAT_MODEL, generation=chat_parameters(0))


def record_query(context, conversation_id, question, response, snapshot, elapsed_ms, *, conn=None):
    trace_id = uuid.uuid4()
    after = query_snapshot(context)
    if after['corpus_sha256'] != snapshot['corpus_sha256']:
        snapshot = {**snapshot, 'corpus_changed_during_query': True, 'corpus_after': after['corpus']}
    snapshot = {**snapshot, 'answer_model_invoked': bool(response['references']), 'elapsed_excludes_audit_persistence': True}
    refs = [{key: ref.get(key) for key in ('index', 'uuid', 'document_id', 'document_version_id', 'distance')}
            for ref in response['references']]
    # No raw question/answer, retrieval rewrite or source text is copied into the audit trace.
    with (nullcontext(conn) if conn is not None else db_connection()) as target, target.cursor() as cur:
        cur.execute('''INSERT INTO query_traces(id,conversation_id,owner_id,question_sha256,answer_sha256,
                       references_metadata,applied_filters,snapshot,elapsed_ms) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (trace_id, conversation_id, context.principal.name, digest([str(trace_id), question]),
                     digest(response['answer']), Jsonb(refs), Jsonb(context.payload()), Jsonb(snapshot), elapsed_ms))
    return str(trace_id)


def get_trace(trace_id):
    principal = organization_principal()
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Audit records are private to the query owner; reviewers do not inherit private conversations.
        cur.execute('SELECT * FROM query_traces WHERE id=%s AND owner_id=%s', (trace_id, principal.name))
        row = cur.fetchone()
        if not row:
            raise KnowledgeError('Query trace not found or inaccessible', 404)
        return dict(row)


def review_publication(cur, principal, row, revision, reason):
    from datetime import datetime, timezone
    at = datetime.now(timezone.utc)
    catalog = source_catalog(cur, principal, row['branch_id'], row['department_id'], at)
    refs = []
    for source in revision['sources']:
        version = catalog.get(source['version_id'])
        refs.append({'index': source['index'], 'document_id': source['document_id'], 'document_version_id': source['version_id'],
                     'uuid': source['chunks'][0]['id'] if source['chunks'] else ''})
        if version and version['checksum'] != source['checksum']:
            raise KnowledgeError('Source checksum changed; publication blocked', 409)
    case = {'id': str(row['id']), 'question': row['topic'], 'answerable': True,
            'expectedDocumentVersionIds': [s['version_id'] for s in revision['sources']],
            'context': {'organization_id': principal.organization_id, 'branch_id': row['branch_id'],
                        'department_id': row['department_id'], 'role': principal.role,
                        'principal': principal.name, 'query_at': at.isoformat()},
            'trace': {'answer': revision['content'], 'references': refs}}
    report = evaluate_case(case, catalog)
    if report['status'] == 'Fail':
        raise KnowledgeError('Deterministic quality rules failed; publication blocked', 409)
    # Unknown semantics always require this explicit Reviewer/Admin action, never auto-pass.
    report['human_approval'] = {'actor': principal.name, 'role': principal.role, 'reason': reason,
                              'reviewed_at': at.isoformat(), 'revision_number': row['revision_number']}
    report['decision'] = 'approved_after_review'
    report['original_generation_snapshot'] = revision['generation_snapshot']
    snapshot = build_snapshot(catalog, chat_model=config.CHAT_MODEL, generation=chat_parameters(0))
    cur.execute('''INSERT INTO release_reviews(draft_id,revision_number,report,report_sha256,snapshot,actor,reason)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                (row['id'], row['revision_number'], Jsonb(report), digest(report), Jsonb(snapshot), principal.name, reason))


def publication_reviews(draft_id):
    from .education import load_draft, serialize
    principal = organization_principal({'admin', 'reviewer', 'nurse'})
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        row = load_draft(cur, draft_id, principal)
        serialize(cur, row, principal)  # Includes source ACL checks before exposing evidence snapshots.
        cur.execute('SELECT * FROM release_reviews WHERE draft_id=%s ORDER BY created_at', (draft_id,))
        return [dict(r) for r in cur.fetchall()]


def list_traces(conversation_id):
    principal = organization_principal()
    with db_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('''SELECT id,created_at,elapsed_ms,answer_sha256 FROM query_traces
                       WHERE conversation_id=%s AND owner_id=%s ORDER BY created_at DESC LIMIT 100''',
                    (conversation_id, principal.name))
        return [dict(row) for row in cur.fetchall()]
