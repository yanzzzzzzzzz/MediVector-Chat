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
from datetime import date
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


QUERY_EXPANSION_MODEL = "gpt-4o-mini-2024-07-18"

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


def generate_retrieval_query(api_key: str, question: str, history: list[dict[str, str]]) -> RetrievalQuery:
    recent_user_turns = [
        str(message.get("content") or "").strip()
        for message in history[-6:]
        if str(message.get("role") or "") == "user" and str(message.get("content") or "").strip()
    ]
    conversation_context = "\n".join(f"- {turn}" for turn in recent_user_turns)

    schema = {
        "name": "retrieval_query_contextualization",
        "schema": {
            "type": "object",
            "properties": {
                "needs_context": {"type": "boolean"},
                "standalone_question": {"type": "string"},
                "terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 8,
                },
            },
            "required": ["needs_context", "standalone_question", "terms"],
            "additionalProperties": False,
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是醫療 RAG 檢索查詢改寫器。"
                "規則：\n"
                "1. 先判斷當前問題是否必須參考最近對話才能理解，並輸出 needs_context。\n"
                "2. 如果當前問題已明確包含症狀、疾病、解剖部位、檢查、治療或藥物，通常視為新檢索主題，不要把最近對話中的其他主題加入 standalone_question 或 terms。\n"
                "3. 只有當問題是語意不完整的追問時，才使用最近對話補全 standalone_question。\n"
                "4. standalone_question 必須是可獨立拿去向量檢索的完整問題；不可加入當前問題與必要上下文以外的主題。\n"
                "5. terms 必須根據 standalone_question 產生，必須保留其中所有解剖部位、症狀、疾病名稱。\n"
                "6. 每個中文關鍵詞都必須同時加上對應的英文同義詞或醫學術語（例如：鼠蹊部→groin inguinal，發燒→fever pyrexia）。\n"
                "7. 可追加相關症狀、病因、治療方式的中英詞，但不要偏離 standalone_question。\n"
                "8. 不要寫完整句子，詞組需簡短，適合直接拼接到向量檢索查詢中。\n"
                "9. 避免重複、避免與問題無關的泛用詞或歷史對話主題。\n"
                "只輸出符合 schema 的 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"使用者當前問題：{question}\n\n"
                f"最近對話內容：\n{conversation_context or '- 無'}\n\n"
                "請輸出 needs_context、standalone_question，並依 standalone_question 產生 3 到 8 組中英文檢索詞。"
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
        standalone_question = str(parsed.get("standalone_question") or "").strip() or question
        terms = normalize_retrieval_terms([str(term) for term in parsed.get("terms") or []])
        return RetrievalQuery(
            question=standalone_question,
            terms=terms[:8],
            needs_context=bool(parsed.get("needs_context")),
        )
    except Exception:
        return RetrievalQuery(question=question, terms=[], needs_context=False)


def get_retrieval_query(
    api_key: str,
    question: str,
    history: list[dict[str, str]],
) -> RetrievalQuery:
    return generate_retrieval_query(api_key, question, history)


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
    metadata_lines = [
        f"標題：{document['title']}",
        f"來源：{document['source']}",
        f"日期：{document.get('published_date', '')}",
        f"適用對象：{document.get('audience', '')}",
        f"主題分類：{document.get('topic', '')}",
        f"內容：{document['content']}",
    ]
    return "\n".join(line for line in metadata_lines if not line.endswith("："))


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
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
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
                    document_id UUID NOT NULL DEFAULT gen_random_uuid(),
                    source_id BIGINT NOT NULL DEFAULT 0,
                    title TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    publisher TEXT NOT NULL DEFAULT '',
                    published_date TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    audience TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    credibility TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL DEFAULT '',
                    file_object_key TEXT NOT NULL DEFAULT '',
                    file_bucket TEXT NOT NULL DEFAULT '',
                    file_content_type TEXT NOT NULL DEFAULT '',
                    file_size BIGINT NOT NULL DEFAULT 0,
                    chunk_index INT NOT NULL DEFAULT 1,
                    chunk_count INT NOT NULL DEFAULT 1,
                    embedding VECTOR({EMBEDDING_DIM}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS document_id UUID")
            cur.execute("UPDATE articles SET document_id = id WHERE document_id IS NULL")
            cur.execute("ALTER TABLE articles ALTER COLUMN document_id SET DEFAULT gen_random_uuid()")
            cur.execute("ALTER TABLE articles ALTER COLUMN document_id SET NOT NULL")
            for column_name in (
                "publisher",
                "published_date",
                "version",
                "audience",
                "topic",
                "credibility",
            ):
                cur.execute(f"ALTER TABLE articles ADD COLUMN IF NOT EXISTS {column_name} TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_embedding_idx
                ON articles USING hnsw (embedding vector_cosine_ops)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_document_id_idx
                ON articles (document_id, chunk_index)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_topic_idx
                ON articles (topic)
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


def metadata_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "publisher": str(payload.get("publisher") or "").strip(),
        "published_date": str(payload.get("published_date") or "").strip() or date.today().isoformat(),
        "version": str(payload.get("version") or "").strip(),
        "audience": str(payload.get("audience") or "").strip(),
        "topic": str(payload.get("topic") or "").strip(),
        "credibility": str(payload.get("credibility") or "").strip(),
    }


def metadata_source_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    content = str(payload.get("content") or "").strip()
    if content:
        parts.append(f"手動輸入內容：\n{content}")

    uploads = payload.get("uploads")
    if isinstance(uploads, list):
        upload_items = uploads
    else:
        upload = payload.get("upload")
        upload_items = [upload] if isinstance(upload, dict) else []

    for upload in upload_items:
        filename = str(upload.get("filename") or "").strip()
        extracted_text = extract_upload_text(upload)
        parts.append(f"檔名：{filename}\n檔案文字：\n{extracted_text}")

    return "\n\n---\n\n".join(parts).strip()


def infer_document_metadata(payload: dict[str, Any]) -> dict[str, str]:
    api_key = require_openai_api_key()
    source_text = metadata_source_text(payload)
    if not source_text:
        raise ValueError("請先輸入內容或選擇 TXT / PDF 檔案，才能自動填入資料欄位。")

    clipped_source_text = source_text[:16000]
    schema = {
        "name": "health_document_metadata",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "published_date": {"type": "string"},
                "audience": {"type": "string"},
                "topic": {"type": "string"},
            },
            "required": [
                "title",
                "published_date",
                "audience",
                "topic",
            ],
            "additionalProperties": False,
        },
    }
    data = openai_post(
        api_key,
        "/chat/completions",
        {
            "model": RISK_MODEL,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是衛教資料庫的 metadata 抽取器。"
                        "請只根據提供內容與檔名線索抽取欄位，不要編造。"
                        "除了 audience 以外，若欄位沒有明確資訊，請輸出空字串。"
                        "來源欄位需由使用者手動填寫，不要輸出來源。"
                        "published_date 若能判斷，優先輸出 YYYY-MM-DD；只能判斷年份或年月時保留原文。"
                        "audience 請根據內容合理推定適用對象；若沒有特定族群限制，請輸出「一般民眾」。"
                        "若內容明顯只適合特定族群，請輸出例如「兒童」、「孕婦」、「成人」、「高齡者」、「照護者」或組合。"
                        "topic 請輸出 1 到 3 個繁體中文分類，用「 / 」分隔。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"請抽取這份衛教資料的 metadata：\n\n{clipped_source_text}",
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": schema,
            },
        },
    )
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {
        "title": str(parsed.get("title") or "").strip(),
        "published_date": str(parsed.get("published_date") or "").strip(),
        "audience": str(parsed.get("audience") or "").strip() or "一般民眾",
        "topic": str(parsed.get("topic") or "").strip(),
    }


