"""Offline release gate. Fail cannot be overridden; review approvals bind the exact report hash."""
import argparse
import json
from pathlib import Path
from medivector.experiment_snapshot import build_snapshot, digest
from medivector.quality_rules import timestamp, evaluate_case


def evaluate_gate(report, approval=None):
    rules = report.get('medical_rules', report)
    results = rules.get('results', [])
    if not results:
        raise ValueError('No medical rule results; refusing an empty green gate')
    catalog = rules.get('source_catalog')
    if not isinstance(catalog, dict):
        raise ValueError('Frozen source catalog is required to replay the checks')
    statuses = []
    for result in results:
        checks = result.get('checks', [])
        if not checks or any(c.get('status') not in {'Pass', 'Fail', 'Review Required'} for c in checks):
            raise ValueError('Missing or invalid rule checks')
        # Derive from individual checks, never trust a supplied summary or expected fixture outcome.
        actual = 'Fail' if any(c['status'] == 'Fail' for c in checks) else ('Review Required' if any(c['status'] == 'Review Required' for c in checks) else 'Pass')
        replay = evaluate_case({**result, 'id': result['case_id']}, catalog)
        if replay['status'] != actual or replay['checks'] != checks:
            raise ValueError('Rule checks do not match a replay of the frozen trace')
        if actual != result.get('status'):
            raise ValueError('Rule result contradicts its checks')
        statuses.append(actual)
    snapshot = report.get('snapshot')
    if approval is not None and snapshot is None:
        raise ValueError('Freeze the experiment snapshot in the input report before approval')
    if snapshot is None:
        dataset = report.get('dataset', {})
        snapshot = build_snapshot(report.get('corpus_manifest', rules.get('source_catalog', {})),
                                  test_dataset_version=dataset.get('dataset_version', rules.get('dataset_version')),
                                  index_version=dataset.get('index_version'), chat_model=dataset.get('chat_model'),
                                  embedding_model=dataset.get('embedding_model'), retriever=dataset.get('retriever'))
    reasons = []
    if snapshot.get('corpus_sha256') != digest(snapshot.get('corpus')):
        raise ValueError('Snapshot corpus hash does not match its data')
    if 'Fail' in statuses:
        state = 'Fail'
        reasons.append('At least one deterministic or reviewed semantic rule failed; approval cannot override it')
    else:
        if 'Review Required' in statuses:
            reasons.append('Rule outcomes require human review')
        if snapshot.get('git_sha') == 'unknown' or snapshot.get('working_tree_dirty') is True:
            reasons.append('Build identity is missing or includes uncommitted changes')
        if not snapshot.get('test_dataset_version') or not snapshot.get('index', {}).get('version'):
            reasons.append('Dataset/index version is not frozen')
        if not snapshot.get('corpus') or not snapshot.get('prompt_versions'):
            reasons.append('Corpus/prompt snapshot is incomplete')
        state = 'Review Required' if reasons else 'Pass'
    report_hash = digest(report)
    accepted = None
    if approval is not None:
        if approval.get('report_sha256') != report_hash:
            raise ValueError('Approval does not match this exact report')
        if approval.get('role') not in {'reviewer', 'admin'} or not str(approval.get('reviewer', '')).strip() or not str(approval.get('reason', '')).strip() or approval.get('decision') != 'approve':
            raise ValueError('Explicit reviewer/admin approval with a reason is required')
        timestamp(approval['reviewed_at'])
        if state != 'Fail':
            accepted = approval
            state = 'Pass'
    return {'format_version': 1, 'status': state, 'release_allowed': state == 'Pass',
            'report_sha256': report_hash, 'snapshot': snapshot, 'reasons': reasons,
            'manual_approval': accepted,
            'limitations': 'CLI approval is a trusted operator artifact, not an identity provider. Protect approval files/CI environments. Online publication separately enforces authenticated Reviewer/Admin authorization. External models are nondeterministic.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    approval = json.loads(args.approval.read_text()) if args.approval else None
    result = evaluate_gate(report, approval)
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use a fresh gate report path')
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    with args.output.with_suffix('.md').open('x') as stream:
        stream.write(f"# Release quality gate\n\nStatus: **{result['status']}**\n\nReport SHA256: `{result['report_sha256']}`\n\n")
        stream.write('\n'.join('- ' + reason for reason in result['reasons']) + '\n\n' + result['limitations'] + '\n')
    raise SystemExit(0 if result['release_allowed'] else (2 if result['status'] == 'Fail' else 3))


if __name__ == '__main__':
    main()
