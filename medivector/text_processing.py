import os
import re
from io import BytesIO
from typing import Any

from .config import MAX_EMBEDDING_CHARS


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
