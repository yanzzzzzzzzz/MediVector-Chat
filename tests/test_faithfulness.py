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