def source_id_from_payload(payload: dict[str, Any], default_source_id: int | None = None) -> int:
    source_id = payload.get("source_id")
    if source_id in (None, ""):
        return default_source_id if default_source_id is not None else int(time.time() * 1000)
    return int(source_id)


def upload_title(upload: dict[str, Any]) -> str:
    filename = str(upload.get("filename") or "").strip()
    if not filename:
        return ""
    return os.path.splitext(os.path.basename(filename))[0].strip()


def normalize_document(
    payload: dict[str, Any],
    upload: dict[str, Any] | None = None,
    document_id: str | None = None,
    default_source_id: int | None = None,
) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    source = str(payload.get("source") or "").strip()
    content = str(payload.get("content") or "").strip()
    if not title and isinstance(upload, dict):
        title = upload_title(upload)
    if isinstance(upload, dict):
        upload_text = extract_upload_text(upload)
        if upload_text:
            content = f"{content}\n\n{upload_text}".strip() if content else upload_text

    if not title or not source or not content:
        raise ValueError("標題、來源必填，內容需直接輸入或由 TXT / PDF 檔案提供。")

    return {
        "document_id": document_id or str(uuidlib.uuid4()),
        "source_id": source_id_from_payload(payload, default_source_id),
        "title": title,
        "source": source,
        **metadata_from_payload(payload),
        "content": content,
    }


