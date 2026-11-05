"""Compare one allowed scope with the union of explicitly authorized scopes; never disable API ACLs."""
import argparse
import json
import os
from pathlib import Path
import httpx


def compare(client, request):
    question = request['question'].strip()
    scopes = request['scopes']
    target = request['target']
    k = request.get('top_k', 5)
    keys = [(s['branch_id'], s['department_id']) for s in scopes]
    if any(set(scope) != {'branch_id', 'department_id'} for scope in scopes) or set(target) != {'branch_id', 'department_id'}:
        raise ValueError('Scope objects must contain only branch_id and department_id')
    if not question or type(k) is not int or not 1 <= k <= 1000 or len(scopes) < 2 or len(scopes) > 20 or len(set(keys)) != len(keys) or target not in scopes:
        raise ValueError('Use 2–20 unique scopes including target, a question and K in 1–1000')
    manifests = []
    for scope in scopes:
        response = client.get('/api/knowledge/corpus-manifest', params=scope)
        response.raise_for_status()
        manifests.append(response.json())
    models = {m['embedding_model'] for m in manifests}
    if len(models) != 1:
        raise ValueError('All scope comparisons must use the same embedding model')
    runs = []
    for scope in scopes:
        response = client.post('/api/retrieval/search', json={**scope, 'question': question, 'mode': 'raw',
                               'top_k': k, 'candidate_limit': max(20, k), 'query_expansion': False})
        response.raise_for_status()
        retrieval = response.json()
        if retrieval['settings']['embedding_model'] not in models or retrieval['standalone_query'] != question or retrieval['terms']:
            raise ValueError('Model/query/terms changed during controlled scope comparison')
        runs.append({'scope': scope, 'retrieval': retrieval})
    for scope, before in zip(scopes, manifests):
        response = client.get('/api/knowledge/corpus-manifest', params=scope)
        response.raise_for_status()
        if response.json()['manifest_sha256'] != before['manifest_sha256']:
            raise ValueError('Authorized corpus changed during scope comparison; retry on a frozen corpus')
    union = {}
    for run in runs:
        for ref in run['retrieval']['results']:
            key = ref['chunk_id']
            if key not in union:
                union[key] = {**ref, 'authorized_scopes': []}
            union[key]['authorized_scopes'].append(run['scope'])
    candidates = sorted(union.values(), key=lambda ref: (ref['distance'], ref['document_id'], ref['chunk_id']))[:k]
    for rank, ref in enumerate(candidates, 1):
        ref['union_rank'] = rank
    selected = next(run['retrieval']['results'] for run in runs if run['scope'] == target)
    return {'format_version': 1, 'question': question, 'target': target, 'top_k': k, 'embedding_model': next(iter(models)),
            'manifests': manifests, 'scoped_results': selected, 'authorized_union_results': candidates, 'runs': runs,
            'limitations': 'Union is assembled only from separately authorized API scopes; approval, validity, organization and ACL filters are never disabled. Query expansion is off and corpus manifests are checked before/after. This is a scope diagnostic, not a reviewed Recall baseline or semantic correctness score.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use fresh report paths')
    token = os.getenv('EVALUATION_API_TOKEN')
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=180) as client:
        report = compare(client, json.loads(args.request.read_text()))
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    lines = ['# Authorized scope comparison', '', report['limitations'], '',
             '| Result set | Rank | Document | Version | Distance |', '|---|---:|---|---|---:|']
    for name in ('scoped_results', 'authorized_union_results'):
        for rank, ref in enumerate(report[name], 1):
            lines.append(f"| {name} | {rank} | {ref['document_id']} | {ref['document_version_id']} | {ref['distance']} |")
    with args.output.with_suffix('.md').open('x') as stream:
        stream.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
