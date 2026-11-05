from uuid import UUID
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import json
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


@router.post("/versions/pdf", status_code=201)
async def create_pdf_version(metadata: str = Form(...), file: UploadFile = File(...)):
    knowledge.organization_principal({"admin", "nurse", "reviewer"})
    data = await file.read(8 * 1024 * 1024 + 1)
    try:
        fields = json.loads(metadata)
        if not isinstance(fields, dict):
            raise ValueError()
    except (ValueError, TypeError):
        raise knowledge.KnowledgeError("metadata must be a JSON object")
    try:
        return knowledge.create_pdf_version(fields, data, file.filename or "")
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.get("/versions/{version_id}/attachment")
def attachment(version_id: UUID, chunk_id: UUID | None = None,
               branch_id: str | None = None, department_id: str | None = None):
    data, sha = knowledge.source_attachment(version_id, chunk_id=chunk_id, branch_id=branch_id, department_id=department_id)
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{version_id}.pdf"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Source-SHA256": sha,
        "Content-Security-Policy": "sandbox"})


@router.get("/query-traces/{trace_id}")
def query_trace(trace_id: UUID):
    from .quality_audit import get_trace
    return get_trace(trace_id)


@router.get('/query-traces')
def query_traces(conversation_id: UUID):
    from .quality_audit import list_traces
    return {'traces': list_traces(conversation_id)}
