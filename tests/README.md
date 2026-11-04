# Tests

Use Python 3.11+ (matching the project's async deadline support) and install all evaluation dependencies:

```sh
python -m pip install -r evaluation/requirements.txt
python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base")'
python -m unittest discover -s tests -v
```

The tokenizer dictionary is downloaded once; set TIKTOKEN_CACHE_DIR for a writable/offline cache.
No OpenAI API Key is needed. Calls to OpenAI are mocked. The default command skips three tests that
need a real PostgreSQL service. Tests cover retrieval schemas/ranking/filtering, authorization and
body/rate limits, baseline/token chunking, existing chat behavior (including disabled RAG, emergency
diversion and generation failure), citation annotations, metrics and bounded retries/deadlines.

For the complete suite, use a disposable pgvector database. Tests initialize extensions and tables,
create randomized principal schemas and drop those test schemas. Never target production:

```sh
docker run --rm --name medivector-tests -d -p 127.0.0.1:55439:5432 \
  -e POSTGRES_PASSWORD=test-only-password pgvector/pgvector:pg16
# Wait for: docker exec medivector-tests pg_isready -U postgres
RUN_DB_TESTS=1 PG_HOST=127.0.0.1 PG_PORT=55439 PG_USER=postgres \
  PG_PASSWORD=test-only-password PG_DATABASE=postgres \
  python -m unittest discover -s tests -v
docker stop medivector-tests
```

DB tests verify actual document/conversation/retrieval isolation and cross-account deletion,
versioned manifest import with refusal to overwrite, and distinct Exact/HNSW execution plans.
Each integration test initializes its own prerequisites and can be run independently.

Frontend tests use Node's built-in test runner and native TypeScript stripping (Node 24+):

```sh
cd frontend/medivector-chat-app
pnpm install --frozen-lockfile --ignore-scripts
pnpm test
pnpm run lint
pnpm run build
```

The HTTP client tests stub fetch and sessionStorage. They check Token headers, caller-header preservation,
anonymous local mode, multipart boundaries and server errors without sending network requests.
The production build includes Vue/TypeScript type checking. CI runs these commands automatically on
push/pull requests and runs all backend tests on Python 3.11 and 3.12 against disposable pgvector services.
