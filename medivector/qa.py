from typing import Any

from .chat import chat_with_gpt
from .config import MEMORY_MESSAGES
from .conversations import load_conversation_history, save_messages
from .models import EvidenceAssessment, Reference
from .openai_client import require_openai_api_key
from .retrieval import assess_evidence, get_retrieval_query, search_references
from .risk import assess_question_risk, emergency_diversion_answer


def ask_question(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("問題不可為空。")
    rag_enabled = bool(payload.get("rag_enabled", True))
    risk = assess_question_risk(api_key, question)

    conversation_id = str(payload.get("conversation_id") or "default")
    history = load_conversation_history(conversation_id)[-MEMORY_MESSAGES:]

    if risk.diverted:
        answer = emergency_diversion_answer(question)
        save_messages(conversation_id, [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])
        return {
            "answer": answer,
            "rag_enabled": False,
            "references": [],
            "memory_messages": len(history) + 2,
            "risk_assessment": {
                "level": risk.level,
                "label": risk.label,
                "reason": risk.reason,
                "diverted": risk.diverted,
                "action": risk.action,
            },
        }

    references: list[Reference] = []
    evidence = EvidenceAssessment(
        sufficient=False,
        reason="未評估。",
        reference_count=0,
        best_distance=None,
    )
    retrieval_terms: list[str] = []
    if rag_enabled:
        retrieval_query = get_retrieval_query(api_key, question, history)
        retrieval_terms = retrieval_query.terms
        references = search_references(api_key, retrieval_query.question, retrieval_terms)
        evidence = assess_evidence(references)
    else:
        evidence = EvidenceAssessment(
            sufficient=False,
            reason="RAG 已關閉，未進行引用證據評估。",
            reference_count=0,
            best_distance=None,
        )

    try:
        answer = chat_with_gpt(api_key, question, references, history, risk, evidence, rag_enabled=rag_enabled)
    except Exception:
        raise

    save_messages(conversation_id, [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ])

    return {
        "answer": answer,
        "rag_enabled": rag_enabled,
        "references": [
            {
                "index": ref.index,
                "uuid": ref.uuid,
                "document_id": ref.document_id,
                "source_id": ref.source_id,
                "title": ref.title,
                "source": ref.source,
                "publisher": ref.publisher,
                "published_date": ref.published_date,
                "version": ref.version,
                "audience": ref.audience,
                "topic": ref.topic,
                "credibility": ref.credibility,
                "content": ref.content,
                "distance": ref.distance,
                "distance_text": "未知" if ref.distance is None else f"{ref.distance:.4f}",
            }
            for ref in references
        ],
        "evidence_assessment": {
            "sufficient": evidence.sufficient,
            "reason": evidence.reason,
            "reference_count": evidence.reference_count,
            "best_distance": evidence.best_distance,
        },
        "retrieval_terms": retrieval_terms,
        "memory_messages": len(history) + 2,
        "risk_assessment": {
            "level": risk.level,
            "label": risk.label,
            "reason": risk.reason,
            "diverted": risk.diverted,
            "action": risk.action,
        },
    }
