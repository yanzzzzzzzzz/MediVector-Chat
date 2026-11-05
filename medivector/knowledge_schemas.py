from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Scope(StrictRequest):
    branch_id: str = Field(min_length=1, max_length=128)
    department_id: str = Field(min_length=1, max_length=128)


class CatalogEntry(StrictRequest):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)


class CreateVersion(StrictRequest):
    document_id: UUID | None = None
    version_label: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=500)
    source_url: str = Field(default="", max_length=2000)
    license: str = Field(min_length=1, max_length=2000)
    audience: str = Field(default="", max_length=500)
    content: str = Field(min_length=1, max_length=200000)
    scopes: list[Scope] = Field(min_length=1, max_length=100)
    effective_from: AwareDatetime
    effective_until: AwareDatetime | None = None
    change_reason: str = Field(min_length=1, max_length=2000)
    allowed_roles: list[Literal["admin", "reviewer", "nurse", "user"]] = Field(default_factory=lambda: ["admin", "reviewer", "nurse", "user"], min_length=1)
    allowed_users: list[str] = Field(default_factory=list, max_length=100)
    chunk_strategy: Literal["baseline", "token"] = "token"
    max_tokens: int = Field(default=512, ge=4, le=6000)
    overlap_tokens: int = Field(default=64, ge=0, le=3000)

    @field_validator("source_url")
    @classmethod
    def valid_source_url(cls, value):
        from urllib.parse import urlsplit
        if value and (urlsplit(value).scheme not in {"http", "https"} or not urlsplit(value).hostname):
            raise ValueError("Source URL must use HTTP or HTTPS")
        return value

    @field_validator("content")
    @classmethod
    def nonempty_content(cls, value):
        if not value.strip():
            raise ValueError("Content must not be blank")
        return value

    @model_validator(mode="after")
    def valid_configuration(self):
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("effective_until must follow effective_from")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        return self


class TransitionRequest(StrictRequest):
    action: Literal["submit", "approve", "return", "withdraw"]
    reason: str = Field(min_length=1, max_length=2000)


class IndexRequest(StrictRequest):
    reason: str = Field(min_length=1, max_length=2000)
