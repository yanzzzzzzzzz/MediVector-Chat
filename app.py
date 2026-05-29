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
import psycopg
from contextlib import contextmanager
from pgvector.psycopg import register_vector
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))

FRONTEND_DIST_DIR = Path(__file__).with_name("frontend") / "medivector-chat-app" / "dist"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small default
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
RISK_MODEL = "gpt-4o-mini-2024-07-18"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
TOP_K = int(os.getenv("TOP_K", "5"))
REFERENCE_CANDIDATE_LIMIT = int(os.getenv("REFERENCE_CANDIDATE_LIMIT", "20"))
MAX_REFERENCE_DISTANCE = float(os.getenv("MAX_REFERENCE_DISTANCE", "0.65"))
REFERENCE_DISTANCE_MARGIN = float(os.getenv("REFERENCE_DISTANCE_MARGIN", "0.12"))
MIN_REFERENCE_COUNT = int(os.getenv("MIN_REFERENCE_COUNT", "2"))
MAX_EVIDENCE_DISTANCE = float(os.getenv("MAX_EVIDENCE_DISTANCE", str(MAX_REFERENCE_DISTANCE)))
MEMORY_MESSAGES = int(os.getenv("MEMORY_MESSAGES", "10"))
MAX_EMBEDDING_CHARS = int(os.getenv("MAX_EMBEDDING_CHARS", "6000"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "health-education-files")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "medivector")
PG_PASSWORD = os.getenv("PG_PASSWORD", "medivector")
PG_DATABASE = os.getenv("PG_DATABASE", "medivector")


CONVERSATION_RETRIEVAL_TERMS: dict[str, list[str]] = {}


QUERY_EXPANSION_MODEL = "gpt-4o-mini-2024-07-18"

@dataclass
class Reference:
    index: int
    uuid: str
    source_id: int
    title: str
    source: str
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


RISK_GREEN_ACTION = "一般衛教模式：提供健康教育資訊與自我照護建議。"
RISK_YELLOW_ACTION = "注意：可能有惡化風險，請提供保守建議並提醒觀察警訊與就醫時機。"
RISK_RED_ACTION = "急症分流：請立即提供就醫/急救指引，不進行一般衛教問答。"

RESPONSE_SECTION_SUMMARY = "【重點摘要】"
RESPONSE_SECTION_ACTIONS = "【你現在可以做的事】"
RESPONSE_SECTION_WARNINGS = "【警訊（出現以下情況請就醫）】"
RESPONSE_SECTION_WHEN_TO_SEEK_CARE = "【何時就醫】"
RESPONSE_SECTIONS = (
    RESPONSE_SECTION_SUMMARY,
    RESPONSE_SECTION_ACTIONS,
    RESPONSE_SECTION_WARNINGS,
    RESPONSE_SECTION_WHEN_TO_SEEK_CARE,
)


def parse_risk_level(level: str) -> str:
    normalized = (level or "").strip().lower()
    if normalized in {"red", "yellow", "green"}:
        return normalized
    return "yellow"


def level_to_label(level: str) -> str:
    if level == "red":
        return "急症"
    if level == "yellow":
        return "注意"
    return "一般"


def level_to_action(level: str) -> str:
    if level == "red":
        return RISK_RED_ACTION
    if level == "yellow":
        return RISK_YELLOW_ACTION
    return RISK_GREEN_ACTION


def normalize_retrieval_terms(terms: list[str]) -> list[str]:
    normalized_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms:
        cleaned_term = re.sub(r"\s+", " ", str(term or "").strip())
        if not cleaned_term:
            continue
        lowered_term = cleaned_term.lower()
        if lowered_term in seen_terms:
            continue
        seen_terms.add(lowered_term)
        normalized_terms.append(cleaned_term)
    return normalized_terms


