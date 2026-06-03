from dataclasses import dataclass


@dataclass
class Reference:
    index: int
    uuid: str
    document_id: str
    source_id: int
    title: str
    source: str
    publisher: str
    published_date: str
    version: str
    audience: str
    topic: str
    credibility: str
    content: str
    distance: float | None


@dataclass
class EvidenceAssessment:
    sufficient: bool
    reason: str
    reference_count: int
    best_distance: float | None


@dataclass
class RiskAssessment:
    level: str
    label: str
    reason: str
    diverted: bool
    action: str


@dataclass
class RetrievalQuery:
    question: str
    terms: list[str]
    needs_context: bool
