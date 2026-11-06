import json
import unittest
from pathlib import Path
from evaluation.faithfulness import evaluate


class FaithfulnessTests(unittest.TestCase):
    def reviewed_case(self):
        return {'id': 'reviewed', 'references': [{'index': 1}],
                'answer': 'First.[1] Second.[1]', 'review_status': 'reviewed',
                'reviewed_by': 'synthetic-test-reviewer', 'reviewed_at': '2026-11-07T01:00:00+08:00',
                'claims': [{'text': 'First.', 'citations': [1], 'support': {'1': True}},
                           {'text': 'Second.', 'citations': [1], 'support': {'1': True}}]}

    def test_unannotated_answer_text_cannot_pass(self):
        case = self.reviewed_case()
        case['claims'].pop()
        result = evaluate(case)
        self.assertFalse(result['annotation_coverage_complete'])
        self.assertEqual(result['generation_faithfulness'], 'unreviewed')

    def test_unrelated_or_reordered_claims_cannot_pass(self):
        for claims in ([{'text': 'Unrelated.', 'citations': [1], 'support': {'1': True}}],
                       list(reversed(self.reviewed_case()['claims']))):
            case = self.reviewed_case()
            case['claims'] = claims
            self.assertEqual(evaluate(case)['generation_faithfulness'], 'unreviewed')

    def test_annotated_citation_must_exist_in_answer_and_references(self):
        for citation in (2, True, '1'):
            case = self.reviewed_case()
            case['claims'][0]['citations'] = [citation]
            self.assertEqual(evaluate(case)['generation_faithfulness'], 'fail')
        case = self.reviewed_case()
        case['answer'] = 'First. Second.'
        self.assertEqual(evaluate(case)['generation_faithfulness'], 'fail')

    def test_claim_coverage_ignores_citation_syntax_and_whitespace_only(self):
        case = self.reviewed_case()
        case['answer'] = 'First. [索引 1]\nSecond.[1]'
        result = evaluate(case)
        self.assertTrue(result['annotation_coverage_complete'])
        self.assertTrue(result['human_review_provenance_valid'])
        self.assertEqual(result['generation_faithfulness'], 'pass')

    def test_reviewed_status_requires_supplied_reviewer_and_timezone(self):
        for field, value in (('reviewed_by', ' '), ('reviewed_at', '2026-11-07T01:00:00'),
                             ('reviewed_at', 'invalid')):
            case = self.reviewed_case()
            case[field] = value
            self.assertEqual(evaluate(case)['generation_faithfulness'], 'unreviewed')

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
