import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from .config import FRONTEND_DIST_DIR
from .conversations import delete_conversation, list_conversations, load_conversation_history
from .db import init_db
from .documents import add_documents, delete_document, infer_document_metadata, list_documents, update_document
from .qa import ask_question
from .schemas import (
    AddDocumentsResponse,
    AskRequest,
    AskResponse,
    ConversationMessagesResponse,
    ConversationsResponse,
    DeleteConversationResponse,
    DeleteDocumentResponse,
    DocumentMutationResponse,
    DocumentsResponse,
    MetadataSuggestionsResponse,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="MediVector API", lifespan=lifespan)


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(json.JSONDecodeError)
async def json_error_handler(_request: Request, exc: json.JSONDecodeError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(Exception)
async def exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/documents", response_model=DocumentsResponse)
def get_documents(q: str = "", date_from: str = "", date_to: str = "") -> dict[str, Any]:
    return {"documents": list_documents(q=q, date_from=date_from, date_to=date_to)}


@app.post("/api/documents/metadata-suggestions", response_model=MetadataSuggestionsResponse)
async def post_metadata_suggestions(request: Request) -> dict[str, Any]:
    return {"metadata": infer_document_metadata(await read_document_payload(request))}


@app.post("/api/documents", response_model=AddDocumentsResponse, status_code=201)
async def post_documents(request: Request) -> dict[str, Any]:
    inserted_documents = add_documents(await read_document_payload(request))
    return {
        "inserted": inserted_documents,
        "document": inserted_documents[0],
        "documents": list_documents(),
    }


@app.put("/api/documents/{document_id}", response_model=DocumentMutationResponse)
async def put_document(document_id: str, request: Request) -> dict[str, Any]:
    document = update_document(document_id, await read_document_payload(request))
    return {"document": document, "documents": list_documents()}


@app.delete("/api/documents/{document_id}", response_model=DeleteDocumentResponse)
def delete_document_route(document_id: str) -> dict[str, Any]:
    return delete_document(document_id)


@app.post("/api/ask", response_model=AskResponse)
def post_ask(payload: AskRequest) -> dict[str, Any]:
    return ask_question(payload.model_dump())


@app.get("/api/conversations", response_model=ConversationsResponse)
def get_conversations() -> dict[str, Any]:
    return {"conversations": list_conversations()}


@app.get("/api/conversations/{conversation_id}", response_model=ConversationMessagesResponse)
def get_conversation_messages(conversation_id: str) -> dict[str, Any]:
    return {"messages": load_conversation_history(conversation_id)}


@app.delete("/api/conversations/{conversation_id}", response_model=DeleteConversationResponse)
def delete_conversation_route(conversation_id: str) -> dict[str, bool]:
    delete_conversation(conversation_id)
    return {"deleted": True}


@app.api_route("/api/{request_path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
def api_not_found(_request_path: str) -> JSONResponse:
    return JSONResponse({"error": "找不到路徑。"}, status_code=404)


@app.get("/{request_path:path}", include_in_schema=False, response_model=None)
def serve_static(request_path: str) -> FileResponse | JSONResponse:
    target = resolve_static_target(request_path)
    if target is None:
        return JSONResponse(
            {"error": "前端尚未 build。開發時請在 frontend\\medivector-chat-app 執行 npm run dev。"},
            status_code=404,
        )
    return FileResponse(target)


async def read_document_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("Content-Type", "")
    if content_type.lower().startswith("multipart/form-data"):
        return await read_multipart_form(request)

    body = await request.body()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


async def read_multipart_form(request: Request) -> dict[str, Any]:
    form = await request.form()
    payload: dict[str, Any] = {}
    uploads: list[dict[str, Any]] = []

    for name, value in form.multi_items():
        if is_upload_file(value):
            upload = await upload_to_payload(value)
            uploads.append(upload)
            payload["upload"] = upload
            continue
        payload[str(name)] = str(value)

    if uploads:
        payload["uploads"] = uploads
    return payload


def is_upload_file(value: Any) -> bool:
    return isinstance(value, (UploadFile, StarletteUploadFile))


async def upload_to_payload(upload_file: UploadFile | StarletteUploadFile) -> dict[str, Any]:
    return {
        "filename": upload_file.filename or "",
        "content_type": upload_file.content_type or "application/octet-stream",
        "data": await upload_file.read(),
    }


def resolve_static_target(request_path: str) -> Path | None:
    if not FRONTEND_DIST_DIR.exists():
        return None

    relative_path = request_path.lstrip("/") or "index.html"
    target = (FRONTEND_DIST_DIR / relative_path).resolve()
    dist_root = FRONTEND_DIST_DIR.resolve()
    try:
        target.relative_to(dist_root)
    except ValueError:
        return dist_root / "index.html"

    if not target.is_file():
        target = dist_root / "index.html"
    return target if target.is_file() else None


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    reload = "--reload" in sys.argv or os.getenv("RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run("medivector.server:app", host=host, port=port, reload=reload)
