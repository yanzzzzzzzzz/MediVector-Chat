"""Stateless retrieval evaluation; never generates answers or persists chats."""
from time import perf_counter

from .config import EMBEDDING_MODEL, QUERY_EXPANSION_MODEL
from .openai_client import require_openai_api_key
from .retrieval import filter_references, get_retrieval_query, retrieve_candidates, retrieval_query_text, normalize_retrieval_terms
from .schemas import RetrievalSearchRequest


def retrieval_search(payload: RetrievalSearchRequest) -> dict:
    started = perf_counter()
    api_key = require_openai_api_key()
    question, terms = payload.question, normalize_retrieval_terms(payload.retrieval_terms)
    if payload.query_expansion:
        query = get_retrieval_query(api_key, question, [])
        question, terms = query.question, query.terms
    limit = max(payload.candidate_limit, payload.top_k)
    candidates = retrieve_candidates(api_key, question, terms, candidate_limit=limit)
    raw_ranks = {ref.uuid: ref.index for ref in candidates}
    results = candidates[:payload.top_k] if payload.mode == "raw" else filter_references(
        candidates, top_k=payload.top_k, max_distance=payload.max_distance,
        distance_margin=payload.distance_margin, dedup=payload.dedup,
    )
    return {
        "results": [
            {"document_id": ref.document_id, "chunk_id": ref.uuid, "rank": rank,
             "raw_rank": raw_ranks[ref.uuid], "distance": ref.distance,
             "content": ref.content, "title": ref.title, "source": ref.source,
             "chunk_metadata": ref.chunk_metadata}
            for rank, ref in enumerate(results, 1)
        ],
        "standalone_query": question, "terms": terms,
        "query_text": retrieval_query_text(question, terms),
        "elapsed_ms": (perf_counter() - started) * 1000,
        "settings": {
            **payload.model_dump(exclude={"question"}), "candidate_limit": limit,
            "embedding_model": EMBEDDING_MODEL,
            "query_expansion_model": QUERY_EXPANSION_MODEL if payload.query_expansion else None,
            "candidate_count": len(candidates),
        },
    }