def generate_retrieval_terms(api_key: str, question: str, history: list[dict[str, str]]) -> list[str]:
    recent_user_turns = [
        str(message.get("content") or "").strip()
        for message in history[-6:]
        if str(message.get("role") or "") == "user" and str(message.get("content") or "").strip()
    ]
    conversation_context = "\n".join(f"- {turn}" for turn in recent_user_turns)

    schema = {
        "name": "retrieval_query_terms",
        "schema": {
            "type": "object",
            "properties": {
                "terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 8,
                },
            },
            "required": ["terms"],
            "additionalProperties": False,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是醫療檢索關鍵詞擴展器。"
                "規則：\n"
                "1. 必須保留問題中出現的所有解剖部位、症狀、疾病名稱，不可省略。\n"
                "2. 每個中文關鍵詞都必須同時加上對應的英文同義詞或醫學術語（例如：鼠蹊部→groin inguinal，發燒→fever pyrexia）。\n"
                "3. 可追加相關症狀、病因、治療方式的中英詞，但不要偏離問題主題。\n"
                "4. 不要寫完整句子，詞組需簡短，適合直接拼接到向量檢索查詢中。\n"
                "5. 避免重複、避免與問題無關的泛用詞。\n"
                "只輸出符合 schema 的 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"使用者當前問題：{question}\n\n"
                f"最近對話內容：\n{conversation_context or '- 無'}\n\n"
                "請先列出問題中的解剖部位與症狀詞（含英文），再追加 2 到 4 個相關擴展詞（含英文），合計 3 到 8 組。"
            ),
        },
    ]

    try:
        data = openai_post(
            api_key,
            "/chat/completions",
            {
                "model": QUERY_EXPANSION_MODEL,
                "temperature": 0.2,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": schema,
                },
            },
        )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        terms = normalize_retrieval_terms([str(term) for term in parsed.get("terms") or []])
        return terms[:8]
    except Exception:
        return []


def get_conversation_retrieval_terms(
    api_key: str,
    conversation_id: str,
    question: str,
    history: list[dict[str, str]],
) -> list[str]:
    cached_terms = CONVERSATION_RETRIEVAL_TERMS.get(conversation_id)
    if cached_terms is not None:
        return cached_terms

    generated_terms = generate_retrieval_terms(api_key, question, history)
    CONVERSATION_RETRIEVAL_TERMS[conversation_id] = generated_terms
    return generated_terms


def assess_question_risk(api_key: str, question: str) -> RiskAssessment:
    text = question.strip()
    if not text:
        return RiskAssessment(
            level="green",
            label="一般",
            reason="問題為空，預設一般風險。",
            diverted=False,
            action=RISK_GREEN_ACTION,
        )
    schema = {
        "name": "risk_triage",
        "schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["red", "yellow", "green"]},
                "reason": {"type": "string"},
            },
            "required": ["level", "reason"],
            "additionalProperties": False,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是醫療風險分級器。"
                "請只根據使用者描述判斷危險程度："
                "red=急症需立即就醫或撥打 119；"
                "yellow=可能惡化需儘快就醫或密切觀察；"
                "green=一般衛教情境。"
                "只輸出符合 schema 的 JSON。"
            ),
        },
        {
            "role": "user",
            "content": f"請判斷以下問題風險等級：\n{text}",
        },
    ]

    try:
        data = openai_post(
            api_key,
            "/chat/completions",
            {
                "model": RISK_MODEL,
                "temperature": 0,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": schema,
                },
            },
        )
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        level = parse_risk_level(str(parsed.get("level") or ""))
        reason = str(parsed.get("reason") or "AI 未提供原因。").strip()
    except Exception as exc:
        # Risk evaluation failure should fail safe to cautious triage.
        level = "yellow"
        reason = f"AI 風險評估暫時不可用，採保守分級。({exc})"

    return RiskAssessment(
        level=level,
        label=level_to_label(level),
        reason=reason,
        diverted=(level == "red"),
        action=level_to_action(level),
    )


def emergency_diversion_answer(question: str) -> str:
    return (
        "你的描述可能涉及急症風險，這裡不適合只靠線上衛教處理。\n"
        "請立即採取以下行動：\n"
        "1. 若有胸痛、呼吸困難、意識改變、大量出血，請立即撥打 119。\n"
        "2. 請盡快前往急診，並告知症狀開始時間、是否持續惡化。\n"
        "3. 若身邊有人可協助，請不要單獨前往。\n\n"
        f"你剛剛提到的問題：{question}\n"
        "若你願意，我可以再幫你整理給醫護人員的重點描述清單。"
    )


