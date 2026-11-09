import copy
import hashlib
import json
import unittest
from pathlib import Path

from evaluation.representation_comparison import compare, cosine_distance, markdown, representations
from medivector.chunking import page_text
from pdf_fixture import pdf_bytes


class RepresentationComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1] / 'evaluation' / 'candidates'
        cls.packet = json.loads((root / 'local-preview-v1.json').read_text())
        cls.corpus = json.loads((root / 'local-preview-corpus-v1.json').read_text())

    def test_page_split_preserves_source_offsets_and_skips_blank_page(self):
        sources = self.corpus['sources']
        rows = representations(sources, 'page_chunks')
        pdf_rows = [r for r in rows if r['version_id'] == sources[1]['id']]
        self.assertEqual([r['chunk_metadata']['pages'] for r in pdf_rows], [[1], [3]])
        self.assertNotIn('Page three:', pdf_rows[0]['embedding_input'])
        for row in rows:
            source = next(s for s in sources if s['id'] == row['version_id'])
            m = row['chunk_metadata']
            self.assertEqual(source['content'][m['start']:m['end']], row['content'])
            self.assertEqual(m['source_sha256'], hashlib.sha256(source['content'].encode()).hexdigest())

    def test_variants_only_change_embedding_representation_until_page_split(self):
        body, title, pages = [representations(self.corpus['sources'], v) for v in ('body', 'title', 'title_pages')]
        for a, b, c in zip(body, title, pages):
            self.assertEqual(a['content'], a['embedding_input'])
            self.assertEqual(a['content'], b['content'])
            self.assertEqual(a['chunk_metadata'], c['chunk_metadata'])
            self.assertTrue(b['embedding_input'].startswith('文件標題：'))
        self.assertIn('PDF 頁碼：1、3', pages[1]['embedding_input'])

    def test_real_pdf_long_page_is_bounded_and_retains_last_page_evidence(self):
        text, pages = page_text(pdf_bytes([
            ['Repeated selectable PDF text. ' * 260, 'End of long page evidence.'],
            [], ['Final page evidence: form Z-42.'],
        ]))
        source = {'id': 'pdf-v1', 'document_id': 'pdf-doc', 'title': 'Long PDF',
                  'content': text, 'pages': pages,
                  'checksum': hashlib.sha256(text.encode()).hexdigest()}
        rows = representations([source], 'page_chunks')
        self.assertGreater(len(rows), 2)
        self.assertEqual([p['status'] for p in pages], ['extracted', 'no_text', 'extracted'])
        self.assertEqual(rows[-1]['chunk_metadata']['pages'], [3])
        self.assertIn('form Z-42', rows[-1]['content'])
        self.assertTrue(all(len(row['content']) <= 6000 for row in rows))
        for row in rows:
            meta = row['chunk_metadata']
            self.assertEqual(row['content'], text[meta['start']:meta['end']])
            page = pages[meta['pages'][0] - 1]
            self.assertGreaterEqual(meta['start'], page['start'])
            self.assertLessEqual(meta['end'], page['end'])
        for page in (pages[0], pages[2]):
            page_rows = [r for r in rows if r['chunk_metadata']['pages'] == [page['page']]]
            self.assertEqual(''.join(r['content'] for r in page_rows), text[page['start']:page['end']])

    def test_real_pdf_short_pages_keep_existing_representation(self):
        text, pages = page_text(pdf_bytes([['First page.'], [], ['Third page.']]))
        source = {'id': 'short-v1', 'document_id': 'short-doc', 'title': 'Short PDF',
                  'content': text, 'pages': pages,
                  'checksum': hashlib.sha256(text.encode()).hexdigest()}
        rows = representations([source], 'page_chunks')
        self.assertEqual([r['content'] for r in rows], ['First page.', 'Third page.'])
        self.assertEqual([r['chunk_metadata']['pages'] for r in rows], [[1], [3]])

    def test_rejects_source_drift_and_invalid_page_mapping(self):
        sources = copy.deepcopy(self.corpus['sources'])
        sources[0]['content'] += 'changed'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            representations(sources, 'body')
        sources = copy.deepcopy(self.corpus['sources'])
        sources[1]['pages'][0]['end'] = 10000
        with self.assertRaisesRegex(ValueError, 'offsets'):
            representations(sources, 'page_chunks')

    def test_shared_embeddings_diagnostics_and_no_review_mutation(self):
        calls = []
        original = copy.deepcopy(self.packet)
        def embed(texts):
            calls.append(texts)
            return [[1.0, 0.0] for _ in texts]
        report = compare(self.packet, self.corpus, embed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), len(set(calls[0])))
        self.assertEqual(self.packet, original)
        self.assertFalse(report['release_gate_eligible'])
        self.assertFalse(report['verified_baseline'])
        self.assertEqual([g['chunk_count'] for g in report['groups']], [2, 2, 2, 3])
        self.assertEqual(len(report['groups'][0]['runs']), 30)
        self.assertIn('candidate-030', markdown(report))
        self.assertEqual(report['groups'][0]['proposed_label_summary']['unanswerable_return_rate'], 1)

    def test_bad_inputs_fail_before_embedding(self):
        for key, value in [('review_status', 'reviewed'), ('corpus_version', 'changed'), ('embedding_model', 'changed')]:
            packet = {**self.packet, key: value}
            with self.assertRaises(ValueError):
                compare(packet, self.corpus, lambda _: self.fail('Must not call embeddings'))
        with self.assertRaisesRegex(ValueError, 'count'):
            compare(self.packet, self.corpus, lambda _: [])

    def test_mixed_review_and_source_identity_drift_are_rejected(self):
        packet = copy.deepcopy(self.packet)
        packet['cases'][0]['reviewed_by'] = 'someone'
        with self.assertRaises(ValueError):
            compare(packet, self.corpus, lambda _: self.fail('Must not embed'))
        corpus = copy.deepcopy(self.corpus)
        corpus['sources'][0]['document_id'] = 'another-document'
        with self.assertRaisesRegex(ValueError, 'identity'):
            compare(self.packet, corpus, lambda _: self.fail('Must not embed'))

    def test_cosine_rejects_invalid_vectors(self):
        self.assertAlmostEqual(cosine_distance([1, 0], [1, 0]), 0)
        self.assertAlmostEqual(cosine_distance([1, 0], [0, 1]), 1)
        for vector in ([], [0, 0], [float('nan'), 1], [1], [float('inf'), 0]):
            with self.assertRaises(ValueError):
                cosine_distance([1, 0], vector)
