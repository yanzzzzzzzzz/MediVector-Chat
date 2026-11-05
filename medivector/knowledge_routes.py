from uuid import UUID
from fastapi import APIRouter
from . import knowledge
from .knowledge_schemas import CatalogEntry, CreateVersion, IndexRequest, TransitionRequest

router = APIRouter(prefix="/api/knowledge", tags=["Institutional knowledge"])


@router.get("/catalog")
def catalog():
    return knowledge.catalog()


@router.put("/catalog/branches")
def branch(payload: CatalogEntry):
    return knowledge.upsert_catalog("branches", payload)


@router.put("/catalog/departments")
def department(payload: CatalogEntry):
    return knowledge.upsert_catalog("departments", payload)


@router.post("/versions", status_code=201)
def create_version(payload: CreateVersion):
    return knowledge.create_version(payload)


@router.get("/versions")
def versions(document_id: UUID | None = None):
    return {"versions": knowledge.list_versions(document_id)}


@router.get("/versions/{version_id}")
def version(version_id: UUID):
    return knowledge.get_version(version_id)


@router.post("/versions/{version_id}/transition")
def transition(version_id: UUID, payload: TransitionRequest):
    return knowledge.transition(version_id, payload)


@router.get("/documents/{document_id}/history")
def history(document_id: UUID):
    return {"events": knowledge.history(document_id)}


@router.get("/chunks/{chunk_id}")
def citation_chunk(chunk_id: UUID, branch_id: str, department_id: str):
    return knowledge.citation_chunk(chunk_id, branch_id, department_id)


@router.get("/corpus-manifest")
def corpus_manifest(branch_id: str, department_id: str):
    return knowledge.corpus_manifest(branch_id, department_id)


@router.post("/versions/{version_id}/index")
def index_version(version_id: UUID, payload: IndexRequest):
    return knowledge.index_version(version_id, payload.reason)
