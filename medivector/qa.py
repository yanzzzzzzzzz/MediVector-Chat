from typing import Any
import time

from .chat import chat_with_gpt
from .config import MEMORY_MESSAGES, SOURCE_SUPPORT_CHECK_ENABLED
from .source_support import assess_source_support
from .conversations import load_conversation_history, save_messages
from .models import EvidenceAssessment, Reference, RiskAssessment
from .openai_client import require_openai_api_key
from .retrieval import assess_evidence, get_retrieval_query, search_references
from .retrieval_context import context_for_request
from .knowledge import KnowledgeError
from .risk import assess_question_risk, emergency_diversion_answer


def ask_question(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    context = context_for_request(payload.get("branch_id"), payload.get("department_id"))
    if context and not payload.get("rag_enabled", True):
        raise KnowledgeError("Institutional answers require approved retrieval evidence")
    from .quality_audit import query_snapshot, record_query
    snapshot = query_snapshot(context) if context else None
    api_key = require_openai_api_key()
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("問題不可為空。")
    rag_enabled = bool(payload.get("rag_enabled", True))
    risk = (RiskAssessment("green", "未做臨床分診", "僅供院所核准衛教資訊查詢。", False, "不提供診斷或個人化診療。")
            if context else assess_question_risk(api_key, question))

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
    support_question = question
    if rag_enabled:
        retrieval_query = get_retrieval_query(api_key, question, chat_history)
        support_question = retrieval_query.question
        retrieval_terms = retrieval_query.terms
        references = search_references(api_key, retrieval_query.question, retrieval_terms, **({"context": context} if context else {}))
        evidence = assess_evidence(references)
    else:
        evidence = EvidenceAssessment(
            sufficient=False,
            reason="RAG 已關閉，未進行引用證據評估。",
            reference_count=0,
            best_distance=None,
        )

    source_support = None
    if context and SOURCE_SUPPORT_CHECK_ENABLED:
        try:
            estimate = assess_source_support(api_key, support_question,
                [{"chunk_id": ref.uuid, "content": ref.content} for ref in references])
        except ValueError:
            estimate = {"status": "uncertain", "estimated_answerable": False,
                        "human_reviewed": False, "semantic_support_verified": False,
                        "reason": "input_budget_or_structure", "supporting_chunk_ids": []}
        # Persist only a summary, never a second copy of source quotes or model requirements.
        source_support = {key: estimate[key] for key in (
            "status", "estimated_answerable", "model", "human_reviewed", "semantic_support_verified",
            "reason", "elapsed_ms", "usage") if key in estimate}
        if estimate["estimated_answerable"]:
            supported_ids = set(estimate["supporting_chunk_ids"])
            references = [ref for ref in references if ref.uuid in supported_ids]
            if not references:
                source_support.update(status="uncertain", estimated_answerable=False, reason="no_supported_chunks")
            evidence = assess_evidence(references)
        if not source_support["estimated_answerable"]:
            evidence = EvidenceAssessment(False, "來源可回答性估計未通過；現有原文不足或無法確認。",
                                          len(references), evidence.best_distance)

    answer_model_invoked = False
    try:
        if context and not references:
            answer = "目前沒有符合此院區、科別且已核准有效的參考資料，無法確認院所規範。請向院方專業人員確認。"
        elif source_support and not source_support["estimated_answerable"]:
            answer = "目前找到的核准文件未提供足以確認此問題的資訊，無法確認院所規範。請向文件負責人確認。"
        else:
            answer_model_invoked = True
            answer = chat_with_gpt(api_key, question, references, chat_history, risk, evidence,
                                   rag_enabled=rag_enabled, **({"institutional": True} if context else {}))
    except Exception:
        raise

    response = {
        "answer": answer,
        "applied_filters": context.payload() if context else None,
        "rag_enabled": rag_enabled,
        "references": references_payload(references),
        "evidence_assessment": evidence_payload(evidence),
        "retrieval_terms": retrieval_terms,
        "memory_messages": len(history) + 2,
        "risk_assessment": risk_payload(risk),
    }
    if source_support is not None:
        response["source_support_assessment"] = source_support
        if snapshot is not None:
            snapshot = {**snapshot, "answer_model_invoked": answer_model_invoked,
                        "source_support_assessment": source_support}

    new_messages = [
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": answer,
            "references": response["references"],
            "evidence_assessment": response["evidence_assessment"],
            "retrieval_terms": response["retrieval_terms"],
            "risk_assessment": response["risk_assessment"],
        },
    ]
    if source_support is not None:
        new_messages[1]["source_support_assessment"] = source_support
    if context:
        response["query_trace_id"] = save_messages(conversation_id, new_messages, on_saved=lambda conn: record_query(
            context, conversation_id, question, response, snapshot, (time.monotonic() - started) * 1000, conn=conn))
    else:
        save_messages(conversation_id, new_messages)
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
            "document_version_id": ref.chunk_metadata.get("version_id"),
            "chunk_metadata": ref.chunk_metadata,
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