def list_documents() -> list[dict[str, Any]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, document_id, source_id, title, source,
                       publisher, published_date, version, audience, topic, credibility,
                       content,
                       file_name, file_object_key, file_bucket, file_content_type, file_size,
                       chunk_index, chunk_count, embedding, created_at, updated_at
                FROM articles
                ORDER BY updated_at DESC, created_at DESC, document_id, chunk_index
                LIMIT 500
            """)
            rows = cur.fetchall()
    documents = []
    for row in rows:
        (id_, document_id, source_id, title, source,
         publisher, published_date, version, audience, topic, credibility,
         content,
         file_name, file_object_key, file_bucket, file_content_type, file_size,
         chunk_index, chunk_count, embedding, created_at, updated_at) = row
        documents.append({
            "uuid": str(id_),
            "document_id": str(document_id),
            "source_id": source_id or 0,
            "title": title or "",
            "source": source or "",
            "publisher": publisher or "",
            "published_date": published_date or "",
            "version": version or "",
            "audience": audience or "",
            "topic": topic or "",
            "credibility": credibility or "",
            "content": content or "",
            "file_name": file_name or "",
            "file_object_key": file_object_key or "",
            "file_bucket": file_bucket or "",
            "file_content_type": file_content_type or "",
            "file_size": file_size or 0,
            "chunk_index": chunk_index or 1,
            "chunk_count": chunk_count or 1,
            "created_at": created_at.isoformat() if created_at else "",
            "updated_at": updated_at.isoformat() if updated_at else "",
            "embedding": serialize_embedding(embedding),
        })
    return documents


def insert_document_chunks(
    cur: psycopg.Cursor,
    documents: list[dict[str, Any]],
    vectors: list[list[float]],
) -> list[dict[str, Any]]:
    inserted_documents = []
    for item, vector in zip(documents, vectors):
        cur.execute("""
            INSERT INTO articles
                (document_id, source_id, title, source, publisher, published_date, version,
                 audience, topic, credibility, content, file_name, file_object_key,
                 file_bucket, file_content_type, file_size, chunk_index, chunk_count, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            item.get("document_id"),
            item.get("source_id", 0),
            item.get("title", ""),
            item.get("source", ""),
            item.get("publisher", ""),
            item.get("published_date", ""),
            item.get("version", ""),
            item.get("audience", ""),
            item.get("topic", ""),
            item.get("credibility", ""),
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
    return inserted_documents


def build_document_chunks(document: dict[str, Any], file_metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    content_chunks = split_text_for_embedding(str(document["content"]))
    if not content_chunks:
        raise ValueError("內容需直接輸入或由 TXT / PDF 檔案提供。")

    documents = []
    chunk_count = len(content_chunks)
    for index, content in enumerate(content_chunks, start=1):
        chunk_document = {
            **document,
            **(file_metadata or {}),
            "content": content,
            "chunk_index": index,
            "chunk_count": chunk_count,
        }
        documents.append(chunk_document)
    return documents


def add_one_document(
    payload: dict[str, Any],
    api_key: str,
    upload: dict[str, Any] | None = None,
    default_source_id: int | None = None,
) -> list[dict[str, Any]]:
    document = normalize_document(payload, upload=upload, default_source_id=default_source_id)
    minio_object: dict[str, Any] = {}
    try:
        if isinstance(upload, dict):
            minio_object = save_upload_to_minio(upload, int(document["source_id"]))
        documents = build_document_chunks(document, minio_object)
        vectors = embed_texts(api_key, [document_embedding_text(item) for item in documents])
        with db_connection() as conn:
            with conn.cursor() as cur:
                return insert_document_chunks(cur, documents, vectors)
    except Exception:
        delete_minio_object(str(minio_object.get("file_bucket") or ""), str(minio_object.get("file_object_key") or ""))
        raise


def add_documents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    api_key = require_openai_api_key()
    uploads = payload.get("uploads")
    if isinstance(uploads, list) and uploads:
        inserted: list[dict[str, Any]] = []
        base_source_id = source_id_from_payload(payload)
        for index, upload in enumerate(uploads):
            inserted.extend(add_one_document(payload, api_key, upload=upload, default_source_id=base_source_id + index))
        return inserted

    upload = payload.get("upload")
    return add_one_document(payload, api_key, upload=upload if isinstance(upload, dict) else None)


def add_document(payload: dict[str, Any]) -> dict[str, Any]:
    documents = add_documents(payload)
    return documents[0]


def fetch_document_file_objects(cur: psycopg.Cursor, document_id: str) -> list[tuple[str, str]]:
    cur.execute(
        """
        SELECT DISTINCT file_bucket, file_object_key
        FROM articles
        WHERE document_id = %s AND file_object_key <> ''
        """,
        (document_id,),
    )
    return [(str(row[0] or ""), str(row[1] or "")) for row in cur.fetchall()]


def cleanup_unreferenced_minio_objects(file_objects: list[tuple[str, str]]) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            for file_bucket, file_object_key in file_objects:
                if not file_object_key:
                    continue
                cur.execute(
                    "SELECT 1 FROM articles WHERE file_object_key = %s LIMIT 1",
                    (file_object_key,),
                )
                if cur.fetchone() is None:
                    delete_minio_object(file_bucket, file_object_key)


def resolve_document_id(cur: psycopg.Cursor, id_or_document_id: str) -> str | None:
    cur.execute(
        "SELECT document_id FROM articles WHERE document_id = %s OR id = %s LIMIT 1",
        (id_or_document_id, id_or_document_id),
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


def update_document(id_or_document_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    uploads = payload.get("uploads")
    if isinstance(uploads, list) and len(uploads) > 1:
        raise ValueError("編輯單份文件時一次只能替換一個檔案。")
    upload = uploads[0] if isinstance(uploads, list) and uploads else payload.get("upload")
    upload = upload if isinstance(upload, dict) else None

    with db_connection() as conn:
        with conn.cursor() as cur:
            document_id = resolve_document_id(cur, id_or_document_id)
            if not document_id:
                raise ValueError("找不到要編輯的文件。")
            cur.execute(
                """
                SELECT file_name, file_object_key, file_bucket, file_content_type, file_size
                FROM articles
                WHERE document_id = %s
                ORDER BY chunk_index
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
            existing_file_metadata = {
                "file_name": str(row[0] or "") if row else "",
                "file_object_key": str(row[1] or "") if row else "",
                "file_bucket": str(row[2] or "") if row else "",
                "file_content_type": str(row[3] or "") if row else "",
                "file_size": int(row[4] or 0) if row else 0,
            }
            old_file_objects = fetch_document_file_objects(cur, document_id)

    document = normalize_document(payload, upload=upload, document_id=document_id)
    minio_object: dict[str, Any] = {}
    try:
        if upload:
            minio_object = save_upload_to_minio(upload, int(document["source_id"]))
        file_metadata = minio_object or existing_file_metadata
        documents = build_document_chunks(document, file_metadata)
        vectors = embed_texts(api_key, [document_embedding_text(item) for item in documents])
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM articles WHERE document_id = %s", (document_id,))
                inserted = insert_document_chunks(cur, documents, vectors)
    except Exception:
        delete_minio_object(str(minio_object.get("file_bucket") or ""), str(minio_object.get("file_object_key") or ""))
        raise

    if minio_object:
        cleanup_unreferenced_minio_objects(old_file_objects)
    return inserted[0]


def delete_document(id_or_document_id: str) -> dict[str, Any]:
    file_objects: list[tuple[str, str]] = []
    deleted_count = 0
    with db_connection() as conn:
        with conn.cursor() as cur:
            document_id = resolve_document_id(cur, id_or_document_id)
            if not document_id:
                return {"deleted": False, "deleted_count": 0}
            file_objects = fetch_document_file_objects(cur, document_id)
            cur.execute("DELETE FROM articles WHERE document_id = %s", (document_id,))
            deleted_count = cur.rowcount
    cleanup_unreferenced_minio_objects(file_objects)
    return {"deleted": deleted_count > 0, "deleted_count": deleted_count}


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
                SELECT id, document_id, source_id, title, source,
                       publisher, published_date, version, audience, topic, credibility,
                       content,
                       embedding <=> %s::vector AS distance
                FROM articles
                ORDER BY distance
                LIMIT %s
                """,
                (question_vector, REFERENCE_CANDIDATE_LIMIT),
            )
            rows = cur.fetchall()

    distances = [float(row[12]) for row in rows if row[12] is not None]
    best_distance = min(distances) if distances else None
    max_allowed_distance = MAX_REFERENCE_DISTANCE
    if best_distance is not None:
        max_allowed_distance = min(MAX_REFERENCE_DISTANCE, best_distance + REFERENCE_DISTANCE_MARGIN)

    references: list[Reference] = []
    seen_reference_keys: set[tuple[str, str, str]] = set()
    for row in rows:
        (id_, document_id, source_id, title, source,
         publisher, published_date, version, audience, topic, credibility,
         content, distance) = row
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
                document_id=str(document_id),
                source_id=int(source_id or 0),
                title=str(title or ""),
                source=str(source or ""),
                publisher=str(publisher or ""),
                published_date=str(published_date or ""),
                version=str(version or ""),
                audience=str(audience or ""),
                topic=str(topic or ""),
                credibility=str(credibility or ""),
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
            (
                f"[{ref.index}] 來源: {ref.source} | 標題: {ref.title} | source_id: {ref.source_id} "
                f"| 日期: {ref.published_date or '未填'} | 適用對象: {ref.audience or '未填'} "
                f"| 主題: {ref.topic or '未填'}\n{ref.content}"
            )
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


def list_conversations() -> list[dict]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id,
                       COALESCE(
                           (SELECT content FROM messages
                            WHERE conversation_id = c.id AND role = 'user'
                            ORDER BY created_at
                            LIMIT 1),
                           '新對話'
                       ) AS title,
                       c.created_at
                FROM conversations c
                ORDER BY c.created_at DESC
                LIMIT 50
                """,
            )
            rows = cur.fetchall()
    return [
        {"id": str(row[0]), "title": row[1][:60], "created_at": row[2].isoformat()}
        for row in rows
    ]


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
        retrieval_query = get_retrieval_query(api_key, question, history)
        retrieval_terms = retrieval_query.terms
        references = search_references(api_key, retrieval_query.question, retrieval_terms)
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
                "document_id": ref.document_id,
                "source_id": ref.source_id,
                "title": ref.title,
                "source": ref.source,
                "publisher": ref.publisher,
                "published_date": ref.published_date,
                "version": ref.version,
                "audience": ref.audience,
                "topic": ref.topic,
                "credibility": ref.credibility,
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
        if parsed.path == "/api/conversations":
            self.send_json({"conversations": list_conversations()})
            return
        if parsed.path.startswith("/api/conversations/"):
            conversation_id = unquote(parsed.path.removeprefix("/api/conversations/"))
            history = load_conversation_history(conversation_id)
            self.send_json({"messages": history})
            return
        if parsed.path.startswith("/api/"):
            self.send_error_json(404, "找不到路徑。")
            return
        self.send_static(parsed.path)
        return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/documents/metadata-suggestions":
                self.send_json({"metadata": infer_document_metadata(self.read_document_payload())})
                return
            if parsed.path == "/api/documents":
                inserted_documents = add_documents(self.read_document_payload())
                self.send_json({"inserted": inserted_documents, "document": inserted_documents[0], "documents": list_documents()}, status=201)
                return
            if parsed.path == "/api/ask":
                self.send_json(ask_question(self.read_json()))
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/documents/"):
                document_id = unquote(parsed.path.removeprefix("/api/documents/"))
                document = update_document(document_id, self.read_document_payload())
                self.send_json({"document": document, "documents": list_documents()})
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/documents/"):
                document_id = unquote(parsed.path.removeprefix("/api/documents/"))
                self.send_json(delete_document(document_id))
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
                upload = {
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "data": data,
                }
                payload.setdefault("uploads", []).append(upload)
                payload["upload"] = upload
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
