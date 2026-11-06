import copy
import json
import unittest
from unittest.mock import patch

from medivector.source_support import assess_source_support, validate_support


class SourceSupportTests(unittest.TestCase):
    def setUp(self):
        self.refs = [{'chunk_id': 'version-a:chunk-1', 'content': '申請者填寫 COPY-A 表並提交文件服務台。紙本影本於第二工作日領取。'}]
        self.valid = {'requirements': [{'requirement': '申請表單名稱', 'state': 'supported',
                    'evidence': [{'chunk_id': 'version-a:chunk-1', 'quote': '申請者填寫 COPY-A 表並提交文件服務台。'}]}]}

    def test_exact_quotes_have_source_local_offsets_not_claimed_verdicts(self):
        result = validate_support(self.valid, self.refs)
        self.assertTrue(result['estimated_answerable'])
        self.assertFalse(result['human_reviewed'])
        self.assertFalse(result['semantic_support_verified'])
        quote = result['requirements'][0]['evidence'][0]
        self.assertEqual(self.refs[0]['content'][quote['chunk_start']:quote['chunk_end']], quote['quote'])

    def test_missing_partial_and_uncertain_requirements_cannot_be_accepted(self):
        for state, expected in [('missing', 'partial'), ('uncertain', 'uncertain')]:
            parsed = copy.deepcopy(self.valid)
            parsed['requirements'].append({'requirement': '領取費用', 'state': state, 'evidence': []})
            result = validate_support(parsed, self.refs)
            self.assertEqual(result['status'], expected)
            self.assertFalse(result['estimated_answerable'])
        self.assertEqual(validate_support({'requirements': [{'requirement': '費用', 'state': 'missing', 'evidence': []}]}, self.refs)['status'], 'insufficient')

    def test_forged_edited_short_or_wrong_source_quotes_are_rejected(self):
        for changes in ({'quote': '申請費用為零元。'}, {'chunk_id': 'other-version:chunk-1'}, {'quote': '表'}):
            parsed = copy.deepcopy(self.valid)
            parsed['requirements'][0]['evidence'][0].update(changes)
            with self.assertRaises(ValueError):
                validate_support(parsed, self.refs)
        with self.assertRaises(ValueError):
            validate_support({'requirements': []}, self.refs)
        parsed = copy.deepcopy(self.valid)
        parsed['requirements'][0]['evidence'] = []
        with self.assertRaises(ValueError):
            validate_support(parsed, self.refs)
        with self.assertRaises(ValueError):
            validate_support({**self.valid, 'status': 'sufficient'}, self.refs)

    def test_title_can_supply_context_but_cannot_supply_a_supporting_quote(self):
        refs = [{**self.refs[0], 'title': '申請費用為零元'}]
        parsed = copy.deepcopy(self.valid)
        parsed['requirements'][0]['evidence'][0]['quote'] = refs[0]['title']
        with self.assertRaisesRegex(ValueError, 'verbatim source text'):
            validate_support(parsed, refs)

    @patch('medivector.source_support.openai_post')
    def test_empty_sources_and_invalid_input_never_call_model(self, post):
        result = assess_source_support('key', '表單名稱？', [])
        self.assertEqual(result['reason'], 'no_sources')
        self.assertFalse(result['estimated_answerable'])
        for refs in (self.refs * 2, [{'chunk_id': 'x', 'content': 'x' * 30001}]):
            with self.assertRaises(ValueError):
                assess_source_support('key', '表單名稱？', refs)
        post.assert_not_called()

    @patch('medivector.source_support.openai_post')
    def test_request_contains_only_question_and_sources_not_proposed_labels(self, post):
        post.return_value = {'choices': [{'message': {'content': json.dumps(self.valid)}}],
                             'usage': {'total_tokens': 42, 'untrusted_field': 'omit'}}
        refs = [{**self.refs[0], 'answerable': True, 'reviewed_by': 'ignore', 'title': '影本申請'}]
        result = assess_source_support('key', '表單名稱？', refs)
        payload = post.call_args.args[2]
        self.assertEqual(json.loads(payload['messages'][1]['content']),
                         {'question': '表單名稱？', 'source_excerpts': [{**self.refs[0], 'title': '影本申請'}]})
        self.assertEqual(payload['response_format']['type'], 'json_schema')
        self.assertTrue(result['estimated_answerable'])
        self.assertEqual(result['usage'], {'total_tokens': 42})

    @patch('medivector.source_support.openai_post')
    def test_model_failure_refusal_and_invalid_grounding_fail_closed(self, post):
        post.side_effect = RuntimeError('must not copy server error or credential')
        result = assess_source_support('key', '表單名稱？', self.refs)
        self.assertEqual(result['reason'], 'model_request_failed')
        self.assertNotIn('credential', json.dumps(result))
        post.side_effect = None
        invalid = copy.deepcopy(self.valid)
        invalid['requirements'][0]['evidence'][0]['quote'] = '虛構費用原文'
        for response in (None, {'choices': []}, {'choices': [{'message': {'content': None}}]},
                         {'choices': [{'message': {'content': json.dumps(invalid)}}]}):
            post.return_value = response
            result = assess_source_support('key', '表單名稱？', self.refs)
            self.assertFalse(result['estimated_answerable'])
            self.assertEqual(result['reason'], 'invalid_or_ungrounded_model_output')
