import unittest

from evaluation.prototype_fixture import build_fixture
from evaluation.representation_comparison import compare
from evaluation.threshold_sweep import sweep, markdown


class ThresholdSweepTests(unittest.TestCase):
    def test_replays_saved_vectors_and_binds_exact_packet(self):
        packet, corpus = build_fixture()
        report = compare(packet, corpus, lambda inputs: [[1.0, 0.0] for _ in inputs])
        result = sweep(report, packet)
        self.assertEqual(len(result['rows']), 32)
        self.assertFalse(result['verified_baseline'])
        self.assertFalse(result['release_gate_eligible'])
        self.assertTrue(all(r['unanswerable_with_candidates'] == 8 for r in result['rows']))
        self.assertIn('page_chunks', markdown(result))
        with self.assertRaisesRegex(ValueError, 'packet differs'):
            sweep(report, {**packet, 'notice': 'changed'})
        with self.assertRaises(ValueError):
            sweep({**report, 'verified_baseline': True}, packet)

    def test_stricter_maximum_cannot_add_candidates(self):
        packet, corpus = build_fixture()
        # Unit vectors at cosine distance .4 put all source candidates between two cutoffs.
        queries = {case['query'] for case in packet['cases']}
        report = compare(packet, corpus, lambda inputs: [[1.0, 0.0] if text in queries else [0.6, 0.8] for text in inputs])
        result = sweep(report, packet)
        for row in result['rows']:
            self.assertEqual(row['unanswerable_with_candidates'], 0 if row['max_distance'] == .35 else 8)
