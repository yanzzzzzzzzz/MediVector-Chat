import unittest
from unittest.mock import patch

from medivector.chat import chat_with_gpt, institutional_answer
from medivector.models import EvidenceAssessment, RiskAssessment
from test_pure_logic import make_reference


class ChatModelTests(unittest.TestCase):
    def test_luna_requests_explicit_non_reasoning_in_both_answer_paths(self):
        response = {"choices": [{"message": {"content": "示範回答 [索引1]"}}]}
        with patch('medivector.chat.CHAT_MODEL', 'gpt-6-luna'), patch('medivector.chat.openai_post', return_value=response) as post:
            institutional_answer('test-key', '問題', [make_reference(1)])
            chat_with_gpt('test-key', '問題', [], [],
                          RiskAssessment('green', '一般', '測試', False, ''),
                          EvidenceAssessment(False, '測試', 0, None))
        self.assertEqual(post.call_count, 2)
        for call in post.call_args_list:
            payload = call.args[2]
            self.assertEqual(call.args[1], '/chat/completions')
            self.assertEqual(payload['model'], 'gpt-6-luna')
            self.assertEqual(payload['reasoning_effort'], 'none')
            self.assertTrue(payload['messages'])
        self.assertEqual(post.call_args_list[0].args[2]['temperature'], 0)
        self.assertEqual(post.call_args_list[1].args[2]['temperature'], 0.2)

    def test_existing_non_reasoning_model_override_preserves_its_payload(self):
        with patch('medivector.chat.CHAT_MODEL', 'gpt-4.1-mini'), patch('medivector.chat.openai_post', return_value={"choices": [{"message": {"content": "測試"}}]}) as post:
            institutional_answer('test-key', '問題', [make_reference(1)])
        self.assertNotIn('reasoning_effort', post.call_args.args[2])
        self.assertEqual(post.call_args.args[2]['model'], 'gpt-4.1-mini')
