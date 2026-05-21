import json
import mimetypes
import os
import re
import sys
import time
import traceback
import uuid as uuidlib
from email import policy
from email.parser import BytesParser
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import MetadataQuery


COLLECTION_NAME = "Article"
FRONTEND_DIST_DIR = Path(__file__).with_name("frontend") / "medivector-chat-app" / "dist"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
TOP_K = int(os.getenv("TOP_K", "5"))
REFERENCE_CANDIDATE_LIMIT = int(os.getenv("REFERENCE_CANDIDATE_LIMIT", "20"))
MAX_REFERENCE_DISTANCE = float(os.getenv("MAX_REFERENCE_DISTANCE", "0.65"))
REFERENCE_DISTANCE_MARGIN = float(os.getenv("REFERENCE_DISTANCE_MARGIN", "0.12"))
MEMORY_MESSAGES = int(os.getenv("MEMORY_MESSAGES", "10"))
MAX_EMBEDDING_CHARS = int(os.getenv("MAX_EMBEDDING_CHARS", "6000"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "health-education-files")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "127.0.0.1")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", "8080"))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))


CONVERSATIONS: dict[str, list[dict[str, str]]] = {}


RETRIEVAL_QUERY_EXPANSIONS = {
    "鼠蹊": "groin inguinal",
    "腹股溝": "groin inguinal",
    "運動員": "athlete athletes athletic sports",
    "疼痛": "pain",
    "神經": "nerve neural neurological ilioinguinal iliohypogastric genitofemoral obturator pudendal femoral",
    "復健": "rehabilitation physical therapy conservative treatment",
    "保守治療": "conservative treatment non-surgical management",
    "肌腱": "tendon tendinopathy",
    "內收肌": "adductor",
}

@dataclass
class Reference:
    index: int
    uuid: str
    source_id: int
    title: str
    source: str
    content: str
    distance: float | None


def require_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("請先設定 OPENAI_API_KEY，才能新增 embedding 或詢問 GPT。")
    return api_key


