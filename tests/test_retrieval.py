import unittest
from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient

from medivector.retrieval import filter_references, search_references
from medivector.server import app
from test_pure_logic import make_reference


class RetrievalTests(unittest.TestCase):
    def test_threshold_sort_dedup_and_immutable_ranks(self):
        a = make_reference(1, .25)
        duplicate = replace(a, uuid="duplicate", index=2)
        boundary = make_reference(3, .375)
        outside = make_reference(4, .376)
        refs = filter_references([outside, boundary, duplicate, a], distance_margin=.125)
        self.assertEqual([r.uuid for r in refs], [a.uuid, boundary.uuid])
        self.assertEqual([r.index for r in refs], [1, 2])
        self.assertEqual(boundary.index, 3)
        self.assertEqual(len(filter_references([a, duplicate], dedup=False)), 2)
        self.assertEqual(filter_references([]), [])
        self.assertEqual(filter_references([outside], max_distance=.3), [])

    @patch("medivector.retrieval.retrieve_candidates")
    def test_top_k_raises_candidate_limit(self, retrieve):
        retrieve.return_value = [make_reference(i, .1) for i in range(1, 16)]
        for k in (3, 5, 10):
            self.assertEqual(len(search_references("key", "query", top_k=k, candidate_limit=1)), k)
            self.assertEqual(retrieve.call_args.kwargs["candidate_limit"], k)

    @patch("medivector.retrieval_api.require_openai_api_key", return_value="fake")
    @patch("medivector.retrieval_api.retrieve_candidates")
    @patch("medivector.retrieval_api.get_retrieval_query")
    @patch("medivector.conversations.save_messages")
    @patch("medivector.chat.chat_with_gpt")
    def test_api_raw_filtered_empty_validation_and_no_chat(self, chat, save, rewrite, retrieve, key):
        client = TestClient(app, client=("127.0.0.1", 1234))
        retrieve.return_value = [make_reference(1, .1), make_reference(2, .9)]
        with patch.dict("os.environ", {"RETRIEVAL_API_TOKEN": ""}):
            response = client.post("/api/retrieval/search", json={"question": "test", "mode": "raw"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(len(data["results"]), 2)
            self.assertEqual(data["results"][1]["raw_rank"], 2)
            self.assertEqual(data["standalone_query"], "test")
            self.assertEqual(data["terms"], [])
            self.assertIn("embedding_model", data["settings"])
            response = client.post("/api/retrieval/search", json={"question": "test"})
            self.assertEqual(len(response.json()["results"]), 1)
            retrieve.return_value = []
            self.assertEqual(client.post("/api/retrieval/search", json={"question": "test"}).json()["results"], [])
            for invalid in ({"question": " "}, {"question": "x", "top_k": 0}, {"question": "x", "mode": "bad"}):
                self.assertEqual(client.post("/api/retrieval/search", json=invalid).status_code, 400)
        rewrite.assert_not_called()
        chat.assert_not_called()
        save.assert_not_called()

    def test_api_remote_and_token_access(self):
        client = TestClient(app, client=("192.0.2.1", 1234))
        with patch.dict("os.environ", {"RETRIEVAL_API_TOKEN": ""}):
            self.assertEqual(client.post("/api/retrieval/search", json={"question": "test"}, headers={"X-Forwarded-For": "127.0.0.1"}).status_code, 403)
        with patch.dict("os.environ", {"RETRIEVAL_API_TOKEN": "secret"}), patch("medivector.server.retrieval_search") as search:
            self.assertEqual(client.post("/api/retrieval/search", json={"question": "test"}).status_code, 401)
            self.assertEqual(client.post("/api/retrieval/search", json={"question": "test"}, headers={b"Authorization": b"Bearer \xff"}).status_code, 401)
            search.return_value = {"results": [], "standalone_query": "test", "terms": [], "query_text": "test", "elapsed_ms": 0, "settings": {}}
            self.assertEqual(client.post("/api/retrieval/search", json={"question": "test"}, headers={"Authorization": "Bearer secret"}).status_code, 200)
