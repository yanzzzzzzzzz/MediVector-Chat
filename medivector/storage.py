import time
import traceback
import uuid as uuidlib
from io import BytesIO
from typing import Any

from .config import MINIO_ACCESS_KEY, MINIO_BUCKET, MINIO_ENDPOINT, MINIO_SECRET_KEY, MINIO_SECURE
from .text_processing import sanitize_filename


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
