"""Protect the existing chat behavior while retrieval gains independent evaluation APIs."""
import unittest
from contextlib import ExitStack
from dataclasses import replace
from unittest.mock import patch

from medivector.models import RetrievalQuery, RiskAssessment
from medivector.qa import ask_question
from test_pure_logic import make_reference


class ChatRegressionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mocks = {}
        defaults = {
            "require_openai_api_key": "fake",
            "assess_question_risk": RiskAssessment("green", "一般", "test", False, ""),
            "load_conversation_history": [{"role": "user", "content": "prior", "references": []}],
            "get_retrieval_query": RetrievalQuery("standalone", ["term"], False),
            "search_references": [make_reference(1, .1)],
            "chat_with_gpt": "answer[1]",
            "save_messages": None,
            "emergency_diversion_answer": "emergency response",
        }
        for name, value in defaults.items():
            self.mocks[name] = self.stack.enter_context(patch(f"medivector.qa.{name}", return_value=value))

    def test_default_rag_keeps_query_rewrite_references_and_history(self):
        result = ask_question({"conversation_id": "conversation", "question": " question "})
        self.mocks["get_retrieval_query"].assert_called_once_with("fake", "question", [{"role": "user", "content": "prior"}])
        self.mocks["search_references"].assert_called_once_with("fake", "standalone", ["term"])
        self.assertTrue(result["rag_enabled"])
        self.assertEqual(result["answer"], "answer[1]")
        self.assertEqual(result["references"][0]["uuid"], "uuid-1")
        self.assertEqual(result["memory_messages"], 3)
        conversation, messages = self.mocks["save_messages"].call_args.args
        self.assertEqual(conversation, "conversation")
        self.assertEqual(messages[0], {"role": "user", "content": "question"})
        self.assertEqual(messages[1]["references"], result["references"])

    def test_disabled_rag_skips_rewrite_and_retrieval(self):
        result = ask_question({"question": "question", "rag_enabled": False})
        self.mocks["get_retrieval_query"].assert_not_called()
        self.mocks["search_references"].assert_not_called()
        self.assertFalse(result["rag_enabled"])
        self.assertEqual(result["references"], [])
        self.assertFalse(self.mocks["chat_with_gpt"].call_args.kwargs["rag_enabled"])
        self.mocks["save_messages"].assert_called_once()

    def test_emergency_diversion_skips_generation_and_retrieval(self):
        self.mocks["assess_question_risk"].return_value = replace(
            self.mocks["assess_question_risk"].return_value, level="red", diverted=True,
        )
        result = ask_question({"question": "question"})
        self.mocks["get_retrieval_query"].assert_not_called()
        self.mocks["search_references"].assert_not_called()
        self.mocks["chat_with_gpt"].assert_not_called()
        self.assertEqual(result["answer"], "emergency response")
        self.assertTrue(result["risk_assessment"]["diverted"])
        self.mocks["save_messages"].assert_called_once()

    def test_generation_failure_does_not_persist_partial_messages(self):
        self.mocks["chat_with_gpt"].side_effect = RuntimeError("upstream failure")
        with self.assertRaisesRegex(RuntimeError, "upstream failure"):
            ask_question({"question": "question"})
        self.mocks["save_messages"].assert_not_called()
