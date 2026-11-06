from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from .config import TOP_K, REFERENCE_CANDIDATE_LIMIT, MAX_REFERENCE_DISTANCE, REFERENCE_DISTANCE_MARGIN


class EmbeddingSchema(BaseModel):
    dimension: int = 0
    preview: list[float] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)


class DocumentItemSchema(BaseModel):
    uuid: str
    document_id: str
    source_id: int | str
    title: str
    source: str
    publisher: str = ""
    published_date: str = ""
    version: str = ""
    audience: str = ""
    topic: str = ""
    credibility: str = ""
    content: str
    file_name: str = ""
    file_object_key: str = ""
    file_bucket: str = ""
    file_content_type: str = ""
    file_size: int = 0
    chunk_index: int = 1
    chunk_count: int = 1
    created_at: str = ""
    updated_at: str = ""
    embedding: EmbeddingSchema = Field(default_factory=EmbeddingSchema)


class DocumentsResponse(BaseModel):
    documents: list[DocumentItemSchema]


class DocumentMutationResponse(BaseModel):
    document: DocumentItemSchema
    documents: list[DocumentItemSchema]


class AddDocumentsResponse(DocumentMutationResponse):
    inserted: list[dict[str, Any]]


class DeleteDocumentResponse(BaseModel):
    deleted: bool
    deleted_count: int


class MetadataSuggestionsSchema(BaseModel):
    title: str = ""
    published_date: str = ""
    audience: str = ""
    topic: str = ""


class MetadataSuggestionsResponse(BaseModel):
    metadata: MetadataSuggestionsSchema


class ReferenceItemSchema(BaseModel):
    document_version_id: str | None = None
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)
    index: int
    uuid: str
    document_id: str
    source_id: int
    title: str
    source: str
    publisher: str = ""
    published_date: str = ""
    version: str = ""
    audience: str = ""
    topic: str = ""
    credibility: str = ""
    content: str
    distance: float | None = None
    distance_text: str


class EvidenceAssessmentSchema(BaseModel):
    sufficient: bool
    reason: str
    reference_count: int
    best_distance: float | None = None


class RiskAssessmentSchema(BaseModel):
    level: str
    label: str
    reason: str
    diverted: bool
    action: str


class SourceSupportAssessmentSchema(BaseModel):
    status: Literal["sufficient", "partial", "insufficient", "uncertain"]
    estimated_answerable: bool
    model: str | None = None
    human_reviewed: Literal[False] = False
    semantic_support_verified: Literal[False] = False
    reason: str | None = None
    elapsed_ms: float | None = None
    usage: dict[str, int] | None = None


class AskRequest(BaseModel):
    branch_id: str | None = None
    department_id: str | None = None
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    rag_enabled: bool = True

    @field_validator("conversation_id")
    @classmethod
    def valid_conversation_id(cls, value: str) -> str:
        try:
            return str(UUID(value))
        except ValueError:
            raise ValueError("conversation_id 必須是有效的 UUID。") from None


class AskResponse(BaseModel):
    source_support_assessment: SourceSupportAssessmentSchema | None = None
    query_trace_id: str | None = None
    applied_filters: dict[str, Any] | None = None
    answer: str
    rag_enabled: bool
    references: list[ReferenceItemSchema] = Field(default_factory=list)
    evidence_assessment: EvidenceAssessmentSchema | None = None
    retrieval_terms: list[str] = Field(default_factory=list)
    memory_messages: int
    risk_assessment: RiskAssessmentSchema | None = None


class ConversationItemSchema(BaseModel):
    id: str
    title: str
    created_at: str


class ConversationsResponse(BaseModel):
    conversations: list[ConversationItemSchema]


class MessageItemSchema(BaseModel):
    query_trace_id: str | None = None
    applied_filters: dict[str, Any] | None = None
    created_at: str | None = None
    source_support_assessment: SourceSupportAssessmentSchema | None = None
    role: str
    content: str
    references: list[ReferenceItemSchema] = Field(default_factory=list)
    evidence_assessment: EvidenceAssessmentSchema | None = None
    retrieval_terms: list[str] = Field(default_factory=list)
    risk_assessment: RiskAssessmentSchema | None = None


class ConversationMessagesResponse(BaseModel):
    messages: list[MessageItemSchema]


class DeleteConversationResponse(BaseModel):
    deleted: bool


class RetrievalSearchRequest(BaseModel):
    branch_id: str | None = None
    department_id: str | None = None
    question: str = Field(min_length=1, max_length=20000)
    top_k: int = Field(default=TOP_K, ge=1, le=1000)
    candidate_limit: int = Field(default=REFERENCE_CANDIDATE_LIMIT, ge=1, le=1000)
    mode: Literal["raw", "filtered"] = "filtered"
    query_expansion: bool = False
    retrieval_terms: list[str] = Field(default_factory=list, max_length=8)
    max_distance: float = Field(default=MAX_REFERENCE_DISTANCE, ge=0, le=2, allow_inf_nan=False)
    distance_margin: float = Field(default=REFERENCE_DISTANCE_MARGIN, ge=0, le=2, allow_inf_nan=False)
    dedup: bool = True

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("問題不可為空。")
        return value


class RetrievalResultSchema(BaseModel):
    document_version_id: str | None = None
    version: str = ""
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)
    document_id: str
    chunk_id: str
    rank: int
    raw_rank: int
    distance: float | None
    content: str
    title: str
    source: str


class RetrievalSearchResponse(BaseModel):
    results: list[RetrievalResultSchema]
    standalone_query: str
    terms: list[str]
    query_text: str
    elapsed_ms: float
    settings: dict[str, Any]
