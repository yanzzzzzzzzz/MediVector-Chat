import json
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from medivector.api_auth import Principal, configured_users, current_principal
from medivector.server import app


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.users = {"alice": {"role": "admin", "token": "a" * 32}, "bob": {"role": "user", "token": "b" * 32}}
        self.env = patch.dict(os.environ, {"API_USERS": json.dumps(self.users)})
        self.env.start()
        self.client = TestClient(app, client=("192.0.2.10", 1))

    def tearDown(self):
        self.env.stop()

    def test_every_sensitive_route_requires_auth(self):
        for method, path in (("GET", "/api/documents"), ("DELETE", "/api/documents/123"),
                             ("GET", "/api/conversations"), ("POST", "/api/ask"),
                             ("POST", "/api/retrieval/search")):
            self.assertEqual(self.client.request(method, path).status_code, 401)

    def test_role_request_size_and_rate_limit(self):
        bob = {"Authorization": "Bearer " + "b" * 32}
        self.assertEqual(self.client.post("/api/documents", headers=bob, json={}).status_code, 403)
        with patch.dict(os.environ, {"MAX_REQUEST_BYTES": "5"}):
            self.assertEqual(self.client.post("/api/ask", headers=bob, content="123456").status_code, 413)
        with patch.dict(os.environ, {"API_RATE_LIMIT_PER_MINUTE": "1"}):
            self.assertEqual(self.client.get("/api/conversations", headers=bob).status_code, 429)

    def test_non_ascii_authorization_is_rejected(self):
        response = self.client.get("/api/documents", headers={b"Authorization": b"Bearer \xff"})
        self.assertEqual(response.status_code, 401)

    def test_namespaces_are_stable_and_distinct(self):
        self.assertNotEqual(Principal("alice", "admin").schema, Principal("bob", "user").schema)
        self.assertEqual(Principal("alice", "admin").schema, Principal("alice", "user").schema)
        with patch.dict(os.environ, {"API_USERS": '{"bad":{"token":"short","role":"admin"}}'}):
            with self.assertRaises(ValueError):
                configured_users()


@unittest.skipUnless(os.getenv("RUN_DB_TESTS") == "1", "requires isolated test PostgreSQL")
class DatabaseIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Each integration test can run independently on a completely fresh database.
        from medivector.db import init_db
        with patch.dict(os.environ, {"API_USERS": "{}"}):
            init_db()

    def test_versioned_manifest_import_refuses_overwrite(self):
        from psycopg import sql
        from evaluation.chunking import chunk_manifest
        from evaluation.index_manifest import index_manifests
        from medivector.db import db_connection
        from medivector.retrieval import retrieve_candidates
        experiment = uuid.uuid4().hex
        principal = Principal("experiment:" + experiment, "admin")
        manifest = chunk_manifest("alpha beta gamma", document_id="stable-doc", version="v1")
        vector = "[1," + ",".join("0" for _ in range(1535)) + "]"
        try:
            with patch("evaluation.index_manifest.require_openai_api_key", return_value="fake"), patch("evaluation.index_manifest.embed_texts", return_value=[vector]) as embed:
                self.assertEqual(index_manifests([manifest], experiment)["chunks"], 1)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    index_manifests([manifest], experiment)
                self.assertEqual(embed.call_count, 1)
            token = current_principal.set(principal)
            try:
                with patch("medivector.retrieval.embed_texts", return_value=[vector]):
                    refs = retrieve_candidates("fake", "alpha")
                self.assertEqual(refs[0].chunk_metadata["source_sha256"], manifest["source_sha256"])
                self.assertEqual(refs[0].chunk_metadata["start"], 0)
                self.assertEqual(refs[0].chunk_metadata["end"], 16)
            finally:
                current_principal.reset(token)
        finally:
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(principal.schema)))

    def test_documents_conversations_and_retrieval_are_isolated(self):
        from psycopg import sql
        from medivector.db import db_connection, init_db
        suffix = uuid.uuid4().hex
        names = ["alice-" + suffix, "bob-" + suffix]
        users = {name: {"role": "admin", "token": token * 32} for name, token in zip(names, ("a", "b"))}
        with patch.dict(os.environ, {"API_USERS": json.dumps(users)}):
            init_db()
            principals = [Principal(name, "admin") for name in names]
            document_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
            conversation_id = str(uuid.uuid4())
            vector = "[1," + ",".join("0" for _ in range(1535)) + "]"
            try:
                for principal, document_id in zip(principals, document_ids):
                    context_token = current_principal.set(principal)
                    try:
                        with db_connection() as conn, conn.cursor() as cur:
                            cur.execute("INSERT INTO articles (document_id, title, content, embedding) VALUES (%s, %s, 'test', %s::public.vector)", (document_id, principal.name, vector))
                            cur.execute("INSERT INTO conversations (id) VALUES (%s)", (conversation_id,))
                            cur.execute("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)", (conversation_id, principal.name))
                    finally:
                        current_principal.reset(context_token)
                client = TestClient(app, client=("192.0.2.1", 1))
                for i, name in enumerate(names):
                    headers = {"Authorization": "Bearer " + users[name]["token"]}
                    docs = client.get("/api/documents", headers=headers)
                    self.assertEqual(docs.status_code, 200, docs.text)
                    self.assertEqual([d["document_id"] for d in docs.json()["documents"]], [document_ids[i]])
                    messages = client.get(f"/api/conversations/{conversation_id}", headers=headers)
                    self.assertEqual(messages.json()["messages"][0]["content"], name)
                    deleted = client.delete(f"/api/documents/{document_ids[1-i]}", headers=headers)
                    self.assertFalse(deleted.json()["deleted"])
                    with patch("medivector.retrieval_api.require_openai_api_key", return_value="fake"), patch("medivector.retrieval.embed_texts", return_value=[vector]):
                        result = client.post("/api/retrieval/search", headers=headers, json={"question": "test", "mode": "raw"})
                    self.assertEqual(result.status_code, 200, result.text)
                    self.assertEqual([r["document_id"] for r in result.json()["results"]], [document_ids[i]])
                bob_headers = {"Authorization": "Bearer " + users[names[1]]["token"]}
                alice_headers = {"Authorization": "Bearer " + users[names[0]]["token"]}
                self.assertEqual(client.delete(f"/api/conversations/{conversation_id}", headers=bob_headers).status_code, 200)
                self.assertEqual(client.get(f"/api/conversations/{conversation_id}", headers=bob_headers).json()["messages"], [])
                self.assertEqual(client.get(f"/api/conversations/{conversation_id}", headers=alice_headers).json()["messages"][0]["content"], names[0])
            finally:
                for principal in principals:
                    with db_connection() as conn, conn.cursor() as cur:
                        cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(principal.schema)))
