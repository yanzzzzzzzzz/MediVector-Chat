import copy
import json
import unittest
import httpx
from evaluation.retrieval_baseline import validate_dataset
from evaluation.synthetic_diagnostic import diagnose, validate_candidate_packet, markdown
from evaluation.release_gate import evaluate_gate


class SyntheticDiagnosticTests(unittest.TestCase):
    def packet(self):
        return {'dataset_version': 'DRAFT-synthetic', 'review_status': 'pending_human', 'notice': 'Synthetic test, not reviewed',
                'corpus_version': 'frozen', 'index_version': 'index', 'embedding_model': 'model',
                'retrieval_context': {'branch_id': 'a', 'department_id': 'general'},
                'cases': [{'id': f'case-{i}', 'query': f'question-{i}', 'answerable': i < 3,
                           'relevant_document_ids': ['doc'] if i < 3 else [],
                           'evidence_spans': [{'document_id': 'doc', 'source_sha256': 'sha', 'start': 0, 'end': 4}] if i < 3 else [],
                           'reviewed_by': '', 'reviewed_at': ''} for i in range(6)]}

    def client(self, requests, drift=False, query_drift=False, model_drift=False):
        gets = 0
        def handle(request):
            nonlocal gets
            if request.method == 'GET':
                gets += 1
                return httpx.Response(200, json={'manifest_sha256': 'changed' if drift and gets > 1 else 'frozen',
                                                'versions': [{'version_id': 'version', 'chunk_ids': ['chunk']} ]})
            payload = json.loads(request.content)
            requests.append(payload)
            number = int(payload['question'].split('-')[-1])
            if payload['mode'] == 'filtered':
                self.assertFalse(payload['query_expansion'])
                self.assertTrue(payload['question'].startswith('standalone-'))
            refs = [{'document_id': 'doc', 'document_version_id': 'version', 'chunk_id': 'chunk', 'distance': .4,
                     'rank': 1, 'chunk_metadata': {'source_sha256': 'sha', 'start': 0, 'end': 5}}]
            if payload['mode'] == 'filtered' and number in (0, 4, 5):
                refs = []
            return httpx.Response(200, json={'results': refs, 'standalone_query': 'drifted' if query_drift and payload['mode'] == 'filtered' else f'standalone-{number}', 'terms': ['synthetic-term'],
                                            'settings': {'embedding_model': 'different' if model_drift else 'model'}, 'elapsed_ms': 2})
        return httpx.Client(base_url='https://example.invalid', transport=httpx.MockTransport(handle))

    def test_runs_replay_queries_and_report_provisional_misses_without_mutating_labels(self):
        packet = self.packet()
        before = copy.deepcopy(packet)
        requests, progress = [], []
        with self.client(requests) as client:
            report = diagnose(client, packet, lambda *args: progress.append(args))
        self.assertEqual(packet, before)
        self.assertEqual(len(requests), 24)
        self.assertEqual(len(progress), 24)
        self.assertEqual(len(report['groups']), 4)
        self.assertFalse(report['verified_baseline'])
        self.assertFalse(report['release_gate_eligible'])
        self.assertTrue(report['k_comparison_limited'])
        self.assertEqual({case['case_id'] for case in report['review_queue']}, {'case-0', 'case-3'})
        self.assertIn('未經人工審查', markdown(report))
        self.assertNotIn('dataset', report)
        self.assertNotIn('experiments', report)
        self.assertEqual(report['snapshot']['test_dataset_version'], None)

    def test_pending_packet_still_cannot_be_baseline_or_release_gate(self):
        packet = self.packet()
        with self.assertRaisesRegex(ValueError, 'human review'):
            validate_dataset(packet)
        with self.client([]) as client:
            report = diagnose(client, packet)
        with self.assertRaises(ValueError):
            evaluate_gate(report)

    def test_rejects_scope_override_mixed_review_and_duplicate_ids(self):
        for mutation in ('scope', 'mixed', 'duplicate', 'reviewed'):
            packet = self.packet()
            if mutation == 'scope': packet['retrieval_context']['organization_id'] = 'other'
            if mutation == 'mixed': packet['cases'][0]['reviewed_by'] = 'somebody'
            if mutation == 'duplicate': packet['cases'][0]['id'] = packet['cases'][1]['id']
            if mutation == 'reviewed': packet['review_status'] = 'reviewed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_candidate_packet(packet)

    def test_changed_corpus_aborts_report(self):
        with self.client([], drift=True) as client, self.assertRaisesRegex(ValueError, 'manifest changed'):
            diagnose(client, self.packet())

    def test_changed_model_or_replayed_query_aborts_comparison(self):
        for settings in ({'query_drift': True}, {'model_drift': True}):
            with self.subTest(settings=settings), self.client([], **settings) as client, self.assertRaises(ValueError):
                diagnose(client, self.packet())
