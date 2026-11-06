"""Compare retrieval-only and model-estimated answerability on frozen synthetic runs."""
import argparse
import hashlib
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from evaluation.synthetic_diagnostic import validate_candidate_packet
from medivector.experiment_snapshot import digest, source_build
from medivector.openai_client import require_openai_api_key
from medivector.source_support import PROMPT, SCHEMA, assess_source_support


def classification_summary(rows, field):
    counts = {'true_accept': 0, 'false_accept': 0, 'true_reject': 0, 'false_reject': 0}
    for row in rows:
        expected, accepted = row['proposed_answerable'], row[field]
        key = ('true_accept' if expected else 'false_accept') if accepted else ('false_reject' if expected else 'true_reject')
        counts[key] += 1
    positives = counts['true_accept'] + counts['false_reject']
    negatives = counts['true_reject'] + counts['false_accept']
    return {**counts, 'false_reject_rate': counts['false_reject'] / positives if positives else None,
            'false_accept_rate': counts['false_accept'] / negatives if negatives else None}


def diagnose(report, packet, assessor, *, variant='title', workers=2, progress=None):
    validate_candidate_packet(packet)
    if (report.get('report_kind') != 'unreviewed_representation_comparison' or
            report.get('verified_baseline') is not False or report.get('release_gate_eligible') is not False):
        raise ValueError('Only unreviewed synthetic representation runs are supported')
    if report.get('candidate_sha256') != digest(packet):
        raise ValueError('Candidate packet differs from measured run')
    if not 1 <= workers <= 4:
        raise ValueError('Use one to four workers')
    groups = [g for g in report['groups'] if g['variant'] == variant]
    if len(groups) != 1:
        raise ValueError('Select one existing representation variant')
    group = groups[0]
    cases = {case['id']: case for case in packet['cases']}
    if {run['case_id'] for run in group['runs']} != set(cases) or len(group['runs']) != len(cases):
        raise ValueError('Run cases differ from packet')
    representations = {r['chunk_id']: r for r in group['representations']}
    # Validate every input before any paid call. Labels are used only after classification.
    for run in group['runs']:
        if run['question'] != cases[run['case_id']]['query']:
            raise ValueError('Question differs from frozen packet')
        seen = set()
        for ref in run['filtered']:
            original = representations.get(ref['uuid'])
            if (not original or ref['uuid'] in seen or ref['document_id'] != original['document_id'] or
                    ref['content'] != original['content'] or ref['chunk_metadata'] != original['chunk_metadata']):
                raise ValueError('Source differs from frozen representation')
            seen.add(ref['uuid'])
    started = time.monotonic()
    def evaluate(run):
        case = cases[run['case_id']]
        refs = [{'chunk_id': ref['uuid'], 'content': ref['content']} for ref in run['filtered']]
        estimate = assessor(run['question'], refs)
        if (estimate.get('human_reviewed') is not False or estimate.get('semantic_support_verified') is not False or
                estimate.get('status') not in {'sufficient', 'partial', 'insufficient', 'uncertain'} or
                not isinstance(estimate.get('estimated_answerable'), bool) or
                estimate.get('estimated_answerable') != (estimate.get('status') == 'sufficient')):
            raise ValueError('Assessor must preserve the unverified model-estimate boundary')
        return {'case_id': case['id'], 'question': case['query'], 'category': case.get('category', 'unspecified'),
                'proposed_answerable': case['answerable'], 'retrieval_has_candidates': bool(refs),
                'support_estimated_answerable': estimate['estimated_answerable'],
                'candidate_chunk_ids': [ref['chunk_id'] for ref in refs], 'estimate': estimate}
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for row in executor.map(evaluate, group['runs']):
            rows.append(row)
            if progress:
                progress(len(rows), len(group['runs']))
    latencies = sorted(row['estimate']['elapsed_ms'] for row in rows if row['candidate_chunk_ids'])
    usage = {key: sum((row['estimate'].get('usage') or {}).get(key, 0) for row in rows)
             for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    return {'report_kind': 'unreviewed_source_support_diagnostic', 'verified_baseline': False,
            'release_gate_eligible': False, 'human_review_complete': False,
            'created_at': datetime.now(timezone.utc).isoformat(), 'input_report_sha256': digest(report),
            'candidate_sha256': digest(packet), 'variant': variant, 'workers': workers,
            'prompt_sha256': digest({'prompt': PROMPT, 'schema': SCHEMA}),
            'source_build': source_build(), 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'retrieval_only': classification_summary(rows, 'retrieval_has_candidates'),
            'with_support_estimate': classification_summary(rows, 'support_estimated_answerable'),
            'uncertain_cases': sum(row['estimate']['status'] == 'uncertain' for row in rows),
            'model_request_failures': sum(row['estimate'].get('reason') == 'model_request_failed' for row in rows),
            'invalid_model_outputs': sum(row['estimate'].get('reason') == 'invalid_or_ungrounded_model_output' for row in rows),
            'token_usage': usage, 'wall_ms': round((time.monotonic() - started) * 1000, 2),
            'p50_model_check_ms': statistics.median(latencies) if latencies else None,
            'p95_model_check_ms': latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
            'rows': rows,
            'limitations': 'Only model-estimated source sufficiency, not an answer or a semantic/clinical guarantee. '
            'Verbatim quotes establish provenance, not entailment or complete requirement decomposition. '
            'Scores use unreviewed program-authored proposed labels on the same synthetic challenge. '
            'Retrieval-only candidate presence is an ablation comparator, not existing chat acceptance behavior. '
            'No live endpoint/index change. Prompt token usage is not a monetary cost calculation. '
            'Non-sufficient and model failures are treated as non-acceptance, with failures counted separately.'}


def markdown(report):
    lines = ['# 來源可回答性隔離比較（AI 估計，未經人工審查）', '', report['limitations'], '',
             '| 策略 | 提議可回答題接受 | 提議可回答題拒絕 | 提議無答案題接受 | 提議無答案題拒絕 |',
             '|---|---:|---:|---:|---:|']
    for key, label in [('retrieval_only', '有候選就接受（比較基準）'), ('with_support_estimate', '來源可回答性估計')]:
        s = report[key]
        lines.append(f"| {label} | {s['true_accept']} | {s['false_reject']} | {s['false_accept']} | {s['true_reject']} |")
    lines += ['', f"模型檢查 P50/P95：{report['p50_model_check_ms']} / {report['p95_model_check_ms']} ms。",
              f"Token usage：{report['token_usage']}。", '',
              f"API 失敗：{report['model_request_failures']}；不合格式／引用無法核對：{report['invalid_model_outputs']}。", '',
              '| 題號 | 問題 | 模型估計 | 與候選標註一致 |', '|---|---|---|---|']
    for row in report['rows']:
        question = row['question'].replace('|', '\\|').replace('\n', ' ')
        agrees = row['proposed_answerable'] == row['support_estimated_answerable']
        lines.append(f"| {row['case_id']} | {question} | {row['estimate']['status']} | {agrees} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('candidates', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', default='title')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--acknowledge-synthetic-data', action='store_true', required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use fresh report paths')
    key = require_openai_api_key()
    def progress(done, total):
        if done % 5 == 0 or done == total:
            print(f'Source check {done}/{total}', flush=True)
    result = diagnose(json.loads(args.report.read_text()), json.loads(args.candidates.read_text()),
                      lambda question, refs: assess_source_support(key, question, refs),
                      variant=args.variant, workers=args.workers, progress=progress)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    with args.output.with_suffix('.md').open('x', encoding='utf-8') as stream:
        stream.write(markdown(result))


if __name__ == '__main__':
    main()
