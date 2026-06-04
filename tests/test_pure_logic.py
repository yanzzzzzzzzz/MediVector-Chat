import unittest
from datetime import date

from medivector.chat import RESPONSE_SECTIONS, normalized_template_answer
from medivector.config import MIN_REFERENCE_COUNT
from medivector.conversations import message_metadata
from medivector.documents import metadata_from_payload
from medivector.models import Reference, RiskAssessment
from medivector.qa import conversation_messages_for_model
from medivector.retrieval import assess_evidence, normalize_retrieval_terms, retrieval_query_text
from medivector.risk import level_to_action, level_to_label, parse_risk_level
from medivector.schemas import AskRequest
from medivector.server import app
from medivector.text_processing import split_text_for_embedding


def make_reference(index: int, distance: float | None = None) -> Reference:
    return Reference(
        index=index,
        uuid=f"uuid-{index}",
        document_id=f"document-{index}",
        source_id=index,
        title=f"title-{index}",
        source="source",
        publisher="",
        published_date="",
        version="",
        audience="",
        topic="",
        credibility="",
        content=f"content-{index}",
        distance=distance,
    )


class PureLogicTests(unittest.TestCase):
    def test_normalize_retrieval_terms_trims_and_deduplicates_case_insensitively(self) -> None:
        terms = normalize_retrieval_terms([" 發燒  fever ", "發燒 fever", "", "Pain", "pain"])

        self.assertEqual(terms, ["發燒 fever", "Pain"])

    def test_retrieval_query_text_adds_terms_when_present(self) -> None:
        text = retrieval_query_text("頭痛怎麼辦", [" 頭痛 headache ", "headache"])

        self.assertEqual(text, "頭痛怎麼辦\n\n檢索關鍵詞：頭痛 headache headache")

    def test_split_text_for_embedding_keeps_chunks_within_limit(self) -> None:
        chunks = split_text_for_embedding("alpha\n\nbeta gamma\n\ndelta epsilon", max_chars=12)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 12 for chunk in chunks))

    def test_parse_risk_level_defaults_unknown_to_yellow(self) -> None:
        self.assertEqual(parse_risk_level("RED"), "red")
        self.assertEqual(parse_risk_level("unknown"), "yellow")
        self.assertEqual(level_to_label("green"), "一般")
        self.assertIn("急症分流", level_to_action("red"))

    def test_normalized_template_answer_adds_required_sections(self) -> None:
        risk = RiskAssessment(
            level="yellow",
            label="注意",
            reason="測試",
            diverted=False,
            action="",
        )

        answer = normalized_template_answer("請先觀察症狀。", risk)

        for section in RESPONSE_SECTIONS:
            self.assertIn(section, answer)
        self.assertIn("24 小時內", answer)

    def test_metadata_from_payload_defaults_date(self) -> None:
        metadata = metadata_from_payload({"topic": "睡眠", "published_date": ""})

        self.assertEqual(metadata["topic"], "睡眠")
        self.assertEqual(metadata["published_date"], date.today().isoformat())
        self.assertEqual(metadata["publisher"], "")

    def test_assess_evidence_handles_empty_and_sufficient_reference_count(self) -> None:
        empty = assess_evidence([])
        self.assertFalse(empty.sufficient)
        self.assertEqual(empty.reference_count, 0)

        references = [make_reference(index) for index in range(1, MIN_REFERENCE_COUNT + 1)]
        enough = assess_evidence(references)
        self.assertTrue(enough.sufficient)
        self.assertEqual(enough.reference_count, MIN_REFERENCE_COUNT)

    def test_fastapi_app_and_ask_schema_are_available(self) -> None:
        request = AskRequest(question="頭痛怎麼辦")

        self.assertEqual(app.title, "MediVector API")
        self.assertEqual(request.conversation_id, "default")
        self.assertTrue(request.rag_enabled)

    def test_message_metadata_keeps_reference_payload_for_history_restore(self) -> None:
        metadata = message_metadata({
            "role": "assistant",
            "content": "回答[1]",
            "references": [{"index": 1, "title": "ref"}],
            "retrieval_terms": ["頭痛 headache"],
            "ignored": "不要存",
        })

        self.assertEqual(metadata["references"], [{"index": 1, "title": "ref"}])
        self.assertEqual(metadata["retrieval_terms"], ["頭痛 headache"])
        self.assertNotIn("ignored", metadata)

    def test_conversation_messages_for_model_strips_history_metadata(self) -> None:
        messages = conversation_messages_for_model([
            {
                "role": "assistant",
                "content": "回答[1]",
                "references": [{"index": 1}],
            },
        ])

        self.assertEqual(messages, [{"role": "assistant", "content": "回答[1]"}])


if __name__ == "__main__":
    unittest.main()