def has_required_response_sections(answer: str) -> bool:
    return all(section in answer for section in RESPONSE_SECTIONS)


def normalized_template_answer(answer: str, risk: RiskAssessment) -> str:
    if has_required_response_sections(answer):
        return answer

    summary = answer.strip() or "目前資訊有限，以下提供一般衛教建議。"
    action_lines = [
        "- 先休息、補充水分，避免劇烈活動或自行加重處置。",
        "- 記錄症狀發生時間、頻率與加重/緩解因素。",
        "- 若你有慢性病或正在用藥，請先避免自行增減藥物。",
    ]

    warning_lines = [
        "- 症狀快速惡化、持續不改善或影響日常活動。",
        "- 出現呼吸困難、意識改變、胸痛、持續高燒等危險訊號。",
        "- 出現脫水、反覆嘔吐、無法進食或其他明顯異常。",
    ]

    when_to_seek_care_lines = ["- 若有任何危險訊號，請立即就醫或撥打 119。"]
    if risk.level == "yellow":
        when_to_seek_care_lines.append("- 建議今天內或 24 小時內安排門診/急診評估。")
    else:
        when_to_seek_care_lines.append("- 若症狀持續超過 1 至 2 天或反覆發作，請儘快就醫。")

    return "\n\n".join(
        [
            RESPONSE_SECTION_SUMMARY,
            summary,
            RESPONSE_SECTION_ACTIONS,
            "\n".join(action_lines),
            RESPONSE_SECTION_WARNINGS,
            "\n".join(warning_lines),
            RESPONSE_SECTION_WHEN_TO_SEEK_CARE,
            "\n".join(when_to_seek_care_lines),
        ]
    )


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


def retrieval_query_text(question: str, retrieval_terms: list[str] | None = None) -> str:
    normalized_terms = normalize_retrieval_terms(retrieval_terms or [])
    if not normalized_terms:
        return question
    return f"{question}\n\n檢索關鍵詞：{' '.join(normalized_terms)}"


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
    try:
        import numpy as np
        if isinstance(vector_payload, np.ndarray):
            return vector_payload.tolist()
    except ImportError:
        pass
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


def get_pg_conninfo() -> str:
    return f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={PG_DATABASE}"


