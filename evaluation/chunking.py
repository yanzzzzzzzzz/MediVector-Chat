"""Versioned, non-destructive chunk manifests for controlled offline experiments."""
import argparse
import hashlib
import json
from pathlib import Path

from medivector.text_processing import split_text_for_embedding


def page_text(file_bytes: bytes) -> tuple[str, list[dict]]:
    from io import BytesIO
    from pypdf import PdfReader
    pages, parts, offset = [], [], 0
    for number, page in enumerate(PdfReader(BytesIO(file_bytes)).pages, 1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        if parts:
            offset += 2
        pages.append({"page": number, "start": offset, "end": offset + len(text)})
        parts.append(text)
        offset += len(text)
    return "\n\n".join(parts), pages


def chunk_manifest(text: str, *, document_id: str, version: str, strategy: str = "baseline",
                   max_chars: int = 6000, max_tokens: int = 512, overlap: int = 64,
                   pages: list[dict] | None = None) -> dict:
    if not document_id or not version or max_chars < 1 or max_tokens < 4 or not 0 <= overlap < max_tokens:
        raise ValueError("Invalid chunk configuration")
    digest = hashlib.sha256(text.encode()).hexdigest()
    chunks = []
    if strategy == "baseline":
        # The legacy algorithm normalizes whitespace; retain exact source spans where possible.
        cursor = 0
        for content in split_text_for_embedding(text, max_chars=max_chars):
            start = text.find(content, cursor)
            if start >= 0:
                end = start + len(content)
            else:
                positions = []
                for part in content.split("\n\n"):
                    found = text.find(part, cursor)
                    if found < 0:
                        raise ValueError("Cannot map baseline chunk to source")
                    positions.append((found, found + len(part)))
                    cursor = found + len(part)
                start, end = positions[0][0], positions[-1][1]
            chunks.append({"content": content, "start": start, "end": end,
                           "whitespace_normalized": text[start:end] != content})
            cursor = end
    elif strategy == "token":
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        start = 0
        # Start with at most max_tokens characters; shrink until the actual BPE budget fits.
        # Cut only at Unicode character boundaries, never decode partial UTF-8 tokens.
        while start < len(text):
            end = min(len(text), start + max_tokens)
            while len(encoder.encode(text[start:end], disallowed_special=())) > max_tokens:
                end -= 1
            if end <= start:
                raise ValueError("Token budget cannot fit one character")
            content = text[start:end]
            chunks.append({"content": content, "start": start, "end": end,
                           "token_count": len(encoder.encode(content, disallowed_special=()))})
            if end == len(text):
                break
            next_start = end
            while next_start > start + 1 and len(encoder.encode(text[next_start - 1:end], disallowed_special=())) <= overlap:
                next_start -= 1
            start = next_start
    else:
        raise ValueError("Unknown strategy")
    for index, chunk in enumerate(chunks, 1):
        chunk.update({"document_id": document_id, "chunk_index": index,
                      "chunk_id": f"{document_id}:{version}:{strategy}:{index}",
                      "pages": [p["page"] for p in pages or [] if p["start"] < chunk["end"] and p["end"] > chunk["start"]]})
    return {"document_id": document_id, "version": version, "source_sha256": digest,
            "strategy": strategy, "max_chars": max_chars, "max_tokens": max_tokens,
            "overlap_tokens": overlap, "encoding": "cl100k_base" if strategy == "token" else None,
            "offset_unit": "unicode_codepoint", "text": text, "pages": pages or [], "chunks": chunks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--strategy", choices=["baseline", "token"], default="baseline")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=64)
    args = parser.parse_args()
    if args.source.suffix.lower() == ".pdf":
        text, pages = page_text(args.source.read_bytes())
    else:
        text, pages = args.source.read_text(encoding="utf-8"), []
    manifest = chunk_manifest(text, document_id=args.document_id, version=args.version,
                              strategy=args.strategy, max_tokens=args.max_tokens, overlap=args.overlap, pages=pages)
    # Exclusive creation protects existing experiment versions and baseline artifacts.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
