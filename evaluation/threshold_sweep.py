"""Replay synthetic representation candidates at fixed thresholds without network calls."""
import argparse
import json
from pathlib import Path

from evaluation.retrieval_baseline import metrics
from medivector.experiment_snapshot import digest
from medivector.models import Reference
from medivector.retrieval import filter_references


def sweep(report, packet):
    if (report.get('report_kind') != 'unreviewed_representation_comparison' or
            report.get('verified_baseline') is not False or packet.get('review_status') != 'pending_human'):
        raise ValueError('Only unreviewed representation comparisons are supported')
    if report['candidate_sha256'] != digest(packet):
        raise ValueError('Candidate packet differs from the measured run')
    cases = {case['id']: case for case in packet['cases']}
    rows = []
    for group in report['groups']:
        if {r['case_id'] for r in group['runs']} != set(cases) or len(group['runs']) != len(cases):
            raise ValueError('Measured cases differ from packet')
        for maximum in (0.35, 0.45, 0.55, 0.65):
            for margin in (0.06, 0.12):
                scores = []
                for run in group['runs']:
                    refs = [Reference(**r) for r in run['raw_candidates']]
                    selected = filter_references(refs, top_k=5, max_distance=maximum, distance_margin=margin)
                    score = metrics(cases[run['case_id']], [
                        {'document_id': r.document_id, 'chunk_metadata': r.chunk_metadata} for r in selected], 5)
                    scores.append(score)
                answerable = [s for s in scores if s['answerable']]
                unanswered = [s for s in scores if not s['answerable']]
                rows.append({'variant': group['variant'], 'max_distance': maximum, 'distance_margin': margin,
                             'answerable_cases': len(answerable), 'answerable_hits': sum(s['hit'] for s in answerable),
                             'unanswerable_cases': len(unanswered),
                             'unanswerable_with_candidates': sum(s['returned_any'] for s in unanswered)})
    return {'report_kind': 'unreviewed_threshold_sweep', 'verified_baseline': False,
            'release_gate_eligible': False, 'input_report_sha256': digest(report),
            'candidate_sha256': digest(packet), 'rows': rows,
            'limitations': 'Reuses exactly the saved candidate distances; no new embedding or generation. '
            'Unreviewed synthetic labels only. Tuning and measuring on the same cases is exploratory, '
            'not a validated threshold choice. A returned candidate does not establish an incorrect answer.'}


def markdown(report):
    lines = ['# 距離門檻敏感度（重播合成檢索結果）', '', report['limitations'], '',
             '| 表示法 | 距離上限 | margin | 提議可回答題命中 | 提議無答案題仍返回候選 |',
             '|---|---:|---:|---:|---:|']
    for row in report['rows']:
        lines.append(f"| {row['variant']} | {row['max_distance']} | {row['distance_margin']} | "
                     f"{row['answerable_hits']}/{row['answerable_cases']} | "
                     f"{row['unanswerable_with_candidates']}/{row['unanswerable_cases']} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('candidates', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use fresh report paths')
    report = sweep(json.loads(args.report.read_text()), json.loads(args.candidates.read_text()))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    with args.output.with_suffix('.md').open('x', encoding='utf-8') as stream:
        stream.write(markdown(report))


if __name__ == '__main__':
    main()
