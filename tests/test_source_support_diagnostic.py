import copy
import unittest

from evaluation.prototype_fixture import build_fixture
from evaluation.release_gate import evaluate_gate
from evaluation.representation_comparison import compare
from evaluation.source_support_diagnostic import diagnose, markdown


class SourceSupportDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet, corpus = build_fixture()
        cls.report = compare(cls.packet, corpus, lambda texts: [[1.0, 0.0] for _ in texts])

    def estimate(self, question, refs):
        return {'status': 'insufficient', 'estimated_answerable': False, 'human_reviewed': False,
                'semantic_support_verified': False, 'requirements': [], 'elapsed_ms': 10, 'usage': None}

    def test_comparison_counts_rejections_without_faking_human_review(self):
        packet = copy.deepcopy(self.packet)
        calls = []
        def assess(question, refs):
            calls.append((question, refs))
            return self.estimate(question, refs)
        report = diagnose(self.report, packet, assess, workers=1)
        self.assertEqual(packet, self.packet)
        self.assertEqual(len(calls), 44)
        self.assertEqual(set(calls[0][1][0]), {'chunk_id', 'content', 'title'})
        self.assertEqual(report['retrieval_only']['false_accept'], 8)
        self.assertEqual(report['with_support_estimate']['false_accept'], 0)
        self.assertEqual(report['with_support_estimate']['false_reject'], 36)
        self.assertFalse(report['release_gate_eligible'])
        self.assertIn('challenge-044', markdown(report))
        with self.assertRaises(ValueError):
            evaluate_gate(report)

    def test_source_question_or_packet_drift_rejected_before_calls(self):
        for field in ('content', 'title', 'uuid', 'document_id', 'chunk_metadata'):
            report = copy.deepcopy(self.report)
            report['groups'][1]['runs'][0]['filtered'][0][field] = 'changed'
            with self.assertRaises(ValueError):
                diagnose(report, self.packet, lambda *args: self.fail('Must not call model'))
        report = copy.deepcopy(self.report)
        report['groups'][1]['runs'][0]['question'] = 'changed'
        with self.assertRaises(ValueError):
            diagnose(report, self.packet, lambda *args: self.fail('Must not call model'))
        with self.assertRaises(ValueError):
            diagnose(self.report, {**self.packet, 'notice': 'changed'}, self.estimate)

    def test_cannot_relabel_model_estimate_as_human_verified(self):
        for change in ({'human_reviewed': True}, {'semantic_support_verified': True},
                       {'status': 'sufficient', 'estimated_answerable': False}):
            with self.assertRaises(ValueError):
                diagnose(self.report, self.packet, lambda q, refs: {**self.estimate(q, refs), **change}, workers=1)
