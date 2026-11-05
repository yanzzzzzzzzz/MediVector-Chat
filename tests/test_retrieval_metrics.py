import unittest
from evaluation.retrieval_baseline import metrics, validate_dataset


class RetrievalMetricTests(unittest.TestCase):
    def test_multiple_docs_duplicate_chunks_and_ranks(self):
        case = {"answerable": True, "relevant_document_ids": ["a", "b"]}
        rows = [{"document_id": d} for d in ("x", "a", "a", "b")]
        score = metrics(case, rows, 3)
        self.assertEqual(score['recall'], .5)
        self.assertEqual(score['mrr'], .5)
        self.assertEqual(score['hit'], 1)
        self.assertEqual(metrics(case, rows, 10)['recall'], 1)
        self.assertEqual(metrics(case, [], 3)['recall'], 0)

    def test_no_answer_and_evidence_interval_union(self):
        self.assertEqual(metrics({"answerable": False, "relevant_document_ids": []}, [], 3), {"answerable": False, "returned_any": False})
        case = {"answerable": True, "relevant_document_ids": ["a"], "evidence_spans": [{"document_id": "a", "source_sha256": "hash", "start": 3, "end": 12}]}
        rows = [{"document_id": "a", "chunk_metadata": {"source_sha256": "hash", "start": start, "end": end}} for start, end in ((0, 8), (6, 15))]
        self.assertEqual(metrics(case, rows, 3)['evidence_recall'], 1)
        self.assertEqual(metrics(case, rows[:1], 3)['evidence_recall'], 0)
        rows[0]['chunk_metadata']['source_sha256'] = 'wrong-version'
        self.assertEqual(metrics(case, rows, 3)['evidence_recall'], 0)

    def test_unreviewed_dataset_rejected(self):
        with self.assertRaises(ValueError):
            validate_dataset({"cases": []})

    def test_candidate_packet_has_thirty_stable_unreviewed_cases_and_is_rejected(self):
        import json
        from pathlib import Path
        packet = json.loads((Path(__file__).parents[1] / 'evaluation/candidates/local-preview-v1.json').read_text())
        self.assertEqual(len(packet['cases']), 30)
        self.assertEqual(len({case['id'] for case in packet['cases']}), 30)
        self.assertTrue(all(not case['reviewed_by'] and not case['reviewed_at'] for case in packet['cases']))
        with self.assertRaisesRegex(ValueError, 'human review'):
            validate_dataset(packet)
