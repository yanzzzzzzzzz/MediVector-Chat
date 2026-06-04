import json
import os
import time
import uuid as uuidlib
from datetime import date
from typing import Any

import psycopg

from .config import RISK_MODEL
from .db import db_connection
from .openai_client import embed_texts, openai_post, require_openai_api_key
from .storage import delete_minio_object, save_upload_to_minio
from .text_processing import document_embedding_text, extract_upload_text, serialize_embedding, split_text_for_embedding


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


def validate_filter_date(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    try:
        date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label}請使用 YYYY-MM-DD 格式。") from exc
    return cleaned


def normalized_document_filters(q: str = "", date_from: str = "", date_to: str = "") -> dict[str, str]:
    filters = {
        "q": str(q or "").strip(),
        "date_from": validate_filter_date(str(date_from or ""), "起始日期"),
        "date_to": validate_filter_date(str(date_to or ""), "結束日期"),
    }
    if filters["date_from"] and filters["date_to"] and filters["date_from"] > filters["date_to"]:
        raise ValueError("起始日期不可晚於結束日期。")
    return filters


def document_filter_clause(filters: dict[str, str]) -> tuple[str, list[Any]]:
    conditions = ["TRUE"]
    params: list[Any] = []
    if filters["q"]:
        pattern = f"%{filters['q']}%"
        searchable_columns = (
            "title",
            "source",
            "publisher",
            "audience",
            "topic",
            "credibility",
            "content",
            "file_name",
        )
        conditions.append("(" + " OR ".join(f"{column} ILIKE %s" for column in searchable_columns) + ")")
        params.extend(pattern for _ in searchable_columns)

    if filters["date_from"]:
        conditions.append("published_date <> '' AND published_date >= %s")
        params.append(filters["date_from"])
    if filters["date_to"]:
        conditions.append("published_date <> '' AND published_date <= %s")
        params.append(filters["date_to"])

    return " AND ".join(conditions), params


def list_documents(q: str = "", date_from: str = "", date_to: str = "") -> list[dict[str, Any]]:
    filters = normalized_document_filters(q, date_from, date_to)
    filter_active = any(filters.values())
    where_clause, filter_params = document_filter_clause(filters)
    with db_connection() as conn:
        with conn.cursor() as cur:
            if filter_active:
                cur.execute(f"""
                    WITH matched_documents AS (
                        SELECT document_id, MAX(updated_at) AS last_updated, MAX(created_at) AS last_created
                        FROM articles
                        WHERE {where_clause}
                        GROUP BY document_id
                        ORDER BY last_updated DESC, last_created DESC, document_id
                        LIMIT 500
                    )
                    SELECT id, document_id, source_id, title, source,
                           publisher, published_date, version, audience, topic, credibility,
                           content,
                           file_name, file_object_key, file_bucket, file_content_type, file_size,
                           chunk_index, chunk_count, embedding, created_at, updated_at
                    FROM articles
                    WHERE document_id IN (SELECT document_id FROM matched_documents)
                    ORDER BY updated_at DESC, created_at DESC, document_id, chunk_index
                """, filter_params)
            else:
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