def openai_post(api_key: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = httpx.post(
            f"{OPENAI_BASE_URL}{path}",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"OpenAI API 回傳錯誤 {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"無法連線到 OpenAI API: {exc}") from exc
    return response.json()


def embed_texts(api_key: str, texts: list[str]) -> list[list[float]]:
    data = openai_post(api_key, "/embeddings", {"model": EMBEDDING_MODEL, "input": texts})
    return [item["embedding"] for item in data["data"]]


def document_embedding_text(document: dict[str, Any]) -> str:
    return f"標題：{document['title']}\n來源：{document['source']}\n內容：{document['content']}"


def retrieval_query_text(question: str) -> str:
    expansions = [
        expansion
        for keyword, expansion in RETRIEVAL_QUERY_EXPANSIONS.items()
        if keyword in question
    ]
    if not expansions:
        return question
    return f"{question}\n\n檢索關鍵詞：{' '.join(expansions)}"


def required_reference_term_groups(question: str) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = []
    if "鼠蹊" in question or "腹股溝" in question:
        groups.append(("鼠蹊", "腹股溝", "groin", "inguinal"))
    if "神經" in question:
        groups.append(
            (
                "神經",
                "nerve",
                "neural",
                "neurolog",
                "ilioinguinal",
                "iliohypogastric",
                "genitofemoral",
                "obturator",
                "pudendal",
                "femoral",
            )
        )
    return groups


def reference_matches_required_terms(props: dict[str, Any], groups: list[tuple[str, ...]]) -> bool:
    if not groups:
        return True
    haystack = " ".join(
        str(props.get(key) or "")
        for key in ("title", "source", "content", "file_name")
    ).lower()
    return all(any(term.lower() in haystack for term in group) for group in groups)


def split_text_for_embedding(text: str, max_chars: int = MAX_EMBEDDING_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", text) if paragraph.strip()]

    for paragraph in paragraphs:
        pieces = [paragraph[index : index + max_chars] for index in range(0, len(paragraph), max_chars)]
        for piece in pieces:
            if not current:
                current = piece
                continue
            if len(current) + len(piece) + 2 <= max_chars:
                current = f"{current}\n\n{piece}"
                continue
            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)
    return chunks


def decode_text_file(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return file_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace").strip()


def extract_pdf_text(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 pypdf 套件，請先執行 pip install -r requirements.txt。") from exc

    reader = PdfReader(BytesIO(file_bytes))
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(text for text in page_texts if text).strip()


def extract_upload_text(upload: dict[str, Any]) -> str:
    filename = str(upload.get("filename") or "").strip()
    file_bytes = upload.get("data") or b""
    if not filename or not file_bytes:
        return ""

    extension = os.path.splitext(filename.lower())[1]
    if extension == ".txt":
        text = decode_text_file(file_bytes)
    elif extension == ".pdf":
        text = extract_pdf_text(file_bytes)
    else:
        raise ValueError("只支援上傳 TXT 或 PDF 檔案。")

    if not text:
        raise ValueError(f"{filename} 沒有可匯入的文字內容。若是掃描版 PDF，請先轉成可複製文字的 PDF 或 TXT。")
    return text


def sanitize_filename(filename: str) -> str:
    basename = os.path.basename(filename).strip() or "upload"
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", basename)
    return sanitized.strip("._") or "upload"


def connect_minio_client() -> Any:
    try:
        from minio import Minio
    except ImportError as exc:
        raise RuntimeError("缺少 minio 套件，請先執行 pip install -r requirements.txt。") from exc

    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def ensure_minio_bucket(minio_client: Any) -> None:
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)


def save_upload_to_minio(upload: dict[str, Any], source_id: int) -> dict[str, Any]:
    filename = str(upload.get("filename") or "").strip()
    file_bytes = upload.get("data") or b""
    if not filename or not file_bytes:
        return {}

    safe_filename = sanitize_filename(filename)
    object_key = f"health-info/{source_id}/{int(time.time())}-{uuidlib.uuid4().hex}-{safe_filename}"
    content_type = str(upload.get("content_type") or "application/octet-stream")
    minio_client = connect_minio_client()
    ensure_minio_bucket(minio_client)
    minio_client.put_object(
        MINIO_BUCKET,
        object_key,
        BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=content_type,
    )
    return {
        "file_name": filename,
        "file_object_key": object_key,
        "file_bucket": MINIO_BUCKET,
        "file_content_type": content_type,
        "file_size": len(file_bytes),
    }


def delete_minio_object(file_bucket: str, file_object_key: str) -> None:
    if not file_bucket or not file_object_key:
        return
    try:
        connect_minio_client().remove_object(file_bucket, file_object_key)
    except Exception:
        traceback.print_exc()


def flatten_vector(vector_payload: Any) -> list[float]:
    if isinstance(vector_payload, dict):
        vector_payload = next(
            (value for value in vector_payload.values() if isinstance(value, list)),
            [],
        )
    if not isinstance(vector_payload, list):
        return []
    if vector_payload and isinstance(vector_payload[0], list):
        vector_payload = vector_payload[0]
    return [float(value) for value in vector_payload]


def serialize_embedding(vector_payload: Any) -> dict[str, Any]:
    vector = flatten_vector(vector_payload)
    rounded = [round(value, 6) for value in vector]
    return {
        "dimension": len(rounded),
        "preview": rounded[:12],
        "values": rounded,
    }


def connect_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_local(
        host=WEAVIATE_HOST,
        port=WEAVIATE_PORT,
        grpc_port=WEAVIATE_GRPC_PORT,
    )


def article_properties() -> list[Property]:
    return [
        Property(name="source_id", data_type=DataType.INT),
        Property(name="title", data_type=DataType.TEXT),
        Property(name="source", data_type=DataType.TEXT),
        Property(name="content", data_type=DataType.TEXT),
        Property(name="file_name", data_type=DataType.TEXT),
        Property(name="file_object_key", data_type=DataType.TEXT),
        Property(name="file_bucket", data_type=DataType.TEXT),
        Property(name="file_content_type", data_type=DataType.TEXT),
        Property(name="file_size", data_type=DataType.INT),
        Property(name="chunk_index", data_type=DataType.INT),
        Property(name="chunk_count", data_type=DataType.INT),
    ]


def ensure_collection_file_properties(collection: Any) -> None:
    for prop in article_properties()[4:]:
        try:
            collection.config.add_property(prop)
        except Exception as exc:
            if "already exists" not in str(exc):
                raise


def ensure_collection(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists(COLLECTION_NAME):
        ensure_collection_file_properties(client.collections.get(COLLECTION_NAME))
        return

    client.collections.create(
        name=COLLECTION_NAME,
        properties=article_properties(),
        vector_config=Configure.Vectors.self_provided(
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    )


def normalize_document(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    source = str(payload.get("source") or "").strip()
    content = str(payload.get("content") or "").strip()
    upload = payload.get("upload")
    if isinstance(upload, dict):
        upload_text = extract_upload_text(upload)
        if upload_text:
            content = f"{content}\n\n{upload_text}".strip() if content else upload_text

    if not title or not source or not content:
        raise ValueError("標題、來源必填，內容需直接輸入或由 TXT / PDF 檔案提供。")

    source_id = payload.get("source_id")
    if source_id in (None, ""):
        source_id = int(time.time())
    else:
        source_id = int(source_id)

    return {
        "source_id": source_id,
        "title": title,
        "source": source,
        "content": content,
    }


def list_documents() -> list[dict[str, Any]]:
    client = connect_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)
        result = collection.query.fetch_objects(
            limit=100,
            include_vector=True,
            return_metadata=MetadataQuery(creation_time=True),
        )
        documents = []
        for obj in result.objects:
            props = obj.properties
            created_at = obj.metadata.creation_time
            documents.append(
                {
                    "uuid": str(obj.uuid),
                    "source_id": props.get("source_id", ""),
                    "title": props.get("title", ""),
                    "source": props.get("source", ""),
                    "content": props.get("content", ""),
                    "file_name": props.get("file_name", ""),
                    "file_object_key": props.get("file_object_key", ""),
                    "file_bucket": props.get("file_bucket", ""),
                    "file_content_type": props.get("file_content_type", ""),
                    "file_size": props.get("file_size", 0),
                    "chunk_index": props.get("chunk_index", 1),
                    "chunk_count": props.get("chunk_count", 1),
                    "created_at": created_at.isoformat() if created_at else "",
                    "embedding": serialize_embedding(obj.vector),
                }
            )
        documents.sort(key=lambda document: document["created_at"], reverse=True)
        return documents
    finally:
        client.close()


def add_document(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    document = normalize_document(payload)
    content_chunks = split_text_for_embedding(str(document["content"]))
    if not content_chunks:
        raise ValueError("內容需直接輸入或由 TXT / PDF 檔案提供。")

    documents = []
    chunk_count = len(content_chunks)
    for index, content in enumerate(content_chunks, start=1):
        chunk_document = {
            **document,
            "content": content,
            "chunk_index": index,
            "chunk_count": chunk_count,
        }
        documents.append(chunk_document)

    vectors = embed_texts(api_key, [document_embedding_text(item) for item in documents])
    upload = payload.get("upload")
    minio_object: dict[str, Any] = {}
    if isinstance(upload, dict):
        minio_object = save_upload_to_minio(upload, int(document["source_id"]))
        for item in documents:
            item.update(minio_object)

    client = connect_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)
        inserted_documents = []
        for item, vector in zip(documents, vectors):
            uuid = collection.data.insert(properties=item, vector=vector)
            inserted_documents.append({"uuid": str(uuid), **item})
        return inserted_documents[0]
    except Exception:
        delete_minio_object(str(minio_object.get("file_bucket") or ""), str(minio_object.get("file_object_key") or ""))
        raise
    finally:
        client.close()


def delete_document(uuid: str) -> dict[str, bool]:
    client = connect_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)
        obj = collection.query.fetch_object_by_id(uuid)
        file_bucket = ""
        file_object_key = ""
        if obj:
            file_bucket = str(obj.properties.get("file_bucket") or "")
            file_object_key = str(obj.properties.get("file_object_key") or "")

        deleted = bool(collection.data.delete_by_id(uuid))
        if deleted and not is_minio_object_referenced(collection, file_object_key):
            delete_minio_object(file_bucket, file_object_key)
        return {"deleted": deleted}
    finally:
        client.close()


def is_minio_object_referenced(collection: Any, file_object_key: str) -> bool:
    if not file_object_key:
        return False
    result = collection.query.fetch_objects(limit=1000)
    return any(str(obj.properties.get("file_object_key") or "") == file_object_key for obj in result.objects)


def search_references(client: weaviate.WeaviateClient, api_key: str, question: str) -> list[Reference]:
    collection = client.collections.get(COLLECTION_NAME)
    question_vector = embed_texts(api_key, [retrieval_query_text(question)])[0]
    result = collection.query.near_vector(
        near_vector=question_vector,
        limit=REFERENCE_CANDIDATE_LIMIT,
        return_metadata=MetadataQuery(distance=True),
    )

    distances = [obj.metadata.distance for obj in result.objects if obj.metadata.distance is not None]
    best_distance = min(distances) if distances else None
    max_allowed_distance = MAX_REFERENCE_DISTANCE
    if best_distance is not None:
        max_allowed_distance = min(MAX_REFERENCE_DISTANCE, best_distance + REFERENCE_DISTANCE_MARGIN)

    references: list[Reference] = []
    seen_reference_keys: set[tuple[str, str, str]] = set()
    required_term_groups = required_reference_term_groups(question)
    for obj in result.objects:
        distance = obj.metadata.distance
        if distance is not None and distance > max_allowed_distance:
            continue

        props = obj.properties
        if not reference_matches_required_terms(props, required_term_groups):
            continue

        reference_key = (
            str(props.get("title", "")),
            str(props.get("source", "")),
            str(props.get("content", "")),
        )
        if reference_key in seen_reference_keys:
            continue
        seen_reference_keys.add(reference_key)

        references.append(
            Reference(
                index=len(references) + 1,
                uuid=str(obj.uuid),
                source_id=int(props.get("source_id", 0) or 0),
                title=str(props.get("title", "")),
                source=str(props.get("source", "")),
                content=str(props.get("content", "")),
                distance=distance,
            )
        )
        if len(references) >= TOP_K:
            break
    return references


def chat_with_gpt(
    api_key: str,
    question: str,
    references: list[Reference],
    history: list[dict[str, str]],
    rag_enabled: bool = True,
) -> str:
    if references:
        context = "\n\n".join(
            f"[{ref.index}] 來源: {ref.source} | 標題: {ref.title} | source_id: {ref.source_id}\n{ref.content}"
            for ref in references
        )
        user_content = (
            f"使用者目前問題：{question}\n\n"
            f"可用參考資料：\n{context}\n\n"
            "請根據可用參考資料回答。每個使用到的重點都要在句尾加上對應索引，例如 [1]。"
        )
    elif not rag_enabled:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "本次使用者已關閉 RAG 搜尋，請不要使用向量資料庫參考，也不要在回答中加任何 [1] 這類索引。"
        )
    else:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "向量資料庫沒有找到足夠相關的參考資料。請直接回答，不要在回答中加任何 [1] 這類索引。"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "你是使用繁體中文回答的助理。你可以參考同一個對話的短期上下文。"
                "若有向量資料庫參考，只能標註實際用到且能支持內容的索引；不要編造來源。"
                "若沒有參考資料，或本次 RAG 關閉，不要輸出任何引用索引。"
            ),
        },
        *history[-MEMORY_MESSAGES:],
        {"role": "user", "content": user_content},
    ]
    data = openai_post(
        api_key,
        "/chat/completions",
        {
            "model": CHAT_MODEL,
            "temperature": 0.2,
            "messages": messages,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def ask_question(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("問題不可為空。")
    rag_enabled = bool(payload.get("rag_enabled", True))

    conversation_id = str(payload.get("conversation_id") or "default")
    history = CONVERSATIONS.setdefault(conversation_id, [])

    references: list[Reference] = []
    if rag_enabled:
        client = connect_client()
        try:
            ensure_collection(client)
            references = search_references(client, api_key, question)
        finally:
            client.close()

    try:
        answer = chat_with_gpt(api_key, question, references, history, rag_enabled=rag_enabled)
    except Exception:
        raise

    history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    )
    del history[:-MEMORY_MESSAGES]

    return {
        "answer": answer,
        "rag_enabled": rag_enabled,
        "references": [
            {
                "index": ref.index,
                "uuid": ref.uuid,
                "source_id": ref.source_id,
                "title": ref.title,
                "source": ref.source,
                "content": ref.content,
                "distance": ref.distance,
                "distance_text": "未知" if ref.distance is None else f"{ref.distance:.4f}",
            }
            for ref in references
        ],
        "memory_messages": len(history),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "VectorDbChat/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/documents":
            self.send_json({"documents": list_documents()})
            return
        if parsed.path.startswith("/api/"):
            self.send_error_json(404, "找不到路徑。")
            return
        self.send_static(parsed.path)
        return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/documents":
                document = add_document(self.read_document_payload())
                self.send_json({"document": document, "documents": list_documents()}, status=201)
                return
            if parsed.path == "/api/ask":
                self.send_json(ask_question(self.read_json()))
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/documents/"):
                uuid = unquote(parsed.path.removeprefix("/api/documents/"))
                self.send_json(delete_document(uuid))
                return
            if parsed.path.startswith("/api/conversations/"):
                conversation_id = unquote(parsed.path.removeprefix("/api/conversations/"))
                CONVERSATIONS.pop(conversation_id, None)
                self.send_json({"deleted": True})
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def read_document_payload(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.lower().startswith("multipart/form-data"):
            return self.read_multipart_form(content_type)
        return self.read_json()

    def read_multipart_form(self, content_type: str) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}

        body = self.rfile.read(length)
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
        )

        payload: dict[str, Any] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue

            filename = part.get_filename()
            data = part.get_payload(decode=True) or b""
            if filename:
                payload["upload"] = {
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "data": data,
                }
                continue

            charset = part.get_content_charset() or "utf-8"
            payload[str(name)] = data.decode(charset, errors="replace")
        return payload

    def send_static(self, request_path: str) -> None:
        if not FRONTEND_DIST_DIR.exists():
            self.send_error_json(404, "前端尚未 build。開發時請在 frontend\\medivector-chat-app 執行 npm run dev。")
            return

        relative_path = request_path.lstrip("/") or "index.html"
        target = (FRONTEND_DIST_DIR / relative_path).resolve()
        dist_root = FRONTEND_DIST_DIR.resolve()
        try:
            target.relative_to(dist_root)
        except ValueError:
            self.send_error_json(403, "拒絕存取。")
            return
        if not target.is_file():
            target = dist_root / "index.html"
        if not target.is_file():
            self.send_error_json(404, "找不到前端檔案。")
            return

        data = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def send_exception(self, exc: Exception) -> None:
        traceback.print_exc()
        status = 400 if isinstance(exc, (ValueError, json.JSONDecodeError)) else 500
        self.send_error_json(status, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Web app running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
