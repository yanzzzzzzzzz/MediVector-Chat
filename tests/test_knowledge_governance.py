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