@contextmanager
def db_connection():
    conn = psycopg.connect(get_pg_conninfo())
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    max_retries = 10
    # Step 1: 建立 extension（不需要 vector type，用普通連線）
    for attempt in range(max_retries):
        try:
            conn = psycopg.connect(get_pg_conninfo())
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
            finally:
                conn.close()
            break
        except Exception as exc:
            if attempt < max_retries - 1:
                print(f"DB 連線失敗（{attempt + 1}/{max_retries}），3 秒後重試…: {exc}", file=sys.stderr)
                time.sleep(3)
            else:
                raise

    # Step 2: 建立資料表（extension 已存在，可安全 register_vector）
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS articles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_id BIGINT NOT NULL DEFAULT 0,
                    title TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL DEFAULT '',
                    file_object_key TEXT NOT NULL DEFAULT '',
                    file_bucket TEXT NOT NULL DEFAULT '',
                    file_content_type TEXT NOT NULL DEFAULT '',
                    file_size BIGINT NOT NULL DEFAULT 0,
                    chunk_index INT NOT NULL DEFAULT 1,
                    chunk_count INT NOT NULL DEFAULT 1,
                    embedding VECTOR({EMBEDDING_DIM}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_embedding_idx
                ON articles USING hnsw (embedding vector_cosine_ops)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS messages_conv_idx
                ON messages (conversation_id, created_at)
            """)


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
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, source_id, title, source, content,
                       file_name, file_object_key, file_bucket, file_content_type, file_size,
                       chunk_index, chunk_count, embedding, created_at
                FROM articles
                ORDER BY created_at DESC
                LIMIT 100
            """)
            rows = cur.fetchall()
    documents = []
    for row in rows:
        (id_, source_id, title, source, content,
         file_name, file_object_key, file_bucket, file_content_type, file_size,
         chunk_index, chunk_count, embedding, created_at) = row
        documents.append({
            "uuid": str(id_),
            "source_id": source_id or 0,
            "title": title or "",
            "source": source or "",
            "content": content or "",
            "file_name": file_name or "",
            "file_object_key": file_object_key or "",
            "file_bucket": file_bucket or "",
            "file_content_type": file_content_type or "",
            "file_size": file_size or 0,
            "chunk_index": chunk_index or 1,
            "chunk_count": chunk_count or 1,
            "created_at": created_at.isoformat() if created_at else "",
            "embedding": serialize_embedding(embedding),
        })
    return documents


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

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                inserted_documents = []
                for item, vector in zip(documents, vectors):
                    cur.execute("""
                        INSERT INTO articles
                            (source_id, title, source, content, file_name, file_object_key,
                             file_bucket, file_content_type, file_size, chunk_index, chunk_count, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        item.get("source_id", 0),
                        item.get("title", ""),
                        item.get("source", ""),
                        item.get("content", ""),
                        item.get("file_name", ""),
                        item.get("file_object_key", ""),
                        item.get("file_bucket", ""),
                        item.get("file_content_type", ""),
                        item.get("file_size", 0),
                        item.get("chunk_index", 1),
                        item.get("chunk_count", 1),
                        vector,
                    ))
                    row = cur.fetchone()
                    inserted_documents.append({"uuid": str(row[0]), **item})
        return inserted_documents[0]
    except Exception:
        delete_minio_object(str(minio_object.get("file_bucket") or ""), str(minio_object.get("file_object_key") or ""))
        raise


def delete_document(uuid: str) -> dict[str, bool]:
    file_bucket = ""
    file_object_key = ""
    deleted = False
    should_delete_minio = False
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_bucket, file_object_key FROM articles WHERE id = %s",
                (uuid,),
            )
            row = cur.fetchone()
            if not row:
                return {"deleted": False}
            file_bucket, file_object_key = str(row[0] or ""), str(row[1] or "")
            cur.execute("DELETE FROM articles WHERE id = %s", (uuid,))
            deleted = cur.rowcount > 0
            if deleted and file_object_key:
                cur.execute(
                    "SELECT 1 FROM articles WHERE file_object_key = %s LIMIT 1",
                    (file_object_key,),
                )
                should_delete_minio = cur.fetchone() is None
    if should_delete_minio:
        delete_minio_object(file_bucket, file_object_key)
    return {"deleted": deleted}


def search_references(
    api_key: str,
    question: str,
    retrieval_terms: list[str] | None = None,
) -> list[Reference]:
    question_vector = embed_texts(api_key, [retrieval_query_text(question, retrieval_terms)])[0]
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_id, title, source, content,
                       embedding <=> %s::vector AS distance
                FROM articles
                ORDER BY distance
                LIMIT %s
                """,
                (question_vector, REFERENCE_CANDIDATE_LIMIT),
            )
            rows = cur.fetchall()

    distances = [float(row[5]) for row in rows if row[5] is not None]
    best_distance = min(distances) if distances else None
    max_allowed_distance = MAX_REFERENCE_DISTANCE
    if best_distance is not None:
        max_allowed_distance = min(MAX_REFERENCE_DISTANCE, best_distance + REFERENCE_DISTANCE_MARGIN)

    references: list[Reference] = []
    seen_reference_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        id_, source_id, title, source, content, distance = row
        distance = float(distance) if distance is not None else None
        if distance is not None and distance > max_allowed_distance:
            continue

        reference_key = (str(title or ""), str(source or ""), str(content or ""))
        if reference_key in seen_reference_keys:
            continue
        seen_reference_keys.add(reference_key)

        references.append(
            Reference(
                index=len(references) + 1,
                uuid=str(id_),
                source_id=int(source_id or 0),
                title=str(title or ""),
                source=str(source or ""),
                content=str(content or ""),
                distance=distance,
            )
        )
        if len(references) >= TOP_K:
            break
    return references


