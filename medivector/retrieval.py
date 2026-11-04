from dataclasses import replace
import json
import re

from .config import (
    MAX_EVIDENCE_DISTANCE,
    MAX_REFERENCE_DISTANCE,
    MIN_REFERENCE_COUNT,
    QUERY_EXPANSION_MODEL,
    REFERENCE_CANDIDATE_LIMIT,
    REFERENCE_DISTANCE_MARGIN,
    TOP_K,
)
from .db import db_connection
from .models import EvidenceAssessment, Reference, RetrievalQuery
from .openai_client import embed_texts, openai_post


def normalize_retrieval_terms(terms: list[str]) -> list[str]:
    normalized_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms:
        cleaned_term = re.sub(r"\s+", " ", str(term or "").strip())
        if not cleaned_term:
            continue
        lowered_term = cleaned_term.lower()
        if lowered_term in seen_terms:
            continue
        seen_terms.add(lowered_term)
        normalized_terms.append(cleaned_term)
    return normalized_terms

def generate_retrieval_query(api_key: str, question: str, history: list[dict[str, str]]) -> RetrievalQuery:
    recent_user_turns = [
        str(message.get("content") or "").strip()
        for message in history[-6:]
        if str(message.get("role") or "") == "user" and str(message.get("content") or "").strip()
    ]
    conversation_context = "\n".join(f"- {turn}" for turn in recent_user_turns)

    schema = {
        "name": "retrieval_query_contextualization",
        "schema": {
            "type": "object",
            "properties": {
                "needs_context": {"type": "boolean"},
                "standalone_question": {"type": "string"},
                "terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 8,
                },
            },
            "required": ["needs_context", "standalone_question", "terms"],
            "additionalProperties": False,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是醫療 RAG 檢索查詢改寫器。"
                "規則：\n"
                "1. 先判斷當前問題是否必須參考最近對話才能理解，並輸出 needs_context。\n"
                "2. 如果當前問題已明確包含症狀、疾病、解剖部位、檢查、治療或藥物，通常視為新檢索主題，不要把最近對話中的其他主題加入 standalone_question 或 terms。\n"
                "3. 只有當問題是語意不完整的追問時，才使用最近對話補全 standalone_question。\n"
                "4. standalone_question 必須是可獨立拿去向量檢索的完整問題；不可加入當前問題與必要上下文以外的主題。\n"
                "5. terms 必須根據 standalone_question 產生，必須保留其中所有解剖部位、症狀、疾病名稱。\n"
                "6. 每個中文關鍵詞都必須同時加上對應的英文同義詞或醫學術語（例如：鼠蹊部→groin inguinal，發燒→fever pyrexia）。\n"
                "7. 可追加相關症狀、病因、治療方式的中英詞，但不要偏離 standalone_question。\n"
                "8. 不要寫完整句子，詞組需簡短，適合直接拼接到向量檢索查詢中。\n"
                "9. 避免重複、避免與問題無關的泛用詞或歷史對話主題。\n"
                "只輸出符合 schema 的 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"使用者當前問題：{question}\n\n"
                f"最近對話內容：\n{conversation_context or '- 無'}\n\n"
                "請輸出 needs_context、standalone_question，並依 standalone_question 產生 3 到 8 組中英文檢索詞。"
            ),
        },
    ]

    try:
        data = openai_post(
            api_key,
            "/chat/completions",
            {
                "model": QUERY_EXPANSION_MODEL,
                "temperature": 0.2,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": schema,
                },
            },
        )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        standalone_question = str(parsed.get("standalone_question") or "").strip() or question
        terms = normalize_retrieval_terms([str(term) for term in parsed.get("terms") or []])
        return RetrievalQuery(
            question=standalone_question,
            terms=terms[:8],
            needs_context=bool(parsed.get("needs_context")),
        )
    except Exception:
        return RetrievalQuery(question=question, terms=[], needs_context=False)


def get_retrieval_query(
    api_key: str,
    question: str,
    history: list[dict[str, str]],
) -> RetrievalQuery:
    return generate_retrieval_query(api_key, question, history)

def retrieval_query_text(question: str, retrieval_terms: list[str] | None = None) -> str:
    normalized_terms = normalize_retrieval_terms(retrieval_terms or [])
    if not normalized_terms:
        return question
    return f"{question}\n\n檢索關鍵詞：{' '.join(normalized_terms)}"

