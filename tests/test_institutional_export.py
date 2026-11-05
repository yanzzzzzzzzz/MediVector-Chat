"""Exercise the CLI protocol with a synthetic fixture, without any external API calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from evaluation.retrieval_baseline import main


class InstitutionalExportTests(unittest.TestCase):
    def test_scoped_export_freezes_manifest_and_replays_expansion(self):
        requests = []
        def handle(request):
            if request.method == "GET":
                self.assertEqual(request.url.params['branch_id'], 'a')
                return httpx.Response(200, json={"manifest_sha256": "frozen"})
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload['branch_id'], 'a')
            self.assertEqual(payload['department_id'], 'lab')
            if payload['mode'] == 'filtered':
                self.assertFalse(payload['query_expansion'])
                self.assertEqual(payload['question'], 'standalone')
                self.assertEqual(payload['retrieval_terms'], ['term'])
            return httpx.Response(200, json={"results": [{"document_id": "doc"}], "standalone_query": "standalone", "terms": ["term"], "settings": {"embedding_model": "fake-model"}, "elapsed_ms": 1})
        dataset = {"dataset_version": "SYNTHETIC-TEST-ONLY", "corpus_version": "frozen", "index_version": "fake-index", "embedding_model": "fake-model", "retrieval_context": {"branch_id": "a", "department_id": "lab"}, "cases": [
            {"id": f"q{i:02}", "query": "synthetic", "reviewed_by": "TEST-FIXTURE-NOT-A-REAL-REVIEW", "reviewed_at": "2026-11-04T00:00:00Z", "answerable": True, "relevant_document_ids": ["doc"]} for i in range(30)]}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'fixture.json', Path(directory)/'report.json'
            source.write_text(json.dumps(dataset))
            client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handle))
            with patch("sys.argv", ["export", str(source), str(output)]), patch("evaluation.retrieval_baseline.httpx.Client", return_value=client):
                main()
            report = json.loads(output.read_text())
            self.assertEqual(len(requests), 120)
            self.assertEqual(report['corpus_manifest']['manifest_sha256'], 'frozen')
            self.assertTrue(output.with_suffix('.md').exists())
            self.assertTrue(all(exp['summary']['3']['recall'] == 1 for exp in report['experiments']))
            rejected = Path(directory)/'rejected.json'
            changed = httpx.Client(base_url="http://test", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"manifest_sha256": "changed"})))
            with patch("sys.argv", ["export", str(source), str(rejected)]), patch("evaluation.retrieval_baseline.httpx.Client", return_value=changed):
                with self.assertRaisesRegex(ValueError, "manifest changed"):
                    main()
            self.assertFalse(rejected.exists())
