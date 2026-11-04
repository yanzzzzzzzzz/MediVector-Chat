"""Backwards-compatible CLI for the shared runtime chunking strategies."""
from medivector.chunking import chunk_manifest, main, page_text

__all__ = ["chunk_manifest", "main", "page_text"]

if __name__ == "__main__":
    main()
