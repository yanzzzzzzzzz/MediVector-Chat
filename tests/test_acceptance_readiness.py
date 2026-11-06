import copy
import json
import unittest
from pathlib import Path

from evaluation.acceptance_readiness import inspect, markdown


class AcceptanceReadinessTests(unittest.TestCase):
    def inputs(self):
        return [json.loads(Path(path).read_text()) for path in (
            'evaluation/candidates/local-preview-v1.json',
            'evaluation/candidates/answer-support-v1.json',
            'docs/pilot/pilot-report.template.json')]

    def test_prepared_materials_are_not_completed_acceptance(self):
        report = inspect(*self.inputs())
        self.assertFalse(report['release_gate_eligible'])
        self.assertFalse(report['issues']['5']['input_ready_for_acceptance'])
        self.assertFalse(report['issues']['8']['input_ready_for_baseline'])
        self.assertEqual(report['issues']['8']['cases'], 30)
        self.assertEqual(report['issues']['20']['record_counts']['participants'], 0)
        self.assertIn('#9 / #10 / #12', markdown(report))

    def test_inputs_are_never_marked_reviewed_or_modified(self):
        inputs = self.inputs()
        original = copy.deepcopy(inputs)
        inspect(*inputs)
        self.assertEqual(inputs, original)

    def test_supplied_review_fields_do_not_certify_human_work(self):
        dataset, answers, pilot = self.inputs()
        dataset['review_status'] = 'reviewed'
        for case in dataset['cases']:
            case.update(reviewed_by='synthetic-test-reviewer', reviewed_at='2026-11-07T01:00:00+08:00')
        pilot.update(status='completed', participants=[{'alias': f'P{i}'} for i in range(3)])
        report = inspect(dataset, answers, pilot)
        self.assertTrue(report['issues']['8']['input_ready_for_baseline'])
        self.assertFalse(report['issues']['8']['baseline_execution_verified'])
        self.assertFalse(report['issues']['20']['real_participation_verified'])
        self.assertEqual(report['status'], 'external_acceptance_required')

    def test_incomplete_or_invalid_dataset_remains_blocked(self):
        for mutation in ('short', 'timestamp'):
            dataset, answers, pilot = self.inputs()
            dataset['review_status'] = 'reviewed'
            for case in dataset['cases']:
                case.update(reviewed_by='synthetic-test-reviewer', reviewed_at='2026-11-07T01:00:00+08:00')
            if mutation == 'short':
                dataset['cases'].pop()
            else:
                dataset['cases'][0]['reviewed_at'] = '2026-11-07T01:00:00'
            self.assertFalse(inspect(dataset, answers, pilot)['issues']['8']['input_ready_for_baseline'])
