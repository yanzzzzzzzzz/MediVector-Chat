"""Offline deterministic source-governance rules. No network, model calls or semantic guessing."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

NO_EVIDENCE_ANSWERS = {
    '沒有可用核准資料，無法確認院所規範。',
    '目前沒有符合此院區、科別且已核准有效的參考資料，無法確認院所規範。請向院方專業人員確認。',
}
LIMITATIONS = ('Rules validate a supplied frozen source catalog, not its authenticity or clinical correctness. '
               'Semantic support needs explicit reviewer annotations; unknown support is Review Required. '
               'Synthetic negative fixtures are regression tests, not a human-reviewed medical baseline.')


def timestamp(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('Evaluation timestamps must include a timezone')
    return at


def evaluate_case(case, catalog):
    context, trace = case['context'], case['trace']
    if not isinstance(case['answerable'], bool):
        raise ValueError('answerable must be boolean')
    if case['answerable'] != bool(case['expectedDocumentVersionIds']):
        raise ValueError('Expected version labels must agree with answerability')
    at = timestamp(context['query_at'])
    checks = []
    def result(rule, status, reason, ref=None):
        checks.append({'rule_id': rule, 'status': status, 'reason': reason,
                       'document_id': (ref or {}).get('document_id'),
                       'version_id': (ref or {}).get('document_version_id'),
                       'chunk_id': (ref or {}).get('uuid')})
    references = trace['references']
    expected = set(case['expectedDocumentVersionIds'])
    indices = set()
    for ref in references:
        version_id = ref.get('document_version_id')
        version = catalog.get(version_id)
        if not version:
            result('citation.identity', 'Fail', 'Version is absent from frozen source catalog', ref)
            continue
        identity = ref['document_id'] == version['document_id'] and ref['uuid'] in version['chunk_ids']
        result('citation.identity', 'Pass' if identity else 'Fail', 'Document/version/chunk binding', ref)
        effective = version['status'] == 'approved' and timestamp(version['effective_from']) <= at and (version['effective_until'] is None or at < timestamp(version['effective_until']))
        result('citation.effective_version', 'Pass' if effective else 'Fail', 'Only approved versions effective at query time are allowed', ref)
        allowed = (version['organization_id'] == context['organization_id']
                   and {'branch_id': context['branch_id'], 'department_id': context['department_id']} in version['scopes']
                   and context['role'] in version['allowed_roles']
                   and (not version['allowed_users'] or context['principal'] in version['allowed_users']))
        result('citation.scope_acl', 'Pass' if allowed else 'Fail', 'Organization, branch, department, role and named-user ACL', ref)
        result('citation.expected_version', 'Pass' if version_id in expected else 'Fail', 'Citation must match labelled expected versions', ref)
        if not isinstance(ref.get('index'), int) or ref['index'] < 1 or ref['index'] in indices:
            result('citation.index', 'Fail', 'Missing, invalid or duplicate citation index', ref)
        indices.add(ref.get('index'))
    cited = {int(i) for i in re.findall(r'\[(?:索引\s*)?(\d+)\]', trace['answer'])}
    result('citation.answer_indices', 'Fail' if cited - indices else 'Pass', f'Unknown answer indices: {sorted(cited - indices)}')
    if case['answerable'] and not references:
        result('retrieval.expected_evidence', 'Fail', 'Answerable case returned no expected evidence')
    if case['answerable'] and references and not cited:
        result('citation.coverage', 'Fail', 'Answer lacks citation markers; paragraph support still needs review')
    review = case.get('support_review')
    reviewed = isinstance(review, dict) and bool(review.get('reviewer')) and bool(review.get('reviewed_at'))
    if reviewed:
        timestamp(review['reviewed_at'])
    if not case['answerable']:
        if not references and trace['answer'].strip() in NO_EVIDENCE_ANSWERS:
            result('answer.no_evidence', 'Pass', 'Canonical refusal, no cited institution rules')
        elif reviewed and review.get('verdict') == 'unsupported':
            result('answer.no_evidence', 'Fail', 'Reviewer-labelled invented or unsupported institution rule')
        else:
            result('answer.no_evidence', 'Review Required', 'Noncanonical response needs review; do not infer safe abstention')
    else:
        verdict = review.get('verdict') if reviewed else None
        result('answer.semantic_support', {'supported': 'Pass', 'unsupported': 'Fail'}.get(verdict, 'Review Required'),
               'Support is reviewer-supplied, never inferred from distance/count or citation existence')
    outcome = 'Fail' if any(c['status'] == 'Fail' for c in checks) else ('Review Required' if any(c['status'] == 'Review Required' for c in checks) else 'Pass')
    return {'case_id': case['id'], 'question': case['question'], 'status': outcome,
            'expected_rule_outcome': case.get('expected_rule_outcome'), 'checks': checks, 'trace': trace, 'context': context}


def evaluate_suite(dataset):
    if dataset.get('format_version') != 1 or not dataset.get('dataset_version') or not dataset.get('corpus_version'):
        raise ValueError('A versioned medical-rule dataset is required')
    cases = dataset['cases']
    if not cases or len({case['id'] for case in cases}) != len(cases):
        raise ValueError('Cases need unique stable IDs')
    results = [evaluate_case(case, dataset['source_catalog']) for case in cases]
    return {'format_version': 1, 'dataset_version': dataset['dataset_version'],
            'corpus_version': dataset['corpus_version'],
            'dataset_sha256': hashlib.sha256(json.dumps(dataset, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'summary': {s: sum(r['status'] == s for r in results) for s in ('Pass', 'Fail', 'Review Required')},
            'results': results, 'limitations': LIMITATIONS}


def markdown(report):
    lines = ['# Medical source rules', '', report['limitations'], '',
             '| Case | Outcome | Rule | Version | Reason |', '|---|---|---|---|---|']
    for row in report['results']:
        for check in row['checks']:
            lines.append('| ' + ' | '.join(str(value or '').replace('|', '\\|').replace('\n', ' ') for value in
                         (row['case_id'], row['status'], check['rule_id'] + ': ' + check['status'], check['version_id'], check['reason'])) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = evaluate_suite(json.loads(args.dataset.read_text()))
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use fresh report paths')
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    with args.output.with_suffix('.md').open('x') as stream:
        stream.write(markdown(report))


if __name__ == '__main__':
    main()
