from typing import Any

from pydantic import BaseModel, Field


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


class AskRequest(BaseModel):
    conversation_id: str = "default"
    question: str
    rag_enabled: bool = True


class AskResponse(BaseModel):
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
