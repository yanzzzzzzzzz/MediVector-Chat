from typing import Any

from .chat import chat_with_gpt
from .config import MEMORY_MESSAGES
from .conversations import load_conversation_history, save_messages
from .models import EvidenceAssessment, Reference, RiskAssessment
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
    chat_history = conversation_messages_for_model(history)

    if risk.diverted:
        answer = emergency_diversion_answer(question)
        response = {
            "answer": answer,
            "rag_enabled": False,
            "references": [],
            "memory_messages": len(history) + 2,
            "risk_assessment": risk_payload(risk),
        }
        save_messages(conversation_id, [
            {"role": "user", "content": question},
            {
                "role": "assistant",
                "content": answer,
                "references": response["references"],
                "risk_assessment": response["risk_assessment"],
            },
        ])
        return response

    references: list[Reference] = []
    evidence = EvidenceAssessment(
        sufficient=False,
        reason="未評估。",
        reference_count=0,
        best_distance=None,
    )
    retrieval_terms: list[str] = []
    if rag_enabled:
        retrieval_query = get_retrieval_query(api_key, question, chat_history)
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
        answer = chat_with_gpt(api_key, question, references, chat_history, risk, evidence, rag_enabled=rag_enabled)
    except Exception:
        raise

    response = {
        "answer": answer,
        "rag_enabled": rag_enabled,
        "references": references_payload(references),
        "evidence_assessment": evidence_payload(evidence),
        "retrieval_terms": retrieval_terms,
        "memory_messages": len(history) + 2,
        "risk_assessment": risk_payload(risk),
    }

    save_messages(conversation_id, [
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": answer,
            "references": response["references"],
            "evidence_assessment": response["evidence_assessment"],
            "retrieval_terms": response["retrieval_terms"],
            "risk_assessment": response["risk_assessment"],
        },
    ])

    return response


def conversation_messages_for_model(history: list[dict]) -> list[dict[str, str]]:
    return [
        {"role": str(message.get("role") or ""), "content": str(message.get("content") or "")}
        for message in history
        if str(message.get("role") or "") in {"user", "assistant"}
    ]


def references_payload(references: list[Reference]) -> list[dict[str, Any]]:
    return [
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
    ]


def evidence_payload(evidence: EvidenceAssessment) -> dict[str, Any]:
    return {
        "sufficient": evidence.sufficient,
        "reason": evidence.reason,
        "reference_count": evidence.reference_count,
        "best_distance": evidence.best_distance,
    }


def risk_payload(risk: RiskAssessment) -> dict[str, Any]:
    return {
        "level": risk.level,
        "label": risk.label,
        "reason": risk.reason,
        "diverted": risk.diverted,
        "action": risk.action,
    }
