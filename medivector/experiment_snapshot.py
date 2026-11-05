"""Allowlisted reproducibility metadata; never serialize environment variables or credentials."""
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from . import config

ROOT = Path(__file__).parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':')).encode()).hexdigest()


def source_build():
    sha = os.getenv('APP_GIT_SHA', 'unknown')
    dirty = None
    if (ROOT / '.git').exists():
        try:
            sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
            dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip())
        except (OSError, subprocess.CalledProcessError):
            pass
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        sha = 'unknown'
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for pattern in ('*.py', 'migrations/*.sql') for p in sorted((ROOT / 'medivector').glob(pattern))}
    return {'git_sha': sha, 'working_tree_dirty': dirty, 'source_sha256': digest(files)}


def build_snapshot(corpus, *, test_dataset_version=None, index_version=None, chat_model=None,
                   embedding_model=None, retriever=None, generation=None):
    prompts = {name: hashlib.sha256((ROOT / 'medivector' / name).read_bytes()).hexdigest()
               for name in ('chat.py', 'retrieval.py', 'education.py')}
    return {'format_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            **source_build(), 'corpus': corpus, 'corpus_sha256': digest(corpus),
            'embedding_model': embedding_model or config.EMBEDDING_MODEL,
            'embedding_dimensions': config.EMBEDDING_DIM, 'chat_model': chat_model,
            'query_expansion_model': config.QUERY_EXPANSION_MODEL, 'prompt_versions': prompts,
            'generation_parameters': generation,
            'retriever': retriever or {'top_k': config.TOP_K, 'candidate_limit': config.REFERENCE_CANDIDATE_LIMIT,
                                      'max_distance': config.MAX_REFERENCE_DISTANCE, 'distance_margin': config.REFERENCE_DISTANCE_MARGIN,
                                      'dedup': True, 'query_expansion': True},
            'index': {'version': index_version, 'institutional_strategy': 'exact_over_authorized_subset',
                      'legacy_strategy': 'postgres_planner_exact_or_hnsw'},
            'test_dataset_version': test_dataset_version,
            'limitations': 'External model responses are nondeterministic. Missing Git SHA/dataset version requires explicit review. Source code digest supplements build identity; no API keys or raw personal questions are recorded.'}