def assess_evidence(references: list[Reference]) -> EvidenceAssessment:
    if not references:
        return EvidenceAssessment(
            sufficient=False,
            reason="沒有找到可用參考資料。",
            reference_count=0,
            best_distance=None,
        )

    distances = [ref.distance for ref in references if ref.distance is not None]
    best_distance = min(distances) if distances else None
    if len(references) < MIN_REFERENCE_COUNT:
        return EvidenceAssessment(
            sufficient=False,
            reason=f"參考資料不足，只有 {len(references)} 筆。",
            reference_count=len(references),
            best_distance=best_distance,
        )

    if best_distance is not None and best_distance > MAX_EVIDENCE_DISTANCE:
        return EvidenceAssessment(
            sufficient=False,
            reason=f"最佳參考距離過高（{best_distance:.4f}），證據偏弱。",
            reference_count=len(references),
            best_distance=best_distance,
        )

    return EvidenceAssessment(
        sufficient=True,
        reason="參考資料數量與距離達到門檻。",
        reference_count=len(references),
        best_distance=best_distance,
    )


def chat_with_gpt(
    api_key: str,
    question: str,
    references: list[Reference],
    history: list[dict[str, str]],
    risk: RiskAssessment,
    evidence: EvidenceAssessment,
    rag_enabled: bool = True,
) -> str:
    template_instruction = (
        "回答必須使用以下四段固定格式，且段落標題需完全一致：\n"
        f"{RESPONSE_SECTION_SUMMARY}\n"
        f"{RESPONSE_SECTION_ACTIONS}\n"
        f"{RESPONSE_SECTION_WARNINGS}\n"
        f"{RESPONSE_SECTION_WHEN_TO_SEEK_CARE}\n"
        "每段內容請簡潔、可執行。"
    )

    evidence_instruction = (
        f"本次引用證據狀態：{'足夠' if evidence.sufficient else '不足'}。"
        f"原因：{evidence.reason}"
    )

    if references:
        context = "\n\n".join(
            f"[{ref.index}] 來源: {ref.source} | 標題: {ref.title} | source_id: {ref.source_id}\n{ref.content}"
            for ref in references
        )
        user_content = (
            f"使用者目前問題：{question}\n\n"
            f"可用參考資料：\n{context}\n\n"
            "請根據可用參考資料回答。"
            "每個使用到參考資料的重點都要在句尾加上對應索引，例如 [1]。"
            "不要引用未使用或不存在的索引。\n\n"
            f"{evidence_instruction}\n"
            "如果證據不足，請以保守方式回答，不要下定論或使用過度肯定語氣。\n\n"
            f"{template_instruction}"
        )
    elif not rag_enabled:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "本次使用者已關閉 RAG 搜尋，請不要使用向量資料庫參考，也不要在回答中加任何 [1] 這類索引。"
            f"\n\n{evidence_instruction}\n"
            "請以保守方式回答，不要表現出有檢索證據支持的確定語氣。\n\n"
            f"{template_instruction}"
        )
    else:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "向量資料庫沒有找到足夠相關的參考資料。請直接回答，不要在回答中加任何 [1] 這類索引。"
            f"\n\n{evidence_instruction}\n"
            "請明確標示這是保守衛教，不要給出確定性判斷。\n\n"
            f"{template_instruction}"
        )

    risk_instruction = (
        "本次風險分級："
        f"{risk.label}（{risk.level}）。"
        f"處置原則：{risk.action}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是使用繁體中文回答的助理。你可以參考同一個對話的短期上下文。"
                "若有向量資料庫參考，只能標註實際用到且能支持內容的索引；不要編造來源。"
                "若沒有參考資料，或本次 RAG 關閉，不要輸出任何引用索引。"
                "你只提供衛教資訊，不可做出診斷、處方、劑量建議或保證療效。"
                "當引用證據不足時，必須主動降低語氣強度，明確說明不確定性。"
                "語氣需保守，不可過度肯定，遇到不確定資訊要明確說明限制。"
            ),
        },
        {"role": "system", "content": risk_instruction},
        {"role": "system", "content": evidence_instruction},
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
    answer = data["choices"][0]["message"]["content"].strip()
    return normalized_template_answer(answer, risk)


