"""Import chunk manifests into a fresh experiment principal schema, never the baseline."""
import argparse
import json
import uuid
from pathlib import Path

from medivector.api_auth import Principal, current_principal
from medivector.db import db_connection, init_tables
from medivector.documents import insert_document_chunks
from medivector.openai_client import embed_texts, require_openai_api_key


def index_manifests(manifests: list[dict], experiment: str):
    if not experiment or not manifests:
        raise ValueError("A new experiment ID and at least one manifest are required")
    principal = Principal("experiment:" + experiment, "admin")
    documents = []
    for manifest in manifests:
        for chunk in manifest["chunks"]:
            documents.append({
                "document_id": str(uuid.uuid5(uuid.NAMESPACE_URL, manifest["document_id"])),
                "title": manifest["document_id"], "source": "chunk-experiment",
                "version": manifest["version"], "content": chunk["content"],
                "chunk_index": chunk["chunk_index"], "chunk_count": len(manifest["chunks"]),
                "chunk_metadata": {**{k: v for k, v in chunk.items() if k != "content"}, "source_sha256": manifest["source_sha256"],
                                   "original_document_id": manifest["document_id"],
                                   "version": manifest["version"], "strategy": manifest["strategy"]},
            })
    if not documents:
        raise ValueError("Manifests contain no chunks")
    # Lock held on a separate session until the new schema import is committed.
    with db_connection() as guard, guard.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (principal.schema,))
        try:
            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (principal.schema,))
            if cur.fetchone():
                raise ValueError("Experiment already exists; choose a new experiment ID")
            vectors = embed_texts(require_openai_api_key(), [d["content"] for d in documents])
            if len(vectors) != len(documents):
                raise ValueError("Embedding count mismatch")
            token = current_principal.set(principal)
            try:
                init_tables()
                with db_connection() as conn, conn.cursor() as writer:
                    inserted = insert_document_chunks(writer, documents, vectors)
            finally:
                current_principal.reset(token)
            return {"principal": principal.name, "schema": principal.schema, "chunks": len(inserted)}
        finally:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (principal.schema,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", type=Path, nargs="+")
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args()
    print(json.dumps(index_manifests([json.loads(p.read_text()) for p in args.manifests], args.experiment)))


if __name__ == "__main__":
    main()
