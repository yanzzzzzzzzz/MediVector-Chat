"""Offline prerequisite inventory for #5/#8/#20; never certifies human work."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.faithfulness import evaluate, review_provenance_valid
from evaluation.retrieval_baseline import validate_dataset

ROOT = Path(__file__).resolve().parents[1]


def inspect(dataset, answers, pilot):
    answer_reports = [evaluate(case) for case in answers]
    reviewed_answers = [r for r in answer_reports if r['human_review_provenance_valid']]
    answer_ready = bool(answers) and len(reviewed_answers) == len(answers) and all(
        r['generation_faithfulness'] == 'pass' for r in answer_reports)
    try:
        validate_dataset(dataset)
        dataset_error = None
    except (ValueError, KeyError, TypeError) as exc:
        dataset_error = str(exc)
    dataset_ready = dataset_error is None and dataset.get('review_status') == 'reviewed'
    reviewed_cases = sum(review_provenance_valid(dict(case, review_status=dataset.get('review_status')))
                         for case in dataset.get('cases', []))
    # Record presence only: content, consent and measurements require actual acceptance review.
    pilot_counts = {key: len(pilot.get(key, [])) for key in (
        'participants', 'interview_records', 'task_measurements', 'prioritized_needs',
        'adoption_and_deployment_findings')}
    blockers = []
    if not answer_ready:
        blockers.append('#5: complete real claim-by-claim review, full answer coverage and citation-support decisions')
    else:
        blockers.append('#5: independently verify supplied review provenance and accept the reviewed report')
    if not dataset_ready:
        blockers.append('#8: review at least 30 cases with reviewer/time and freeze corpus/index/model versions')
    blockers.append('#8: execute the reviewed baseline in the independent Lab and analyse actual failures; do not invent five failures')
    blockers.append('#20: verify 3–5 real professional interviews and Pilot records, paired measurements, needs and deployment findings')
    return {
        'report_kind': 'acceptance_prerequisite_inventory',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'external_acceptance_required',
        'release_gate_eligible': False,
        'issues': {
            '5': {'input_ready_for_acceptance': answer_ready, 'answers': len(answers),
                  'supplied_review_provenance_valid': len(reviewed_answers), 'results': answer_reports},
            '8': {'input_ready_for_baseline': dataset_ready, 'cases': len(dataset.get('cases', [])),
                  'supplied_review_provenance_valid': reviewed_cases, 'validation_error': dataset_error,
                  'baseline_execution_verified': False},
            '20': {'reported_status': pilot.get('status'), 'record_counts': pilot_counts,
                   'real_participation_verified': False},
            '9': {'depends_on': [5, 8, 20]}, '10': {'depends_on': [5, 8]},
            '12': {'depends_on': [5, 8, 20]},
        },
        'remaining_acceptance': blockers,
        'limitations': 'Offline structural checks only. Supplied reviewer identity, actual participation, source authorization and semantic decisions are not authenticated. No clinical validation or automatic issue closure.',
    }


def markdown(report):
    issues = report['issues']
    return '\n'.join([
        '# 人工驗收準備檢查', '', report['limitations'], '',
        '| Issue | 輸入檢查 | 下一步 |', '|---|---|---|',
        f"| #5 | {issues['5']['supplied_review_provenance_valid']}/{issues['5']['answers']} 份具審查欄位 | 核對全部陳述及引用；獨立確認人工審查 |",
        f"| #8 | {issues['8']['supplied_review_provenance_valid']}/{issues['8']['cases']} 題具審查欄位；baseline input ready={issues['8']['input_ready_for_baseline']} | 凍結資料、執行獨立 Lab、分析實際失敗 |",
        f"| #20 | {issues['20']['record_counts']['participants']} 位參與者紀錄；{issues['20']['record_counts']['task_measurements']} 筆量測 | 真實訪談及 Pilot，再核對報告 |",
        '| #9 / #10 / #12 | 依賴上述驗收 | 保持開啟 |', '',
        '## 尚需驗收', '', *('- ' + item for item in report['remaining_acceptance']), '',
        '本報告僅盤點輸入；不能當作正式 baseline、發布閘門通過或真人工作完成證明。', '',
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='Fresh .json output; .md is also written')
    parser.add_argument('--dataset', type=Path, default=ROOT / 'evaluation/candidates/local-preview-v1.json')
    parser.add_argument('--answers', type=Path, default=ROOT / 'evaluation/candidates/answer-support-v1.json')
    parser.add_argument('--pilot', type=Path, default=ROOT / 'docs/pilot/pilot-report.template.json')
    args = parser.parse_args()
    if args.output.suffix != '.json':
        parser.error('output must use .json suffix')
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Use fresh report paths; existing evidence is never overwritten')
    inputs = {name: path.read_bytes() for name, path in (
        ('dataset', args.dataset), ('answers', args.answers), ('pilot', args.pilot))}
    report = inspect(*(json.loads(inputs[name]) for name in ('dataset', 'answers', 'pilot')))
    report['input_sha256'] = {name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()}
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    with args.output.with_suffix('.md').open('x') as stream:
        stream.write(markdown(report))
    print('External acceptance required; JSON/Markdown prerequisite reports written.')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
