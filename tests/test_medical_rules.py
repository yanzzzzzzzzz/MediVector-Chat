import copy
import json
import tempfile
import unittest
from pathlib import Path
from evaluation.medical_rules import evaluate_case, evaluate_suite, markdown
from evaluation.retrieval_baseline import medical_rules_for_run

FIXTURES = Path(__file__).parents[1] / 'evaluation' / 'medical_rules_cases.json'


class MedicalRuleTests(unittest.TestCase):
    def setUp(self):
        self.dataset = json.loads(FIXTURES.read_text())

    def test_all_synthetic_expectations_and_five_cases_per_negative_category(self):
        report = evaluate_suite(self.dataset)
        self.assertEqual(len(report['results']), 19)
        for category in ('old-version', 'wrong-scope', 'no-answer'):
            self.assertEqual(sum(c['category'] == category for c in self.dataset['cases']), 5)
        for row in report['results']:
            self.assertEqual(row['status'], row['expected_rule_outcome'], row['case_id'])
        self.assertEqual(report['summary'], {'Pass': 2, 'Fail': 15, 'Review Required': 2})
        self.assertIn('citation.effective_version', markdown(report))
        self.assertIn('v-old-version-0', markdown(report))

    def test_unreviewed_valid_citations_are_never_semantic_pass(self):
        case = next(c for c in self.dataset['cases'] if c['id'] == 'valid-citation-unreviewed')
        self.assertEqual(evaluate_case(case, self.dataset['source_catalog'])['status'], 'Review Required')
        case['support_review'] = {'verdict': 'supported'}
        self.assertEqual(evaluate_case(case, self.dataset['source_catalog'])['status'], 'Review Required')

    def test_identity_pollution_invalid_answer_indices_and_missing_evidence_fail(self):
        base = next(c for c in self.dataset['cases'] if c['id'] == 'annotated-synthetic-positive')
        for mutation in ('version', 'document', 'chunk', 'index', 'missing'):
            case = copy.deepcopy(base)
            ref = case['trace']['references'][0]
            if mutation == 'version': ref['document_version_id'] = 'invented'
            if mutation == 'document': ref['document_id'] = 'other-document'
            if mutation == 'chunk': ref['uuid'] = 'other-chunk'
            if mutation == 'index': case['trace']['answer'] = 'Wrong [99]'
            if mutation == 'missing': case['trace']['references'] = []
            self.assertEqual(evaluate_case(case, self.dataset['source_catalog'])['status'], 'Fail', mutation)

    def test_timezone_boundaries_and_bad_labels_fail_closed(self):
        dataset = copy.deepcopy(self.dataset)
        dataset['cases'][0]['context']['query_at'] = '2026-11-01T00:00:00'
        with self.assertRaises(ValueError): evaluate_suite(dataset)
        dataset = copy.deepcopy(self.dataset)
        dataset['cases'][0]['expectedDocumentVersionIds'] = []
        with self.assertRaises(ValueError): evaluate_suite(dataset)
        dataset = copy.deepcopy(self.dataset)
        dataset['cases'][1]['id'] = dataset['cases'][0]['id']
        with self.assertRaises(ValueError): evaluate_suite(dataset)

    def test_retrieval_batch_integration_refuses_a_different_corpus(self):
        report = medical_rules_for_run(FIXTURES, self.dataset['corpus_version'])
        self.assertEqual(report['summary']['Fail'], 15)
        with self.assertRaises(ValueError): medical_rules_for_run(FIXTURES, 'different-corpus')

    def test_cli_outputs_json_and_markdown_and_refuses_report_overwrite(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'rules.json'
            args = [sys.executable, '-m', 'evaluation.medical_rules', str(FIXTURES), str(output)]
            subprocess.run(args, check=True, capture_output=True)
            self.assertEqual(json.loads(output.read_text())['summary']['Fail'], 15)
            self.assertTrue(output.with_suffix('.md').exists())
            self.assertNotEqual(subprocess.run(args, capture_output=True).returncode, 0)
