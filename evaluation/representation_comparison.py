"""Isolated synthetic embedding ablation; never reads or writes a live database."""
import argparse
import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.retrieval_baseline import metrics
from evaluation.synthetic_diagnostic import validate_candidate_packet
from medivector.chunking import chunk_manifest
from medivector.config import EMBEDDING_MODEL
from medivector.experiment_snapshot import digest, source_build
from medivector.models import Reference
from medivector.openai_client import embed_texts, require_openai_api_key
from medivector.retrieval import filter_references

VARIANTS = ('body', 'title', 'title_pages', 'page_chunks')


def representations(sources, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown representation')
    records = []
    for source in sources:
        text = source['content']
        checksum = hashlib.sha256(text.encode()).hexdigest()
        if checksum != source['checksum']:
            raise ValueError('Source checksum mismatch')
        pages = source.get('pages', [])
        previous_end = 0
        for page in pages:
            if not 0 <= page['start'] <= page['end'] <= len(text) or page['start'] < previous_end:
                raise ValueError('Invalid page offsets')
            previous_end = page['end']
        if variant == 'page_chunks' and pages:
            spans = []
            for page in pages:
                if page['end'] == page['start']:
                    continue
                manifest = chunk_manifest(text[page['start']:page['end']],
                                          document_id=source['document_id'], version=source['id'])
                spans.extend((page['start'] + c['start'], page['start'] + c['end'], [page['page']])
                             for c in manifest['chunks'])
        else:
            manifest = chunk_manifest(text, document_id=source['document_id'], version=source['id'], pages=pages)
            spans = [(c['start'], c['end'], c['pages']) for c in manifest['chunks']]
        for number, (start, end, page_numbers) in enumerate(spans, 1):
            # Metadata changes embedding input only; citations still point into untouched source text.
            content = text[start:end]
            prefix = f"文件標題：{source['title']}\n" if variant != 'body' else ''
            if variant in ('title_pages', 'page_chunks') and page_numbers:
                prefix += 'PDF 頁碼：' + '、'.join(map(str, page_numbers)) + '\n'
            records.append({'chunk_id': f"{source['id']}:{variant}:{number}",
                            'document_id': source['document_id'], 'version_id': source['id'],
                            'title': source['title'], 'content': content, 'embedding_input': prefix + content,
                            'chunk_metadata': {'source_sha256': checksum, 'start': start, 'end': end,
                                               'pages': page_numbers, 'version_id': source['id']}})
    return records


def cosine_distance(a, b):
    if not a or len(a) != len(b) or not all(math.isfinite(x) for x in (*a, *b)):
        raise ValueError('Invalid embedding dimensions or values')
    denominator = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b))
    if denominator == 0:
        raise ValueError('Zero embedding')
    return max(0.0, min(2.0, 1 - sum(x*y for x, y in zip(a, b)) / denominator))


