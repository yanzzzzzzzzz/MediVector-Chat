import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_qa_regression
from medivector.conversations import message_metadata
from medivector.qa import ask_question
from test_pure_logic import make_reference


class SourceSupportGateTests(unittest.TestCase):
    def setUp(self):
        test_qa_regression.ChatRegressionTests.setUp(self)
        self.context = SimpleNamespace(payload=lambda: {'branch_id': 'a', 'department_id': 'general'})
        self.stack.enter_context(patch('medivector.qa.context_for_request', return_value=self.context))
        self.stack.enter_context(patch('medivector.quality_audit.query_snapshot', return_value={'corpus_sha256': 'test'}))
        self.stack.enter_context(patch('medivector.qa.SOURCE_SUPPORT_CHECK_ENABLED', True))
        self.assess = self.stack.enter_context(patch('medivector.qa.assess_source_support', return_value={
            'status': 'insufficient', 'estimated_answerable': False, 'human_reviewed': False,
            'semantic_support_verified': False, 'supporting_chunk_ids': [],
            'requirements': [{'requirement': 'private raw text must not persist'}]}))

    def test_insufficient_partial_or_uncertain_skips_answer_model_and_persists_only_summary(self):
        for status in ('insufficient', 'partial', 'uncertain'):
            self.assess.return_value['status'] = status
            response = ask_question({'question': 'question'})
            self.assertIn('無法確認院所規範', response['answer'])
            self.assertFalse(response['source_support_assessment']['estimated_answerable'])
            self.assertNotIn('requirements', response['source_support_assessment'])
            self.assertFalse(response['evidence_assessment']['sufficient'])
            saved = self.mocks['save_messages'].call_args.args[1][1]
            self.assertIn('source_support_assessment', message_metadata(saved))
            self.assertNotIn('private raw text', str(saved))
        self.mocks['chat_with_gpt'].assert_not_called()

    def test_sufficient_uses_only_supported_source_chunks_and_standalone_question_for_check(self):
        self.mocks['search_references'].return_value = [make_reference(1, .1), make_reference(2, .11)]
        self.assess.return_value.update(status='sufficient', estimated_answerable=True, supporting_chunk_ids=['uuid-2'])
        response = ask_question({'question': 'question'})
        self.assertEqual(self.assess.call_args.args[1], 'standalone')
        self.assertEqual([r['uuid'] for r in response['references']], ['uuid-2'])
        args = self.mocks['chat_with_gpt'].call_args.args
        self.assertEqual([ref.uuid for ref in args[2]], ['uuid-2'])
        self.assertTrue(self.mocks['chat_with_gpt'].call_args.kwargs['institutional'])

    def test_disabled_gate_or_noninstitutional_chat_never_calls_checker(self):
        with patch('medivector.qa.SOURCE_SUPPORT_CHECK_ENABLED', False):
            self.assertNotIn('source_support_assessment', ask_question({'question': 'question'}))
        with patch('medivector.qa.context_for_request', return_value=None):
            self.assertNotIn('source_support_assessment', ask_question({'question': 'question'}))
        self.assess.assert_not_called()
        self.assertEqual(self.mocks['chat_with_gpt'].call_count, 2)

    def test_input_limit_and_missing_supported_ids_do_not_fall_back_to_generation(self):
        self.assess.side_effect = ValueError('source budget')
        response = ask_question({'question': 'question'})
        self.assertEqual(response['source_support_assessment']['reason'], 'input_budget_or_structure')
        self.assess.side_effect = None
        self.assess.return_value.update(status='sufficient', estimated_answerable=True, supporting_chunk_ids=['not-available'])
        response = ask_question({'question': 'question'})
        self.assertFalse(response['source_support_assessment']['estimated_answerable'])
        self.mocks['chat_with_gpt'].assert_not_called()

    def test_audit_records_that_answer_model_was_skipped_despite_candidate_references(self):
        self.mocks['save_messages'].side_effect = lambda _id, _messages, **kwargs: kwargs['on_saved']('fake-connection')
        with patch('medivector.quality_audit.record_query', return_value='trace') as record:
            response = ask_question({'question': 'question'})
        self.assertEqual(response['query_trace_id'], 'trace')
        self.assertTrue(response['references'])
        snapshot = record.call_args.args[4]
        self.assertIs(snapshot['answer_model_invoked'], False)
        self.assertEqual(snapshot['source_support_assessment']['status'], 'insufficient')
