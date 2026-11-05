from typing import Literal
from uuid import UUID
from pydantic import Field
from .knowledge_schemas import StrictRequest


class GenerateDraft(StrictRequest):
    branch_id: str = Field(min_length=1, max_length=128)
    department_id: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=500)
    version_ids: list[UUID] = Field(min_length=1, max_length=10)


class EditDraft(StrictRequest):
    expected_revision: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=100000)
    reason: str = Field(min_length=1, max_length=2000)


class DraftTransition(StrictRequest):
    expected_revision: int = Field(ge=1)
    action: Literal['submit', 'return', 'approve', 'withdraw']
    reason: str = Field(min_length=1, max_length=2000)


class SourceFeedback(StrictRequest):
    version_id: UUID
    conversation_id: UUID | None = None
    category: Literal['inappropriate_answer', 'outdated_source', 'other']
    reason: str = Field(min_length=1, max_length=2000)
