import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from evaluation.medical_rules import evaluate_suite
from evaluation.release_gate import evaluate_gate
from medivector.experiment_snapshot import build_snapshot, digest

FIXTURES = Path(__file__).parents[1] / 'evaluation' / 'medical_rules_cases.json'


class ReleaseGateTests(unittest.TestCase):
    def report(self, case_id):
        dataset = json.loads(FIXTURES.read_text())
        dataset['cases'] = [c for c in dataset['cases'] if c['id'] == case_id]
        report = evaluate_suite(dataset)
        snapshot = build_snapshot(dataset['source_catalog'], test_dataset_version='synthetic-v1', index_version='index-v1')
        snapshot.update(git_sha='a'*40, working_tree_dirty=False)
        report['snapshot'] = snapshot
        return report

    def approval(self, report):
        return {'report_sha256': digest(report), 'reviewer': 'synthetic-reviewer', 'role': 'reviewer',
                'decision': 'approve', 'reason': 'Synthetic test approval', 'reviewed_at': '2026-11-01T00:00:00Z'}

    def test_pass_review_and_fail_are_distinct_and_fail_cannot_be_overridden(self):
        passed = self.report('annotated-synthetic-positive')
        self.assertTrue(evaluate_gate(passed)['release_allowed'])
        review = self.report('valid-citation-unreviewed')
        self.assertEqual(evaluate_gate(review)['status'], 'Review Required')
        self.assertTrue(evaluate_gate(review, self.approval(review))['release_allowed'])
        failed = self.report('old-version-01')
        self.assertEqual(evaluate_gate(failed, self.approval(failed))['status'], 'Fail')
        self.assertFalse(evaluate_gate(failed, self.approval(failed))['release_allowed'])

    def test_tampered_summary_trace_or_approval_fails_closed(self):
        report = self.report('old-version-01')
        report['results'][0]['status'] = 'Pass'
        with self.assertRaises(ValueError): evaluate_gate(report)
        report = self.report('annotated-synthetic-positive')
        report['results'][0]['trace']['references'][0]['document_version_id'] = 'wrong-version'
        with self.assertRaises(ValueError): evaluate_gate(report)
        report = self.report('valid-citation-unreviewed')
        approval = self.approval(report)
        report['results'][0]['question'] += 'changed'
        with self.assertRaises(ValueError): evaluate_gate(report, approval)
        approval = self.approval(report); approval['role'] = 'nurse'
        with self.assertRaises(ValueError): evaluate_gate(report, approval)
        with self.assertRaises(ValueError): evaluate_gate({'results': []})

    def test_missing_build_identity_or_frozen_versions_requires_review(self):
        report = self.report('annotated-synthetic-positive')
        report['snapshot']['git_sha'] = 'unknown'
        self.assertEqual(evaluate_gate(report)['status'], 'Review Required')
        report = self.report('annotated-synthetic-positive')
        report['snapshot']['test_dataset_version'] = None
        self.assertEqual(evaluate_gate(report)['status'], 'Review Required')
        report['snapshot']['corpus'] = {'tampered': True}
        with self.assertRaises(ValueError): evaluate_gate(report)

    def test_snapshot_is_allowlisted_and_never_serializes_environment_secrets(self):
        secret = 'SYNTHETIC-NOT-A-REAL-SECRET-DO-NOT-LOG'
        with patch.dict(os.environ, {'OPENAI_API_KEY': secret, 'PG_PASSWORD': secret, 'API_USERS': secret}):
            snapshot = build_snapshot({'version-1': {'checksum': 'abc'}}, test_dataset_version='dataset-v1')
        self.assertNotIn(secret, json.dumps(snapshot))
        self.assertEqual(snapshot['corpus_sha256'], digest(snapshot['corpus']))
        self.assertIn('chat.py', snapshot['prompt_versions'])
        self.assertEqual(len(snapshot['source_sha256']), 64)

    def test_cli_exit_codes_and_history_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for case, expected in [('old-version-01', 2), ('valid-citation-unreviewed', 3), ('annotated-synthetic-positive', 0)]:
                report_path = directory / (case + '.json')
                report_path.write_text(json.dumps(self.report(case)))
                output = directory / (case + '-gate.json')
                result = subprocess.run([sys.executable, '-m', 'evaluation.release_gate', str(report_path), str(output)], capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr.decode())
                self.assertTrue(output.with_suffix('.md').exists())
