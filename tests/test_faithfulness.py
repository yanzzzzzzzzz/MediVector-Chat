import json
import unittest
from pathlib import Path
from evaluation.faithfulness import evaluate


class FaithfulnessTests(unittest.TestCase):
    def test_citation_failure_modes(self):
        cases = json.loads(Path('evaluation/faithfulness_cases.json').read_text())
        reports = {case['id']: evaluate(case) for case in cases}
        self.assertEqual(reports['supported']['generation_faithfulness'], 'pass')
        for name in ('missing', 'nonexistent', 'unsupported', 'no-evidence'):
            self.assertEqual(reports[name]['generation_faithfulness'], 'fail')
        self.assertEqual(reports['unreviewed']['generation_faithfulness'], 'unreviewed')
        self.assertEqual(reports['nonexistent']['invalid_citations'], [2])
        self.assertTrue(reports['unsupported']['unsupported_citations'])

    def test_nonexistent_citation_fails_even_when_semantics_are_unreviewed(self):
        from evaluation.faithfulness import evaluate
        case = {'id': 'invalid-unreviewed', 'references': [{'index': 1}], 'answer': 'Unknown claim [索引 2]',
                'claims': [], 'review_status': 'pending_human'}
        self.assertEqual(evaluate(case)['invalid_citations'], [2])
        self.assertEqual(evaluate(case)['generation_faithfulness'], 'fail')

    def test_pending_human_annotations_cannot_be_reported_as_pass(self):
        from evaluation.faithfulness import evaluate
        case = {'id': 'pending', 'references': [{'index': 1}], 'answer': 'Synthetic [索引1]',
                'claims': [{'text': 'Synthetic', 'citations': [1], 'support': {'1': True}}], 'review_status': 'pending_human'}
        self.assertEqual(evaluate(case)['generation_faithfulness'], 'unreviewed')
