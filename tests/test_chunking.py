import unittest
from evaluation.chunking import chunk_manifest


class ChunkingTests(unittest.TestCase):
    def test_baseline_source_offsets(self):
        text = "alpha\n\nbeta gamma\n\ndelta epsilon"
        manifest = chunk_manifest(text, document_id="doc", version="v1", max_chars=12)
        for chunk in manifest["chunks"]:
            self.assertEqual(text[chunk["start"]:chunk["end"]], chunk["content"])

    def test_tokens_overlap_unicode_pages(self):
        text = "頭痛衛教😀請注意休息。" * 15
        pages = [{"page": 1, "start": 0, "end": 50}, {"page": 2, "start": 50, "end": len(text)}]
        manifest = chunk_manifest(text, document_id="doc", version="v2", strategy="token", max_tokens=24, overlap=6, pages=pages)
        chunks = manifest["chunks"]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c["token_count"] <= 24 for c in chunks))
        self.assertEqual(chunks[0]["start"], 0)
        self.assertEqual(chunks[-1]["end"], len(text))
        for a, b in zip(chunks, chunks[1:]):
            self.assertLess(b["start"], a["end"])
            self.assertGreater(b["start"], a["start"])
        for c in chunks:
            self.assertEqual(c["content"], text[c["start"]:c["end"]])
        self.assertTrue(any(2 in c["pages"] for c in chunks))

    def test_baseline_maps_normalized_whitespace(self):
        text = "alpha\n\n\n  beta\n\n\n  gamma"
        manifest = chunk_manifest(text, document_id="doc", version="v1", max_chars=14)
        self.assertTrue(any(c["whitespace_normalized"] for c in manifest["chunks"]))
        self.assertEqual(manifest["chunks"][0]["start"], 0)

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            chunk_manifest("x", document_id="doc", version="v1", max_tokens=8, overlap=8)

    def test_pdf_keeps_blank_page_and_failed_page_diagnostics_without_false_citations(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from medivector.chunking import page_text
        good = SimpleNamespace(extract_text=lambda: 'original text')
        blank = SimpleNamespace(extract_text=lambda: '')
        def failed():
            raise ValueError('broken page')
        with patch('pypdf.PdfReader', return_value=SimpleNamespace(pages=[good, blank, SimpleNamespace(extract_text=failed), good])):
            text, pages = page_text(b'fixture')
        self.assertEqual([page['status'] for page in pages], ['extracted', 'no_text', 'extraction_failed', 'extracted'])
        manifest = chunk_manifest(text, document_id='doc', version='v1', pages=pages)
        self.assertEqual(manifest['chunks'][0]['pages'], [1, 4])