def ensure_conversation(conn: psycopg.Connection, conversation_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (conversation_id,),
        )


def load_conversation_history(conversation_id: str) -> list[dict[str, str]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at
                """,
                (conversation_id,),
            )
            rows = cur.fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]


def save_messages(conversation_id: str, new_messages: list[dict[str, str]]) -> None:
    with db_connection() as conn:
        ensure_conversation(conn, conversation_id)
        with conn.cursor() as cur:
            for msg in new_messages:
                cur.execute(
                    "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                    (conversation_id, msg["role"], msg["content"]),
                )
            cur.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = %s
                  AND id NOT IN (
                      SELECT id FROM messages
                      WHERE conversation_id = %s
                      ORDER BY created_at DESC
                      LIMIT %s
                  )
                """,
                (conversation_id, conversation_id, MEMORY_MESSAGES),
            )


def delete_conversation(conversation_id: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
    CONVERSATION_RETRIEVAL_TERMS.pop(conversation_id, None)


def ask_question(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("問題不可為空。")
    rag_enabled = bool(payload.get("rag_enabled", True))
    risk = assess_question_risk(api_key, question)

    conversation_id = str(payload.get("conversation_id") or "default")
    history = load_conversation_history(conversation_id)[-MEMORY_MESSAGES:]

    if risk.diverted:
        answer = emergency_diversion_answer(question)
        save_messages(conversation_id, [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ])
        return {
            "answer": answer,
            "rag_enabled": False,
            "references": [],
            "memory_messages": len(history) + 2,
            "risk_assessment": {
                "level": risk.level,
                "label": risk.label,
                "reason": risk.reason,
                "diverted": risk.diverted,
                "action": risk.action,
            },
        }

    references: list[Reference] = []
    evidence = EvidenceAssessment(
        sufficient=False,
        reason="未評估。",
        reference_count=0,
        best_distance=None,
    )
    retrieval_terms: list[str] = []
    if rag_enabled:
        retrieval_terms = get_conversation_retrieval_terms(api_key, conversation_id, question, history)
        references = search_references(api_key, question, retrieval_terms)
        evidence = assess_evidence(references)
    else:
        evidence = EvidenceAssessment(
            sufficient=False,
            reason="RAG 已關閉，未進行引用證據評估。",
            reference_count=0,
            best_distance=None,
        )

    try:
        answer = chat_with_gpt(api_key, question, references, history, risk, evidence, rag_enabled=rag_enabled)
    except Exception:
        raise

    save_messages(conversation_id, [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ])

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
        "evidence_assessment": {
            "sufficient": evidence.sufficient,
            "reason": evidence.reason,
            "reference_count": evidence.reference_count,
            "best_distance": evidence.best_distance,
        },
        "retrieval_terms": retrieval_terms,
        "memory_messages": len(history) + 2,
        "risk_assessment": {
            "level": risk.level,
            "label": risk.label,
            "reason": risk.reason,
            "diverted": risk.diverted,
            "action": risk.action,
        },
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
                delete_conversation(conversation_id)
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


def _serve() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    init_db()
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Web app running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


def main() -> None:
    reload = "--reload" in sys.argv or os.getenv("RELOAD", "").lower() in {"1", "true", "yes"}
    if reload:
        try:
            from watchfiles import run_process
        except ImportError:
            print("watchfiles 未安裝，請執行 pip install watchfiles。", file=sys.stderr)
            sys.exit(1)
        print("Auto-reload 已啟用，監聽 app.py 變動…")
        run_process(Path(__file__), target=_serve, watch_filter=lambda _c, p: p == str(Path(__file__).resolve()))
    else:
        _serve()


if __name__ == "__main__":
    main()