def compare(packet, corpus, embed, *, max_distance=0.65, distance_margin=0.12):
    validate_candidate_packet(packet)
    if packet['corpus_version'] != corpus['manifest']['manifest_sha256']:
        raise ValueError('Candidate corpus mismatch')
    if packet['embedding_model'] != EMBEDDING_MODEL:
        raise ValueError('Embedding model mismatch')
    if max_distance < 0 or distance_margin < 0 or not all(map(math.isfinite, (max_distance, distance_margin))):
        raise ValueError('Invalid thresholds')
    versions = {v['version_id']: v for v in corpus['manifest']['versions']}
    if len(versions) != len(corpus['sources']) or {s['id'] for s in corpus['sources']} != set(versions):
        raise ValueError('Source versions differ from manifest')
    for source in corpus['sources']:
        version = versions[source['id']]
        if source['checksum'] != version['checksum'] or source['document_id'] != version['document_id']:
            raise ValueError('Source identity differs from manifest')
    variants = {name: representations(corpus['sources'], name) for name in VARIANTS}
    # Embed every unique input once, replaying identical query vectors across all variants.
    inputs = list(dict.fromkeys([c['query'] for c in packet['cases']] +
                               [r['embedding_input'] for rows in variants.values() for r in rows]))
    vectors = embed(inputs)
    if len(vectors) != len(inputs):
        raise ValueError('Embedding count mismatch')
    for vector in vectors:
        cosine_distance(vectors[0], vector)
    lookup = dict(zip(inputs, vectors))
    groups = []
    for name, rows in variants.items():
        runs = []
        for case in packet['cases']:
            candidates = [Reference(index=i, uuid=row['chunk_id'], document_id=row['document_id'],
                                    source_id=0, title=row['title'], source='frozen-synthetic-source',
                                    publisher='', published_date='', version=row['version_id'],
                                    audience='', topic='', credibility='', content=row['content'],
                                    distance=cosine_distance(lookup[case['query']], lookup[row['embedding_input']]),
                                    chunk_metadata=row['chunk_metadata']) for i, row in enumerate(rows, 1)]
            ordered = sorted(candidates, key=lambda r: (r.distance, r.uuid))
            ordered = [Reference(**{**asdict(ref), 'index': rank}) for rank, ref in enumerate(ordered, 1)]
            selected = filter_references(ordered, top_k=5, max_distance=max_distance, distance_margin=distance_margin)
            results = [asdict(r) for r in selected]
            score = metrics(case, results, 5)
            if case['answerable']:
                relevant = set(case['relevant_document_ids'])
                score['precision'] = sum(r['document_id'] in relevant for r in results) / len(results) if results else 0.0
            runs.append({'case_id': case['id'], 'question': case['query'], 'category': case.get('category', 'unspecified'),
                         'raw_candidates': [asdict(r) for r in ordered], 'filtered': results,
                         'proposed_label_metrics': score})
        answered = [r['proposed_label_metrics'] for r in runs if r['proposed_label_metrics']['answerable']]
        unanswered = [r['proposed_label_metrics'] for r in runs if not r['proposed_label_metrics']['answerable']]
        summary = {key: sum(r[key] for r in answered) / len(answered) if answered else None for key in ('recall', 'mrr', 'hit', 'precision')}
        evidence_scores = [r['evidence_recall'] for r in answered if r['evidence_recall'] is not None]
        summary['evidence_recall'] = sum(evidence_scores) / len(evidence_scores) if evidence_scores else None
        summary['unanswerable_return_rate'] = sum(r['returned_any'] for r in unanswered) / len(unanswered) if unanswered else None
        groups.append({'variant': name, 'chunk_count': len(rows), 'representations': rows,
                       'proposed_label_summary': summary, 'runs': runs})
    return {'report_kind': 'unreviewed_representation_comparison', 'verified_baseline': False,
            'release_gate_eligible': False, 'human_review_complete': False,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'candidate_sha256': digest(packet), 'source_packet_sha256': digest(corpus),
            'corpus_size': {'versions': len(corpus['sources']), 'cases': len(packet['cases'])},
            'embedding_model': EMBEDDING_MODEL, 'unique_embedding_inputs': len(inputs),
            'settings': {'max_distance': max_distance, 'distance_margin': distance_margin, 'top_k': 5,
                         'query_expansion': False, 'ranking': 'in_memory_exact_cosine'},
            'groups': groups, 'source_build': source_build(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limitations': 'Synthetic ablation with program-authored sources/questions and unreviewed proposed labels; '
            'not an independent holdout or real-world generalization study. '
            'No live ACL, database ranking, generation, clinical validation or latency benchmark. '
            'Page splitting changes chunk count. Query expansion is off for every variant. '
            'A source/version match does not establish that a retrieved page supports an answer.'}


def markdown(report):
    lines = ['# 文件表示法比較（合成資料，未經人工審查）', '', report['limitations'], '',
             '| 表示法 | chunks | 暫定 Recall@5 | 暫定 MRR@5 | 暫定片段精確率 | 暫定證據覆蓋 | 提議無答案題仍返回候選 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for group in report['groups']:
        s = group['proposed_label_summary']
        lines.append(f"| {group['variant']} | {group['chunk_count']} | {s['recall']} | {s['mrr']} | {s['precision']} | {s['evidence_recall']} | {s['unanswerable_return_rate']} |")
    lines += ['', '## 逐題比較', '', '| 題號 | ' + ' | '.join(VARIANTS) + ' |',
              '|---|' + '---|' * len(VARIANTS)]
    for i, run in enumerate(report['groups'][0]['runs']):
        cells = []
        for group in report['groups']:
            r = group['runs'][i]
            score = r['proposed_label_metrics']
            cells.append(('命中' if score['hit'] else '漏檢') if score['answerable'] else
                         ('仍返回候選' if score['returned_any'] else '無候選'))
        lines.append('| ' + run['case_id'] + ' | ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidates', type=Path)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--acknowledge-synthetic-data', action='store_true', required=True,
                        help='Confirm files contain authorized nonpersonal synthetic data')
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Choose fresh report paths')
    packet = json.loads(args.candidates.read_text(encoding='utf-8'))
    corpus = json.loads(args.corpus.read_text(encoding='utf-8'))
    report = compare(packet, corpus, lambda texts: embed_texts(require_openai_api_key(), texts))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    with args.output.with_suffix('.md').open('x', encoding='utf-8') as stream:
        stream.write(markdown(report))


if __name__ == '__main__':
    main()
