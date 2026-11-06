import json
import unittest
from pathlib import Path

from evaluation.release_gate import evaluate_gate
from evaluation.source_support_boundaries import build_boundaries
from evaluation.source_support_diagnostic import diagnose, markdown
from evaluation.synthetic_diagnostic import validate_candidate_packet


class SourceSupportBoundaryTests(unittest.TestCase):
    def test_frozen_boundaries_cover_categories_and_never_claim_retrieval_or_human_review(self):
        packet, inputs = build_boundaries()
        root = Path(__file__).parents[1] / 'evaluation' / 'candidates'
        self.assertEqual(packet, json.loads((root / 'source-support-boundaries-v1.json').read_text()))
        self.assertEqual(inputs, json.loads((root / 'source-support-boundary-input-v1.json').read_text()))
        validate_candidate_packet(packet)
        self.assertEqual(len(packet['cases']), 18)
        self.assertEqual({c['category'] for c in packet['cases']},
                         {'compound', 'exception', 'negation', 'instruction', 'conflict'})
        self.assertEqual(inputs['input_kind'], 'synthetic_direct_excerpts_without_retrieval')
        self.assertTrue(all(not c['reviewed_by'] and not c['reviewed_at'] for c in packet['cases']))
        for category in {c['category'] for c in packet['cases']}:
            self.assertTrue(any(c['answerable'] for c in packet['cases'] if c['category'] == category))
            self.assertTrue(any(not c['answerable'] for c in packet['cases'] if c['category'] == category))

    def test_boundary_adapter_does_not_send_labels_and_remains_ineligible_for_gate(self):
        packet, inputs = build_boundaries()
        calls = []
        def estimate(question, refs):
            calls.append(refs)
            return {'status': 'uncertain', 'estimated_answerable': False, 'human_reviewed': False,
                    'semantic_support_verified': False, 'elapsed_ms': 1, 'usage': None}
        report = diagnose(inputs, packet, estimate, variant='direct_excerpts', workers=1)
        self.assertEqual(len(calls), 18)
        self.assertEqual(set(calls[0][0]), {'chunk_id', 'content'})
        self.assertNotIn('proposed_rationale', str(calls))
        self.assertFalse(report['verified_baseline'])
        self.assertIn('無檢索比較', markdown(report))
        with self.assertRaises(ValueError):
            evaluate_gate(report)

    def test_scope_probes_separate_document_coverage_from_actual_rules(self):
        packet, inputs = build_boundaries(scope_probes=True)
        root = Path(__file__).parents[1] / 'evaluation' / 'candidates'
        self.assertEqual(packet, json.loads((root / 'source-support-scope-probes-v1.json').read_text()))
        self.assertEqual(inputs, json.loads((root / 'source-support-scope-input-v1.json').read_text()))
        self.assertEqual([c['answerable'] for c in packet['cases']], [True, False, True, False])
        self.assertNotEqual(packet['dataset_version'], build_boundaries()[0]['dataset_version'])
        validate_candidate_packet(packet)
