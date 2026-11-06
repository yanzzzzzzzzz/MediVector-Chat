"""Unreviewed synthetic engineering runs; deliberately incompatible with verified baseline exports."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from evaluation.retrieval_baseline import collect_runs
from medivector.experiment_snapshot import build_snapshot, digest

LIMITATIONS = (
    'Candidate labels have NOT been human reviewed. All relevance scores are provisional comparisons '
    'against proposed labels, not verified Recall or clinical quality. No answer generation or semantic '
    'faithfulness is measured. Raw nearest-neighbor returns do not establish answerability. '
    'K=3/5/10 reuse one max-K result; a tiny corpus cannot distinguish those K settings. '
    'Sequential latency includes embedding/provider variability; raw expansion runs include rewrite cost '
    'while filtered runs replay the rewrite, so their latency is not a causal raw-vs-filter speed comparison. '
    'This report is not eligible for a release gate or the independent Lab verified-baseline command.'
)


def validate_candidate_packet(packet):
    if packet.get('review_status') != 'pending_human':
        raise ValueError('This diagnostic only accepts explicitly pending-human candidate packets')
    if not all(packet.get(key) for key in ('dataset_version', 'corpus_version', 'index_version', 'embedding_model', 'notice')):
        raise ValueError('Freeze and describe the synthetic candidate corpus first')
    context = packet.get('retrieval_context')
    if not isinstance(context, dict) or set(context) != {'branch_id', 'department_id'} or not all(context.values()):
        raise ValueError('Diagnostic requires an explicit institution scope; identity/ACL cannot be overridden')
    cases = packet.get('cases', [])
    if not cases or len({case['id'] for case in cases}) != len(cases):
        raise ValueError('Cases must have stable unique IDs')
    for case in cases:
        if not isinstance(case.get('query'), str) or not case['query'].strip() or not isinstance(case.get('answerable'), bool):
            raise ValueError('Each case needs a query and proposed boolean answerability')
        if not isinstance(case.get('relevant_document_ids'), list) or bool(case['relevant_document_ids']) != case['answerable']:
            raise ValueError('Proposed labels must be structurally consistent')
        if case.get('reviewed_by') or case.get('reviewed_at'):
            raise ValueError('Keep reviewed cases separate; do not mix review states')


def diagnose(client, packet, progress=None):
    validate_candidate_packet(packet)
    manifest, experiments = collect_runs(client, packet, progress)
    by_id = {case['id']: case for case in packet['cases']}
    review = {}
    groups = []
    for experiment in experiments:
        converted = []
        for run in experiment['runs']:
            converted.append({'case_id': run['case_id'], 'retrieval': run['retrieval'], 'proposed_label_scores': run['metrics']})
            score = run['metrics']['10']
            # Raw candidates for no-answer questions are expected, not a hallucination failure.
            if experiment['mode'] == 'filtered':
                reasons = []
                if score['answerable'] and score['recall'] < 1:
                    reasons.append('proposed relevant document missing after filtering')
                if score['answerable'] and score.get('evidence_recall') is not None and score['evidence_recall'] < 1:
                    reasons.append('proposed evidence span not covered')
                if not score['answerable'] and score['returned_any']:
                    reasons.append('filtered candidates returned for a proposed no-answer question; relevance needs review')
                if reasons:
                    case = by_id[run['case_id']]
                    entry = review.setdefault(case['id'], {'case_id': case['id'], 'question': case['query'], 'proposed_answerable': case['answerable'], 'observations': [], 'human_review': 'pending'})
                    entry['observations'].append({'query_expansion': experiment['query_expansion'], 'reasons': reasons,
                                                  'references': [{k: ref.get(k) for k in ('document_id', 'document_version_id', 'chunk_id', 'distance', 'rank')} for ref in run['retrieval']['results']],
                                                  'settings': run['retrieval']['settings']})
        groups.append({'mode': experiment['mode'], 'query_expansion': experiment['query_expansion'],
                       'proposed_label_summary': experiment['summary'], 'p50_ms': experiment['p50_ms'],
                       'p95_ms': experiment['p95_ms'], 'runs': converted})
    chunk_count = sum(len(version['chunk_ids']) for version in manifest['versions'])
    return {'format_version': 1, 'report_kind': 'unreviewed_synthetic_diagnostic',
            'created_at': datetime.now(timezone.utc).isoformat(), 'verified_baseline': False,
            'release_gate_eligible': False, 'human_review_complete': False,
            'candidate_packet': packet, 'candidate_sha256': digest(packet), 'corpus_manifest': manifest,
            'corpus_size': {'versions': len(manifest['versions']), 'chunks': chunk_count},
            'k_comparison_limited': chunk_count < 10, 'groups': groups,
            'review_queue': list(review.values())[:5], 'review_queue_total': len(review),
            'snapshot': build_snapshot(manifest, test_dataset_version=None, index_version=packet['index_version'],
                                       embedding_model=packet['embedding_model'],
                                       retriever={'mode': 'synthetic_diagnostic', 'k': [3, 5, 10], 'query_expansion': [False, True], 'human_labels': False}),
            'limitations': LIMITATIONS}


def markdown(report):
    lines = ['# 合成資料工程診斷（未經人工審查，不是正式 baseline）', '', report['limitations'], '',
             f"文件版本：{report['corpus_size']['versions']}；chunks：{report['corpus_size']['chunks']}。",
             '以下分數只與候選標註比較，不代表人工確認的檢索品質。', '',
             '| Mode | 改寫 | K | 暫定 Recall | 暫定 MRR | 暫定 Hit | 暫定證據覆蓋 | 提議無答案題仍返回候選 | P50 ms | P95 ms |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for group in report['groups']:
        for k, score in group['proposed_label_summary'].items():
            values = [group['mode'], group['query_expansion'], k, score['recall'], score['mrr'], score['hit'],
                      score['evidence_recall'], score['unanswerable_return_rate'], round(group['p50_ms'], 1), round(group['p95_ms'], 1)]
            lines.append('| ' + ' | '.join(str(v) for v in values) + ' |')
    lines += ['', '## 待人工核對的觀察', '', '下列是與候選標註的差異，不是已確認的醫療錯誤或失敗根因。']
    for case in report['review_queue']:
        lines += ['', f"### {case['case_id']}：{case['question']}"]
        for observation in case['observations']:
            lines.append(f"- 改寫 {observation['query_expansion']}：" + '; '.join(observation['reasons']))
            for ref in observation['references']:
                lines.append(f"  - 版本 `{ref['document_version_id']}`，distance={ref['distance']}")
    if not report['review_queue']:
        lines.append('本次沒有符合佇列條件的觀察；不捏造五個失敗案例。')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidates', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--acknowledge-synthetic-data', action='store_true', required=True,
                        help='Confirm inputs are authorized nonpersonal synthetic engineering examples')
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use fresh diagnostic report paths')
    packet = json.loads(args.candidates.read_text())
    headers = {'Authorization': 'Bearer ' + os.environ['EVALUATION_API_TOKEN']} if os.getenv('EVALUATION_API_TOKEN') else {}
    def progress(mode, expansion, done, total):
        if done % 5 == 0 or done == total:
            print(f'{mode} expansion={expansion}: {done}/{total}', flush=True)
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=180) as client:
        report = diagnose(client, packet, progress)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    with args.output.with_suffix('.md').open('x') as stream:
        stream.write(markdown(report))


if __name__ == '__main__':
    main()
