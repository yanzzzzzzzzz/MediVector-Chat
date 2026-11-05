import hashlib
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import sql

from medivector.api_auth import Principal, current_principal
from medivector.db import db_connection, init_db, init_tables
from medivector.server import app


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "requires isolated test PostgreSQL")
class KnowledgeGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"API_USERS": "{}"}):
            init_db()

    def setUp(self):
        suffix = uuid.uuid4().hex
        self.org = "hospital-" + suffix
        def account(role, token, org=None, branches=None):
            return {"role": role, "token": token * 32, "organization_id": org or self.org,
                    "branch_ids": branches or ["a", "b"], "department_ids": ["general", "lab"]}
        self.users = {"admin": account("admin", "a"), "nurse": account("nurse", "n"),
                      "reviewer": account("reviewer", "r"), "reader": account("user", "u", branches=["a"]),
                      "outsider": account("admin", "o", org="outside-" + suffix)}
        self.env = patch.dict(os.environ, {"API_USERS": json.dumps(self.users), "API_RATE_LIMIT_PER_MINUTE": "10000"})
        self.env.start()
        init_db()
        self.client = TestClient(app, client=("192.0.2.1", 1234))
        self.vector = [1.] + [0.] * 1535
        self.embeddings = patch("medivector.knowledge.embed_texts", side_effect=lambda key, texts: [self.vector for _ in texts])
        self.embeddings.start()
        self.key = patch("medivector.knowledge.require_openai_api_key", return_value="fake")
        self.key.start()
        self.retrieval_key = patch("medivector.retrieval_api.require_openai_api_key", return_value="fake")
        self.retrieval_key.start()
        self.retrieval_embedding = patch("medivector.retrieval.embed_texts", return_value=[self.vector])
        self.retrieval_embedding.start()
        for branch in ("a", "b"):
            self.assertEqual(self.request("PUT", "/api/knowledge/catalog/branches", {"id": branch, "name": branch}).status_code, 200)
        for department in ("general", "lab"):
            self.assertEqual(self.request("PUT", "/api/knowledge/catalog/departments", {"id": department, "name": department}).status_code, 200)

    def tearDown(self):
        for patcher in (self.retrieval_embedding, self.retrieval_key, self.key, self.embeddings):
            patcher.stop()
        self.env.stop()
        # Only random test organization schemas are removed; event guards do not obstruct DROP SCHEMA.
        with db_connection() as conn, conn.cursor() as cur:
            for name in ("admin", "outsider"):
                principal = Principal.from_config(name, self.users[name])
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(principal.schema)))

    def request(self, method, path, payload=None, user="admin"):
        return self.client.request(method, path, json=payload, headers={"Authorization": "Bearer " + self.users[user]["token"]})

    def payload(self, **changes):
        now = datetime.now(timezone.utc)
        return {"version_label": "v1", "title": "Synthetic preparation instructions", "source": "Synthetic test fixture",
                "source_url": "https://example.invalid/fixture", "license": "Synthetic fixture; not for clinical use",
                "content": "Check the appointment location. Bring the appointment notice.",
                "scopes": [{"branch_id": "a", "department_id": "general"}],
                "effective_from": (now - timedelta(days=1)).isoformat(),
                "effective_until": (now + timedelta(days=30)).isoformat(),
                "change_reason": "Synthetic test revision", "chunk_strategy": "baseline", **changes}

    def create(self, **changes):
        response = self.request("POST", "/api/knowledge/versions", self.payload(**changes), user="nurse")
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def action(self, version, action, user="reviewer"):
        return self.request("POST", f"/api/knowledge/versions/{version['id']}/transition", {"action": action, "reason": "Synthetic test approval"}, user)

    def approve(self, version):
        self.assertEqual(self.action(version, "submit", "nurse").status_code, 200)
        response = self.action(version, "approve")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def search(self, user="reader", **changes):
        return self.request("POST", "/api/retrieval/search", {"question": "preparation", "branch_id": "a", "department_id": "general", "mode": "raw", **changes}, user)

    def test_legacy_migration_is_stable_draft_and_unscoped(self):
        principal = Principal.from_config("admin", self.users["admin"])
        token = current_principal.set(principal)
        document_id = uuid.uuid4()
        try:
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO articles(document_id, content) VALUES (%s,'legacy original')", (document_id,))
            init_tables()
            init_tables()
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT id,status,checksum,legacy_import FROM document_versions WHERE document_id=%s", (document_id,))
                rows = cur.fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][1], "draft")
                self.assertEqual(rows[0][2], hashlib.sha256(b'legacy original').hexdigest())
                self.assertTrue(rows[0][3])
                cur.execute("SELECT count(*) FROM document_version_scopes WHERE version_id=%s", (rows[0][0],))
                self.assertEqual(cur.fetchone()[0], 0)
        finally:
            current_principal.reset(token)
        self.assertEqual(self.search().json()["results"], [])

    def test_review_state_machine_and_revision_history(self):
        v1 = self.create()
        self.assertEqual(v1["status"], "draft")
        self.assertIsNone(v1["approved_at"])
        self.assertEqual(self.action(v1, "approve").status_code, 409)
        self.assertEqual(self.action(v1, "submit", "nurse").status_code, 200)
        self.assertEqual(self.action(v1, "approve", "nurse").status_code, 403)
        self.assertEqual(self.action(v1, "return").json()["status"], "draft")
        approved_v1 = self.approve(v1)
        self.assertEqual(approved_v1["approved_by"], "reviewer")
        v2 = self.create(document_id=v1["document_id"], version_label="v2", content="Revised synthetic instructions")
        self.approve(v2)
        original = self.request("GET", f"/api/knowledge/versions/{v1['id']}").json()
        self.assertEqual(original["status"], "superseded")
        self.assertEqual(original["content"], v1["content"])
        self.assertEqual(v2["document_id"], v1["document_id"])
        self.assertNotEqual(v2["id"], v1["id"])
        self.assertEqual(v2["version_number"], 2)
        events = self.request("GET", f"/api/knowledge/documents/{v1['document_id']}/history").json()["events"]
        self.assertTrue(any(e["action"] == "supersede" and e["version_id"] == v1["id"] for e in events))
        self.assertEqual(self.action(v2, "withdraw").json()["status"], "archived")
        self.assertEqual(self.search().json()["results"], [])

    def test_formal_retrieval_applies_scope_state_validity_and_acl_before_ranking(self):
        a = self.approve(self.create())
        b = self.approve(self.create(scopes=[{"branch_id": "b", "department_id": "general"}]))
        self.approve(self.create(scopes=[{"branch_id": "a", "department_id": "lab"}]))
        self.create(content="Unapproved material must never be retrieved")
        restricted = self.approve(self.create(allowed_users=["nurse", "reviewer"]))
        rows = self.search().json()
        self.assertEqual([r["document_version_id"] for r in rows["results"]], [a["id"]])
        self.assertEqual(rows["settings"]["applied_filters"]["branch_id"], "a")
        self.assertEqual(rows["settings"]["applied_filters"]["strategy"], "exact_over_authorized_subset")
        self.assertEqual(self.search(branch_id="b").status_code, 403)
        self.assertEqual([r["document_version_id"] for r in self.search(user="nurse", branch_id="b").json()["results"]], [b["id"]])
        self.assertNotIn(restricted["id"], [r["document_version_id"] for r in rows["results"]])
        principal = Principal.from_config("admin", self.users["admin"])
        context = current_principal.set(principal)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute("UPDATE document_versions SET effective_until=now()-interval '1 second' WHERE id=%s", (a["id"],))
        finally:
            current_principal.reset(context)
        self.assertEqual(self.search().json()["results"], [])
        self.assertEqual(self.search(user="outsider").json()["results"], [])

    def test_api_parameters_cannot_grant_extra_permissions_or_skip_approval(self):
        payload = self.payload(status="approved", organization_id="foreign")
        self.assertEqual(self.request("POST", "/api/knowledge/versions", payload, "nurse").status_code, 400)
        self.assertEqual(self.request("GET", "/api/documents", user="reader").status_code, 403)
        self.assertEqual(self.request("POST", "/api/retrieval/search", {"question": "test"}, "reader").status_code, 400)
        v1 = self.create()
        self.assertEqual(self.request("GET", f"/api/knowledge/versions/{v1['id']}", user="reader").status_code, 404)
        self.assertEqual(self.request("GET", f"/api/knowledge/versions/{v1['id']}", user="outsider").status_code, 404)
        self.assertEqual(self.action(v1, "submit", "reader").status_code, 403)

    def test_shared_organization_does_not_share_personal_conversations(self):
        from medivector.conversations import save_messages
        principal = Principal.from_config("nurse", self.users["nurse"])
        token = current_principal.set(principal)
        conversation = str(uuid.uuid4())
        try:
            save_messages(conversation, [{"role": "user", "content": "my private synthetic question"}])
        finally:
            current_principal.reset(token)
        self.assertEqual(self.request("GET", "/api/conversations", user="reader").json()["conversations"], [])
        self.assertEqual(self.request("GET", f"/api/conversations/{conversation}", user="reader").json()["messages"], [])
        self.request("DELETE", f"/api/conversations/{conversation}", user="reader")
        self.assertEqual(len(self.request("GET", f"/api/conversations/{conversation}", user="nurse").json()["messages"]), 1)
        token = current_principal.set(Principal.from_config("reader", self.users["reader"]))
        try:
            with self.assertRaisesRegex(ValueError, "another account"):
                save_messages(conversation, [{"role": "user", "content": "attempted overwrite"}])
        finally:
            current_principal.reset(token)

    def test_citation_rechecks_withdrawal_and_redacts_old_history(self):
        from medivector.conversations import save_messages
        version = self.approve(self.create())
        ref = self.search().json()["results"][0]
        citation = self.request("GET", f"/api/knowledge/chunks/{ref['chunk_id']}?branch_id=a&department_id=general", user="reader")
        self.assertEqual(citation.status_code, 200)
        self.assertEqual(citation.json()["document_version_id"], version["id"])
        metadata = ref["chunk_metadata"]
        self.assertEqual(metadata["source_sha256"], version["checksum"])
        self.assertEqual(version["content"][metadata["start"]:metadata["end"]], ref["content"])
        conversation = str(uuid.uuid4())
        token = current_principal.set(Principal.from_config("reader", self.users["reader"]))
        try:
            save_messages(conversation, [{"role": "assistant", "content": "prior cited response",
                                         "references": [{"uuid": ref["chunk_id"], "document_version_id": version["id"], "chunk_metadata": metadata}]}])
        finally:
            current_principal.reset(token)
        self.assertEqual(self.action(version, "withdraw").status_code, 200)
        self.assertEqual(self.request("GET", f"/api/knowledge/chunks/{ref['chunk_id']}?branch_id=a&department_id=general", user="reader").status_code, 404)
        history = self.request("GET", f"/api/conversations/{conversation}", user="reader").json()["messages"]
        self.assertNotEqual(history[0]["content"], "prior cited response")
        self.assertEqual(history[0]["references"], [])

    def test_partial_scope_reviewer_cannot_publish_other_branch(self):
        self.users["limited"] = {"role": "reviewer", "token": "l" * 32, "organization_id": self.org,
                                 "branch_ids": ["a"], "department_ids": ["general"]}
        with patch.dict(os.environ, {"API_USERS": json.dumps(self.users)}):
            version = self.create(scopes=[{"branch_id": "a", "department_id": "general"},
                                          {"branch_id": "b", "department_id": "lab"}])
            self.assertEqual(len(version["scopes"]), 2)
            self.assertEqual(self.action(version, "submit", "nurse").status_code, 200)
            self.assertEqual(self.action(version, "approve", "limited").status_code, 403)
            self.assertEqual(self.action(version, "approve").status_code, 200)

    def test_database_rejects_mismatched_chunk_provenance_and_event_edits(self):
        import psycopg
        version = self.create()
        token = current_principal.set(Principal.from_config("admin", self.users["admin"]))
        try:
            with self.assertRaises(psycopg.IntegrityError):
                with db_connection() as conn, conn.cursor() as cur:
                    cur.execute("INSERT INTO articles(document_id,document_version_id,content) VALUES (%s,%s,'wrong source')", (uuid.uuid4(), version["id"]))
            with self.assertRaises(psycopg.DatabaseError):
                with db_connection() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE knowledge_events SET reason='tampered' WHERE version_id=%s", (version["id"],))
        finally:
            current_principal.reset(token)

    def test_publication_cannot_replace_newer_revision_or_create_future_gap(self):
        older = self.create()
        self.assertEqual(self.action(older, "submit", "nurse").status_code, 200)
        current = self.approve(self.create(document_id=older["document_id"], version_label="v2"))
        self.assertEqual(self.action(older, "approve").status_code, 409)
        future = self.create(document_id=older["document_id"], version_label="v3", effective_from=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
        self.assertEqual(self.action(future, "submit", "nurse").status_code, 200)
        self.assertEqual(self.action(future, "approve").status_code, 409)
        self.assertEqual([r["document_version_id"] for r in self.search().json()["results"]], [current["id"]])

    def test_manifest_is_stable_and_only_contains_current_approved_versions(self):
        draft = self.create()
        path = "/api/knowledge/corpus-manifest?branch_id=a&department_id=general"
        self.assertEqual(self.request("GET", path, user="reader").json()["versions"], [])
        self.approve(draft)
        first = self.request("GET", path, user="reader").json()
        second = self.request("GET", path, user="reader").json()
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(first["versions"][0]["version_id"], draft["id"])
        replacement = self.create(document_id=draft["document_id"], version_label="v2")
        self.approve(replacement)
        changed = self.request("GET", path, user="reader").json()
        self.assertNotEqual(first["manifest_sha256"], changed["manifest_sha256"])
        self.assertEqual([v["version_id"] for v in changed["versions"]], [replacement["id"]])

    def create_without_key(self, **changes):
        with patch("medivector.knowledge.require_openai_api_key", side_effect=RuntimeError("missing key")), patch("medivector.knowledge.embed_texts") as embed:
            version = self.create(**changes)
            embed.assert_not_called()
        self.assertEqual(version["index_status"], "pending")
        self.assertEqual(version["indexed_chunk_count"], 0)
        return version

    def test_no_key_preserves_source_workflow_without_fake_vectors(self):
        version = self.create_without_key()
        approved = self.approve(version)
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["index_status"], "pending")
        self.assertEqual(self.search().json()["results"], [])
        manifest = self.request("GET", "/api/knowledge/corpus-manifest?branch_id=a&department_id=general", user="reader").json()
        self.assertEqual(manifest["versions"], [])
        token = current_principal.set(Principal.from_config("admin", self.users["admin"]))
        try:
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*),count(embedding) FROM articles WHERE document_version_id=%s", (version["id"],))
                total, indexed = cur.fetchone()
                self.assertGreater(total, 0)
                self.assertEqual(indexed, 0)
        finally:
            current_principal.reset(token)

    def test_pending_source_can_be_indexed_once_and_becomes_searchable(self):
        version = self.approve(self.create_without_key())
        result = self.request("POST", f"/api/knowledge/versions/{version['id']}/index", {"reason": "Test deferred indexing"}, "nurse")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["index_status"], "ready")
        self.assertEqual(result.json()["id"], version["id"])
        self.assertEqual(result.json()["checksum"], version["checksum"])
        self.assertEqual([r["document_version_id"] for r in self.search().json()["results"]], [version["id"]])
        with patch("medivector.knowledge.embed_texts") as embed:
            repeat = self.request("POST", f"/api/knowledge/versions/{version['id']}/index", {"reason": "Attempted overwrite"})
            self.assertEqual(repeat.status_code, 409)
            embed.assert_not_called()
        events = self.request("GET", f"/api/knowledge/documents/{version['document_id']}/history").json()["events"]
        self.assertEqual([e["actor"] for e in events if e["action"] == "index"], ["nurse"])

    def test_indexing_enforces_role_and_org_and_withdrawal(self):
        version = self.approve(self.create_without_key())
        path = f"/api/knowledge/versions/{version['id']}/index"
        with patch("medivector.knowledge.embed_texts") as embed:
            self.assertEqual(self.request("POST", path, {"reason": "unauthorized"}, "reader").status_code, 403)
            self.assertEqual(self.request("POST", path, {"reason": "wrong organization"}, "outsider").status_code, 404)
            self.assertEqual(self.action(version, "withdraw").status_code, 200)
            self.assertEqual(self.request("POST", path, {"reason": "withdrawn source"}).status_code, 409)
            embed.assert_not_called()

    def test_failed_indexing_rolls_back_without_changing_source(self):
        version = self.approve(self.create_without_key())
        with patch("medivector.knowledge.embed_texts", return_value=[]):
            response = self.request("POST", f"/api/knowledge/versions/{version['id']}/index", {"reason": "Bad embedding count"})
        self.assertEqual(response.status_code, 400)
        saved = self.request("GET", f"/api/knowledge/versions/{version['id']}").json()
        self.assertEqual(saved["index_status"], "pending")
        self.assertEqual(saved["checksum"], version["checksum"])
        self.assertEqual(saved["status"], "approved")
        self.assertEqual(self.search().json()["results"], [])

    def test_no_approved_evidence_does_not_call_answer_model(self):
        self.create()
        with patch("medivector.qa.require_openai_api_key", return_value="fake"), patch("medivector.qa.get_retrieval_query") as rewrite, patch("medivector.qa.chat_with_gpt") as generate, patch("medivector.qa.assess_question_risk") as risk:
            from medivector.models import RetrievalQuery
            rewrite.return_value = RetrievalQuery("preparation", [], False)
            response = self.request("POST", "/api/ask", {"conversation_id": str(uuid.uuid4()), "question": "preparation", "branch_id": "a", "department_id": "general"}, "reader")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("無法確認院所規範", response.json()["answer"])
            self.assertEqual(response.json()["references"], [])
            generate.assert_not_called()
            risk.assert_not_called()
        response = self.request("POST", "/api/ask", {"question": "test", "rag_enabled": False, "branch_id": "a", "department_id": "general"}, "reader")
        self.assertEqual(response.status_code, 400)

    def upload_pdf(self, data, user='nurse', **changes):
        payload = self.payload(**changes)
        payload.pop('content', None)
        return self.client.post('/api/knowledge/versions/pdf',
                                data={'metadata': json.dumps(payload)}, files={'file': ('demo.pdf', data, 'application/pdf')},
                                headers={'Authorization': 'Bearer ' + self.users[user]['token']})

    def test_ten_pdf_queries_trace_to_exact_version_offsets_pages_and_original(self):
        from pdf_fixture import pdf_bytes
        from medivector.chunking import page_text, chunk_manifest
        from medivector.models import RetrievalQuery
        data = pdf_bytes([[f'Synthetic instruction {i}: verify appointment location and notice.' for i in range(6)],
                          [], [f'Synthetic instruction {i}: bring the appointment document.' for i in range(6, 12)]])
        text, pages = page_text(data)
        manifest = chunk_manifest(text, document_id='test', version='test', strategy='token', max_tokens=32, overlap=0, pages=pages)
        vectors = [[float(i == n) for i in range(1536)] for n in range(len(manifest['chunks']))]
        with patch('medivector.knowledge.embed_texts', return_value=vectors):
            response = self.upload_pdf(data, chunk_strategy='token', max_tokens=32, overlap_tokens=0)
        self.assertEqual(response.status_code, 201, response.text)
        version = self.approve(response.json())
        self.assertEqual(version['pages'][1]['status'], 'no_text')
        self.assertEqual(version['attachment']['sha256'], hashlib.sha256(data).hexdigest())
        self.assertGreaterEqual(len(manifest['chunks']), 10)
        for i in [n * (len(manifest["chunks"]) - 1) // 9 for n in range(10)]:
            with self.subTest(question=i), patch('medivector.qa.require_openai_api_key', return_value='fake'), patch('medivector.retrieval.embed_texts', return_value=[vectors[i]]), patch('medivector.qa.get_retrieval_query', return_value=RetrievalQuery(f'Find instruction {i}', [], False)), patch('medivector.qa.chat_with_gpt', return_value='Synthetic answer [1]'):
                answer = self.request('POST', '/api/ask', {'conversation_id': str(uuid.uuid4()), 'question': f'Find instruction {i}', 'branch_id': 'a', 'department_id': 'general'}, 'reader')
            self.assertEqual(answer.status_code, 200, answer.text)
            ref = answer.json()['references'][0]
            self.assertEqual(ref['document_version_id'], version['id'])
            path = f"/api/knowledge/chunks/{ref['uuid']}?branch_id=a&department_id=general"
            source = self.request('GET', path, user='reader')
            self.assertEqual(source.status_code, 200, source.text)
            meta = source.json()['chunk_metadata']
            self.assertEqual(source.json()['content'], text[meta['start']:meta['end']])
            self.assertEqual(meta['pages'], manifest['chunks'][i]['pages'])
            self.assertNotIn(2, meta['pages'])
            original = self.request('GET', f"/api/knowledge/versions/{version['id']}/attachment?chunk_id={ref['uuid']}&branch_id=a&department_id=general", user='reader')
            self.assertEqual(original.content, data)
            self.assertEqual(original.headers['x-source-sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(original.headers['cache-control'], 'no-store')
        # Original bytes cannot be overwritten, even by an application SQL update.
        token = current_principal.set(Principal.from_config('admin', self.users['admin']))
        try:
            with self.assertRaises(Exception):
                with db_connection() as conn, conn.cursor() as cur:
                    cur.execute('UPDATE source_attachments SET data=%s WHERE version_id=%s', (b'changed', version['id']))
        finally:
            current_principal.reset(token)
        self.assertEqual(self.action(version, 'withdraw').status_code, 200)
        self.assertEqual(self.request('GET', path, user='reader').status_code, 404)
        self.assertEqual(self.request('GET', f"/api/knowledge/versions/{version['id']}/attachment", user='reader').status_code, 404)

    def test_pdf_rejects_invalid_empty_encrypted_and_foreign_access(self):
        from pdf_fixture import pdf_bytes
        from pypdf import PdfReader, PdfWriter
        from io import BytesIO
        for data in (b'not a pdf', b'%PDF-broken', pdf_bytes([[]])):
            self.assertEqual(self.upload_pdf(data).status_code, 400)
        writer = PdfWriter(); writer.append(PdfReader(BytesIO(pdf_bytes([['Synthetic']])))); writer.encrypt('secret')
        output = BytesIO(); writer.write(output)
        self.assertEqual(self.upload_pdf(output.getvalue()).status_code, 400)
        self.assertEqual(self.upload_pdf(pdf_bytes([['Synthetic']]), user='reader').status_code, 403)
        version = self.upload_pdf(pdf_bytes([['Synthetic source']])).json()
        path = f"/api/knowledge/versions/{version['id']}/attachment"
        self.assertEqual(self.request('GET', path, user='outsider').status_code, 404)
        self.assertEqual(self.request('GET', path, user='reader').status_code, 404)
        self.approve(version)
        self.assertEqual(self.request('GET', path, user='reader').status_code, 200)
        foreign = self.create(scopes=[{'branch_id': 'b', 'department_id': 'general'}])
        self.assertEqual(self.request('GET', f"/api/knowledge/versions/{foreign['id']}/attachment", user='reader').status_code, 404)
        self.assertEqual(self.request('GET', path + '?chunk_id=' + str(uuid.uuid4()) + '&branch_id=a&department_id=general', user='reader').status_code, 404)

    def generate_education(self, version, user='nurse', **changes):
        with patch('medivector.education.require_openai_api_key', return_value='fake'), patch('medivector.education.openai_post', return_value={'choices': [{'message': {'content': '待人工審核草稿\n請核對預約地點並攜帶通知單。[來源1]'}}]}):
            return self.request('POST', '/api/education/drafts', {'branch_id': 'a', 'department_id': 'general', 'topic': '合成檢查前衛教', 'version_ids': [version['id']], **changes}, user)

    def education_action(self, draft, action, user='reviewer', **changes):
        return self.request('POST', f"/api/education/drafts/{draft['id']}/transition", {'expected_revision': draft['revision_number'], 'action': action, 'reason': '合成流程測試，非臨床核准', **changes}, user)

    def test_generated_education_edit_return_publish_withdraw_e2e(self):
        version = self.approve(self.create())
        response = self.generate_education(version)
        self.assertEqual(response.status_code, 201, response.text)
        draft = response.json()
        self.assertEqual(draft['status'], 'draft')
        self.assertEqual(draft['sources'][0]['version_id'], version['id'])
        path = f"/api/education/drafts/{draft['id']}"
        self.assertEqual(self.request('GET', path, user='reader').status_code, 404)
        self.assertEqual(self.request('GET', '/api/education/drafts', user='reader').json()['drafts'], [])
        edited = self.request('POST', path + '/revisions', {'expected_revision': 1, 'content': draft['content'] + '\n流程示範；請由專業人員核對。[來源1]', 'reason': '補上示範限制'}, 'nurse')
        self.assertEqual(edited.status_code, 200, edited.text)
        draft = edited.json()
        self.assertEqual(draft['revision_number'], 2)
        self.assertIn('+流程示範', draft['revisions'][1]['diff'])
        self.assertEqual(draft['revisions'][0]['sources'], draft['revisions'][1]['sources'])
        self.assertEqual(draft['revisions'][0]['generation_snapshot'], draft['revisions'][1]['generation_snapshot'])
        self.assertEqual(draft['revisions'][0]['generation_snapshot']['retriever']['mode'], 'explicit_selected_sources')
        self.assertEqual(self.education_action(draft, 'approve', user='nurse').status_code, 403)
        self.assertEqual(self.education_action(draft, 'approve').status_code, 409)
        draft = self.education_action(draft, 'submit', user='nurse').json()
        self.assertEqual(self.request('POST', path + '/revisions', {'expected_revision': 2, 'content': 'unsafe edit [來源1]', 'reason': 'test'}, 'nurse').status_code, 409)
        draft = self.education_action(draft, 'return').json()
        self.assertEqual(draft['status'], 'draft')
        draft = self.education_action(draft, 'submit', user='nurse').json()
        draft = self.education_action(draft, 'approve').json()
        self.assertEqual(draft['status'], 'published')
        public = self.request('GET', path, user='reader')
        self.assertEqual(public.status_code, 200, public.text)
        self.assertNotIn('revisions', public.json())
        self.assertNotIn('content', public.json()['sources'][0])
        self.assertEqual(self.education_action(draft, 'withdraw', user='nurse').status_code, 403)
        archived = self.education_action(draft, 'withdraw').json()
        self.assertEqual(archived['status'], 'archived')
        self.assertEqual([e['action'] for e in archived['events']], ['generate', 'edit', 'submit', 'return', 'submit', 'approve', 'withdraw'])
        self.assertEqual(self.request('GET', path, user='reader').status_code, 404)
        self.assertEqual(self.request('GET', path, user='outsider').status_code, 404)
        token = current_principal.set(Principal.from_config('admin', self.users['admin']))
        try:
            with self.assertRaises(Exception):
                with db_connection() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE education_revisions SET content='tampered' WHERE draft_id=%s", (draft['id'],))
        finally:
            current_principal.reset(token)

    def test_education_rejects_stale_edits_bad_citations_and_invalid_sources(self):
        source = self.create()
        self.assertEqual(self.generate_education(source).status_code, 409)
        source = self.approve(source)
        self.assertEqual(self.generate_education(source, user='reader').status_code, 403)
        self.assertEqual(self.generate_education(source, user='outsider').status_code, 409)
        self.assertEqual(self.generate_education(source, branch_id='b').status_code, 409)
        draft = self.generate_education(source).json()
        path = f"/api/education/drafts/{draft['id']}/revisions"
        for content, expected in [('missing source', 1), ('wrong [來源2]', 1), ('valid [來源1]', 99)]:
            response = self.request('POST', path, {'expected_revision': expected, 'content': content, 'reason': 'test'}, 'nurse')
            self.assertEqual(response.status_code, 409, response.text)
        self.action(source, 'withdraw')
        self.assertEqual(self.education_action(draft, 'submit', user='nurse').status_code, 409)

    def test_published_education_becomes_unavailable_when_source_withdrawn(self):
        source = self.approve(self.create())
        draft = self.generate_education(source).json()
        draft = self.education_action(draft, 'submit', user='nurse').json()
        draft = self.education_action(draft, 'approve').json()
        self.action(source, 'withdraw')
        self.assertEqual(self.request('GET', '/api/education/drafts', user='reader').json()['drafts'], [])
        self.assertEqual(self.request('GET', f"/api/education/drafts/{draft['id']}", user='reader').status_code, 409)
        self.assertEqual(self.request('GET', f"/api/education/drafts/{draft['id']}", user='reviewer').status_code, 200)

    def test_generation_rechecks_sources_after_model_call_and_never_auto_publishes(self):
        source = self.approve(self.create())
        def withdraw_during_generation(*args, **kwargs):
            self.assertEqual(self.action(source, 'withdraw').status_code, 200)
            return {'choices': [{'message': {'content': '待審稿 [來源1]'}}]}
        with patch('medivector.education.require_openai_api_key', return_value='fake'), patch('medivector.education.openai_post', side_effect=withdraw_during_generation):
            response = self.request('POST', '/api/education/drafts', {'branch_id': 'a', 'department_id': 'general', 'topic': 'test', 'version_ids': [source['id']]}, 'nurse')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.request('GET', '/api/education/drafts').json()['drafts'], [])

    def test_feedback_links_only_owned_query_and_accessible_source(self):
        from medivector.models import RetrievalQuery
        source = self.approve(self.create())
        trace = str(uuid.uuid4())
        with patch('medivector.qa.require_openai_api_key', return_value='fake'), patch('medivector.qa.get_retrieval_query', return_value=RetrievalQuery('preparation', [], False)), patch('medivector.qa.chat_with_gpt', return_value='Synthetic answer [1]'):
            answer = self.request('POST', '/api/ask', {'conversation_id': trace, 'question': 'preparation', 'branch_id': 'a', 'department_id': 'general'}, 'reader')
        self.assertEqual(answer.status_code, 200, answer.text)
        payload = {'version_id': source['id'], 'conversation_id': trace, 'category': 'inappropriate_answer', 'reason': '合成回報，不含個人資料'}
        self.assertEqual(self.request('POST', '/api/education/feedback', payload, 'reader').status_code, 201)
        self.assertEqual(self.request('POST', '/api/education/feedback', payload, 'nurse').status_code, 404)
        self.assertEqual(self.request('POST', '/api/education/feedback', payload, 'outsider').status_code, 404)
        self.assertEqual(self.request('GET', '/api/education/feedback', user='reader').status_code, 403)
        reports = self.request('GET', '/api/education/feedback', user='reviewer').json()['feedback']
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['conversation_id'], trace)
        self.assertIsNotNone(reports[0]['query_trace_id'])
        self.action(source, 'withdraw')
        self.assertEqual(self.request('POST', '/api/education/feedback', {**payload, 'category': 'outdated_source'}, 'reader').status_code, 201)

    def test_generated_source_snapshots_do_not_bypass_named_user_acl(self):
        source = self.approve(self.create(allowed_users=['nurse', 'reviewer']))
        draft = self.generate_education(source).json()
        # Admin's role alone does not override explicit source ACLs.
        self.assertEqual(self.request('GET', f"/api/education/drafts/{draft['id']}", user='admin').status_code, 404)
        self.assertEqual(self.request('GET', '/api/education/drafts', user='admin').json()['drafts'], [])
        self.assertEqual(self.education_action(draft, 'submit', user='admin').status_code, 404)

    def test_query_trace_records_config_ids_and_hashes_without_raw_question_or_answer(self):
        from medivector.models import RetrievalQuery
        source = self.approve(self.create())
        question = 'SYNTHETIC_PRIVATE_QUESTION_123'
        answer_text = 'SYNTHETIC_PRIVATE_ANSWER_456 [1]'
        trace = str(uuid.uuid4())
        with patch('medivector.qa.require_openai_api_key', return_value='fake'), patch('medivector.qa.get_retrieval_query', return_value=RetrievalQuery('preparation', [], False)), patch('medivector.qa.chat_with_gpt', return_value=answer_text):
            response = self.request('POST', '/api/ask', {'conversation_id': trace, 'question': question, 'branch_id': 'a', 'department_id': 'general'}, 'reader')
        self.assertEqual(response.status_code, 200, response.text)
        trace_id = response.json()['query_trace_id']
        path = '/api/knowledge/query-traces/' + trace_id
        audit = self.request('GET', path, user='reader')
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertNotIn(question, audit.text)
        self.assertNotIn(answer_text, audit.text)
        self.assertNotIn(self.users['reader']['token'], audit.text)
        data = audit.json()
        self.assertGreaterEqual(data['elapsed_ms'], 0)
        self.assertEqual(data['references_metadata'][0]['document_version_id'], source['id'])
        self.assertIn(source['id'], data['snapshot']['corpus'])
        self.assertEqual(len(data['snapshot']['source_sha256']), 64)
        self.assertIn('chat.py', data['snapshot']['prompt_versions'])
        self.assertEqual(self.request('GET', path, user='nurse').status_code, 404)
        self.assertEqual(self.request('GET', path, user='outsider').status_code, 404)
        self.assertEqual(self.request('GET', '/api/knowledge/query-traces?conversation_id=' + trace, user='nurse').json()['traces'], [])
        self.assertEqual(self.request('GET', '/api/knowledge/query-traces?conversation_id=' + trace, user='reader').json()['traces'][0]['id'], trace_id)
        self.assertEqual(self.request('DELETE', '/api/conversations/' + trace, user='reader').status_code, 200)
        self.assertEqual(self.request('GET', path, user='reader').status_code, 200)
        token = current_principal.set(Principal.from_config('admin', self.users['admin']))
        try:
            with self.assertRaises(Exception):
                with db_connection() as conn, conn.cursor() as cur:
                    cur.execute('DELETE FROM query_traces WHERE id=%s', (trace_id,))
        finally:
            current_principal.reset(token)

    def test_publication_records_human_review_and_blocks_identity_quality_failure(self):
        source = self.approve(self.create())
        draft = self.generate_education(source).json()
        draft = self.education_action(draft, 'submit', user='nurse').json()
        published = self.education_action(draft, 'approve')
        self.assertEqual(published.status_code, 200, published.text)
        path = f"/api/education/drafts/{draft['id']}/release-reviews"
        reviews = self.request('GET', path, user='reviewer').json()['reviews']
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]['report']['status'], 'Review Required')
        self.assertEqual(reviews[0]['report']['human_approval']['actor'], 'reviewer')
        self.assertEqual(reviews[0]['revision_number'], 1)
        self.assertEqual(self.request('GET', path, user='reader').status_code, 403)
        # Remove a chunk only in the isolated test schema to simulate a polluted source index.
        second = self.generate_education(source).json()
        second = self.education_action(second, 'submit', user='nurse').json()
        token = current_principal.set(Principal.from_config('admin', self.users['admin']))
        try:
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute('DELETE FROM articles WHERE document_version_id=%s', (source['id'],))
            with self.assertRaises(Exception):
                with db_connection() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE release_reviews SET reason='changed' WHERE draft_id=%s", (draft['id'],))
        finally:
            current_principal.reset(token)
        denied = self.education_action(second, 'approve')
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertIn('quality', denied.text)
        self.assertEqual(self.request('GET', f"/api/education/drafts/{second['id']}", user='nurse').json()['status'], 'in_review')

    def test_audit_write_failure_rolls_back_conversation_with_answer(self):
        from medivector.models import RetrievalQuery
        from medivector.knowledge import KnowledgeError
        self.approve(self.create())
        conversation_id = str(uuid.uuid4())
        with patch('medivector.qa.require_openai_api_key', return_value='fake'), patch('medivector.qa.get_retrieval_query', return_value=RetrievalQuery('preparation', [], False)), patch('medivector.qa.chat_with_gpt', return_value='Synthetic [1]'), patch('medivector.quality_audit.record_query', side_effect=KnowledgeError('Synthetic audit failure', 503)):
            response = self.request('POST', '/api/ask', {'conversation_id': conversation_id, 'question': 'preparation', 'branch_id': 'a', 'department_id': 'general'}, 'reader')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.request('GET', '/api/conversations/' + conversation_id, user='reader').json()['messages'], [])
        self.assertEqual(self.request('GET', '/api/knowledge/query-traces?conversation_id=' + conversation_id, user='reader').json()['traces'], [])
