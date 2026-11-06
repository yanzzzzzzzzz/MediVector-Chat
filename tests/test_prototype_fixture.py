import hashlib
import json
import unittest
from pathlib import Path

from evaluation.prototype_fixture import build_fixture
from evaluation.representation_comparison import representations
from evaluation.retrieval_baseline import validate_dataset
from evaluation.synthetic_diagnostic import validate_candidate_packet


class PrototypeFixtureTests(unittest.TestCase):
    def test_frozen_fixture_is_reproducible_unreviewed_and_self_consistent(self):
        packet, corpus = build_fixture()
        root = Path(__file__).parents[1] / 'evaluation' / 'candidates'
        self.assertEqual(packet, json.loads((root / 'prototype-challenge-v1.json').read_text()))
        self.assertEqual(corpus, json.loads((root / 'prototype-challenge-corpus-v1.json').read_text()))
        validate_candidate_packet(packet)
        with self.assertRaisesRegex(ValueError, 'human review'):
            validate_dataset(packet)
        self.assertEqual(len(corpus['sources']), 12)
        self.assertEqual(len(packet['cases']), 44)
        self.assertEqual(sum(c['answerable'] for c in packet['cases']), 36)
        sources = {s['document_id']: s for s in corpus['sources']}
        for source in sources.values():
            self.assertEqual(source['checksum'], hashlib.sha256(source['content'].encode()).hexdigest())
        for case in packet['cases']:
            self.assertFalse(case['reviewed_by'])
            self.assertFalse(case['reviewed_at'])
            for span in case['evidence_spans']:
                source = sources[span['document_id']]
                self.assertEqual(source['checksum'], span['source_sha256'])
                self.assertGreater(len(source['content'][span['start']:span['end']]), 0)
        self.assertTrue({'similar_titles', 'paraphrase', 'long_document', 'cross_language', 'no_answer'} <=
                        {c['category'] for c in packet['cases']})

    def test_challenge_exercises_long_chunks_and_true_page_numbers(self):
        _, corpus = build_fixture()
        body = representations(corpus['sources'], 'body')
        pages = representations(corpus['sources'], 'page_chunks')
        self.assertGreater(len(body), len(corpus['sources']))
        self.assertGreater(len(pages), len(body))
        english = corpus['sources'][-2]
        selected = [r for r in pages if r['document_id'] == english['document_id']]
        self.assertEqual([r['chunk_metadata']['pages'] for r in selected], [[1], [3], [4]])
        for row in body + pages:
            source = next(s for s in corpus['sources'] if s['document_id'] == row['document_id'])
            m = row['chunk_metadata']
            self.assertEqual(row['content'], source['content'][m['start']:m['end']])