def retrieve_candidates(
    api_key: str,
    question: str,
    retrieval_terms: list[str] | None = None,
    *,
    candidate_limit: int = REFERENCE_CANDIDATE_LIMIT,
) -> list[Reference]:
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    question_vector = embed_texts(api_key, [retrieval_query_text(question, retrieval_terms)])[0]
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, document_id, source_id, title, source,
                       publisher, published_date, version, audience, topic, credibility,
                       content, embedding OPERATOR(public.<=>) %s::public.vector AS distance, chunk_metadata
                FROM articles
                ORDER BY distance
                LIMIT %s
                """,
                (question_vector, candidate_limit),
            )
            rows = cur.fetchall()
    return [
        Reference(
            index=rank, uuid=str(row[0]), document_id=str(row[1]),
            source_id=int(row[2] or 0), title=str(row[3] or ""),
            source=str(row[4] or ""), publisher=str(row[5] or ""),
            published_date=str(row[6] or ""), version=str(row[7] or ""),
            audience=str(row[8] or ""), topic=str(row[9] or ""),
            credibility=str(row[10] or ""), content=str(row[11] or ""),
            distance=float(row[12]) if row[12] is not None else None,
            chunk_metadata=row[13] or {},
        )
        for rank, row in enumerate(rows, 1)
    ]


def filter_references(
    candidates: list[Reference],
    *,
    top_k: int = TOP_K,
    max_distance: float = MAX_REFERENCE_DISTANCE,
    distance_margin: float = REFERENCE_DISTANCE_MARGIN,
    dedup: bool = True,
) -> list[Reference]:
    if top_k < 1 or max_distance < 0 or distance_margin < 0:
        raise ValueError("Invalid retrieval limits")
    ordered = sorted(candidates, key=lambda ref: (
        ref.distance is None, ref.distance if ref.distance is not None else 0, ref.index,
    ))
    distances = [ref.distance for ref in ordered if ref.distance is not None]
    cutoff = min(max_distance, min(distances) + distance_margin) if distances else max_distance
    references: list[Reference] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in ordered:
        if ref.distance is not None and ref.distance > cutoff:
            continue
        key = (ref.title, ref.source, ref.content)
        if dedup and key in seen:
            continue
        seen.add(key)
        references.append(replace(ref, index=len(references) + 1))
        if len(references) >= top_k:
            break
    return references


def search_references(
    api_key: str,
    question: str,
    retrieval_terms: list[str] | None = None,
    *,
    top_k: int = TOP_K,
    candidate_limit: int = REFERENCE_CANDIDATE_LIMIT,
    max_distance: float = MAX_REFERENCE_DISTANCE,
    distance_margin: float = REFERENCE_DISTANCE_MARGIN,
    dedup: bool = True,
) -> list[Reference]:
    return filter_references(
        retrieve_candidates(api_key, question, retrieval_terms,
                            candidate_limit=max(candidate_limit, top_k)),
        top_k=top_k, max_distance=max_distance, distance_margin=distance_margin, dedup=dedup,
    )


def assess_evidence(references: list[Reference]) -> EvidenceAssessment:
    if not references:
        return EvidenceAssessment(
            sufficient=False,
            reason="沒有找到可用參考資料。",
            reference_count=0,
            best_distance=None,
        )

    distances = [ref.distance for ref in references if ref.distance is not None]
    best_distance = min(distances) if distances else None
    if len(references) < MIN_REFERENCE_COUNT:
        return EvidenceAssessment(
            sufficient=False,
            reason=f"參考資料不足，只有 {len(references)} 筆。",
            reference_count=len(references),
            best_distance=best_distance,
        )

    if best_distance is not None and best_distance > MAX_EVIDENCE_DISTANCE:
        return EvidenceAssessment(
            sufficient=False,
            reason=f"最佳參考距離過高（{best_distance:.4f}），證據偏弱。",
            reference_count=len(references),
            best_distance=best_distance,
        )

    return EvidenceAssessment(
        sufficient=True,
        reason="參考資料數量與距離達到門檻。",
        reference_count=len(references),
        best_distance=best_distance,
    )
