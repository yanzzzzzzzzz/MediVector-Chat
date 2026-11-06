"""Build a reproducible nonclinical synthetic document-retrieval challenge packet."""
import argparse
import hashlib
import json
import uuid
from pathlib import Path

from medivector.experiment_snapshot import digest

NOTICE = ('虛構機構的合成文件管理測試；規定、代碼、地點均為虛構，不供真實院所使用。'
          '題目與標註由程式準備，未經人工審查。頁面是合成的抽取文字，不代表實測 PDF 解析。')


def definitions():
    # Each tuple contains a paraphrased question, exact proposed evidence, and challenge category.
    return [
        ('門診報到準備須知', ['本文件僅適用初次門診報到。到場後先至藍色服務櫃台領取序號，請攜帶預約通知單。若忘記通知單，向接待人員申請重印。'], [
            ('第一次來看門診，到了以後要先去哪裡？', '先至藍色服務櫃台領取序號', 'paraphrase'),
            ('初次就診當天要帶哪一張紙？', '請攜帶預約通知單', 'paraphrase'),
            ('第一次看診忘了帶通知文件怎麼處理？', '向接待人員申請重印', 'similar_titles')]),
        ('門診回診準備須知', ['本文件僅適用既有預約的門診回診。先到綠色自助機掃描回診卡，無須重新領取初診序號。回診卡遺失時，請至回診支援窗口補印。'], [
            ('已經有回診預約，要去哪裡完成報到？', '到綠色自助機掃描回診卡', 'similar_titles'),
            ('回來複診還要再拿初診號碼嗎？', '無須重新領取初診序號', 'paraphrase'),
            ('複診用的卡片找不到，在哪裡補發？', '至回診支援窗口補印', 'paraphrase')]),
        ('住院文件準備須知', ['本文件說明住院行政文件作業。住院報到請到橙色住院櫃台，攜帶住院通知與身分核對表。表單漏填聯絡欄位時，交由住院行政人員協助補登。'], [
            ('辦住院手續要到哪個櫃台？', '到橙色住院櫃台', 'similar_titles'),
            ('辦入院要準備哪兩份文件？', '住院通知與身分核對表', 'paraphrase'),
            ('入院表格忘記寫聯絡資料，找誰處理？', '住院行政人員協助補登', 'paraphrase')]),
        ('出院文件準備須知', ['本文件僅處理出院行政文件，不含照護建議。先至紫色結帳窗口完成文件核對。收據影本向出院文件櫃台申請。文件上的姓名有誤時，交由出院行政人員更正，不自行塗改。'], [
            ('要離院了，行政資料先到哪裡核對？', '紫色結帳窗口', 'similar_titles'),
            ('離院的收據要再拿一份，去哪裡辦？', '向出院文件櫃台申請', 'paraphrase'),
            ('離院資料名字打錯，可以自己改嗎？', '交由出院行政人員更正，不自行塗改', 'paraphrase')]),
        ('文件核准作業規範', ['文件作者建立草稿後，須提交文件審核佇列。審核者確認版本與適用範圍，再核准發布。退回時須填寫修改理由，由原作者建立修訂。核准紀錄包含審核帳號、時間與版本識別碼。'], [
            ('內容寫好以後，應送到哪裡給人檢查？', '提交文件審核佇列', 'paraphrase'),
            ('審查退件時必須留下什麼說明？', '須填寫修改理由', 'paraphrase'),
            ('通過審查後，系統會保存哪些追蹤資訊？', '審核帳號、時間與版本識別碼', 'paraphrase')]),
        ('文件撤回作業規範', ['已發布文件發現版本錯誤時，審核者應撤回該版本並填寫原因。撤回後一般讀者無法再從查詢取得該內容，歷史事件仍保留。修正內容須建立新版並重新送審，不能直接覆寫原核准版本。'], [
            ('已經發出去的資料版本弄錯，審核者要怎麼處理？', '撤回該版本並填寫原因', 'similar_titles'),
            ('下架後一般使用者還查得到那份內容嗎？', '一般讀者無法再從查詢取得該內容', 'paraphrase'),
            ('已通過的原稿可以直接蓋掉，換成修正版嗎？', '建立新版並重新送審，不能直接覆寫', 'paraphrase')]),
        ('文件影印申請須知', ['本文件適用公開行政文件影本。申請者填寫 COPY-A 表並提交文件服務台。紙本影本於第二工作日領取。申請進度以影印案件編號查詢，不能使用診斷證明申請編號。'], [
            ('想拿公開行政資料的紙本副本，要填哪個表？', 'COPY-A 表', 'similar_titles'),
            ('影印申請交到哪個單位？', '提交文件服務台', 'paraphrase'),
            ('送出紙本副本申請後，何時可以拿到？', '第二工作日領取', 'paraphrase')]),
        ('文件證明申請須知', ['本文件僅示範到場證明申請，未訂定診斷證明規則。申請到場證明填寫 VISIT-B 表，交至證明服務台。領取時出示申請回條。證明上的日期錯誤時，應退回證明服務台更正。'], [
            ('只想證明當天有到場，應該填哪張表？', 'VISIT-B 表', 'similar_titles'),
            ('拿到場證明時，要出示哪個憑據？', '出示申請回條', 'paraphrase'),
            ('到場證明寫錯日期，去哪裡改？', '退回證明服務台更正', 'paraphrase')]),
        ('預約地點變更通知', ['本文件僅記錄服務地點調整，不變更預約時段。收到地點變更通知後，請至銀色接待區核對新地點代碼。若通知上有兩個地點代碼，以有簽核戳記的最新通知為準。'], [
            ('約好的時間沒變，但服務位置換了，要去哪裡核對？', '銀色接待區', 'paraphrase'),
            ('收到換地點的信，預約時間也會一起改嗎？', '不變更預約時段', 'paraphrase'),
            ('手上有兩張不同位置的通知，該看哪張？', '有簽核戳記的最新通知', 'similar_titles')]),
        ('新進文件維護者操作手冊', [
            '新進維護者先使用訓練帳號登入測試工作區，完成草稿與撤回演練後才申請正式權限。\n\n' +
            '\n\n'.join(f'Appendix {i:03d}: Synthetic training record. Check document identifiers, review history, and source links in the sandbox. Record the observed screen and return to the training workspace.' for i in range(45)) +
            '\n\n附錄末段：完成演練後，將 TRAIN-C 表交至文件治理小組。測試帳號於訓練結束後停用。'], [
            ('剛接手維護工作，第一次登入該用哪種帳號？', '訓練帳號登入測試工作區', 'long_document'),
            ('練習全部做完，要把哪個表送給哪個小組？', 'TRAIN-C 表交至文件治理小組', 'long_document'),
            ('新人演練用的帳號什麼時候停掉？', '訓練結束後停用', 'long_document')]),
        ('服務中心到場流程', [
            'Synthetic workflow only. Before arrival, confirm the appointment location using the latest invitation.',
            '',
            'On arrival, bring the confirmation letter to the amber reception desk. This does not describe medical preparation.',
            'After the administrative visit, return the visitor badge to the exit desk.'], [
            ('出發之前，服務地點要用什麼資料確認？', 'confirm the appointment location using the latest invitation', 'cross_language'),
            ('到了服務中心，確認信要拿給哪個櫃台？', 'bring the confirmation letter to the amber reception desk', 'cross_language'),
            ('行政事情辦完後，訪客證要交到哪裡？', 'return the visitor badge to the exit desk', 'cross_language')]),
        ('文件服務中心到場流程', [
            'Synthetic workflow only. For document collection, use the reference number in the collection email.',
            'Bring the collection receipt to the teal document desk. An appointment confirmation letter is not a collection receipt.',
            'If the printed copy is incomplete, contact the document support desk before leaving.'], [
            ('要來取文件，案件號碼應從哪封信找？', 'reference number in the collection email', 'cross_language'),
            ('取件收條要交給哪個顏色的文件櫃台？', 'collection receipt to the teal document desk', 'cross_language'),
            ('領到的紙本缺頁，離開前該找誰？', 'contact the document support desk before leaving', 'cross_language')]),
    ]


def build_fixture():
    sources, cases, versions = [], [], []
    for index, (title, page_parts, questions) in enumerate(definitions(), 1):
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'medivector:prototype-challenge-v1:doc:{index}'))
        version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'medivector:prototype-challenge-v1:version:{index}'))
        parts, pages, offset = [], [], 0
        for number, part in enumerate(page_parts, 1):
            if not part:
                pages.append({'page': number, 'start': offset, 'end': offset, 'status': 'no_text'})
                continue
            if parts:
                offset += 2
            pages.append({'page': number, 'start': offset, 'end': offset + len(part), 'status': 'extracted'})
            parts.append(part)
            offset += len(part)
        text = '\n\n'.join(parts)
        checksum = hashlib.sha256(text.encode()).hexdigest()
        # Single-part text sources are not labelled as PDF pages.
        source = {'id': version_id, 'document_id': doc_id, 'version_label': 'synthetic-v1',
                  'title': '【虛構示範】' + title, 'content': text, 'checksum': checksum,
                  'pages': pages if len(page_parts) > 1 else [], 'source': '虛構文件管理流程',
                  'license': '本專案自行建立的合成測試文字', 'source_url': ''}
        sources.append(source)
        versions.append({'version_id': version_id, 'document_id': doc_id, 'checksum': checksum,
                         'version_label': 'synthetic-v1', 'status': 'approved',
                         'note': 'Approved is a synthetic workflow state, not clinical approval'})
        for query, evidence, category in questions:
            start = text.index(evidence)
            cases.append({'id': f'challenge-{len(cases)+1:03d}', 'query': query, 'answerable': True,
                          'category': category, 'relevant_document_ids': [doc_id],
                          'expected_document_version_ids': [version_id],
                          'evidence_spans': [{'document_id': doc_id, 'source_sha256': checksum,
                                              'start': start, 'end': start + len(evidence)}],
                          'reviewed_by': '', 'reviewed_at': '', 'review_notes': ''})
    for query in [
        '大腸鏡之前要停藥幾天？', 'MRI 檢查前必須空腹幾個小時？',
        '診斷證明要付多少費用？', '到場證明可以當成診斷證明使用嗎？',
        '紙本副本能不能寄到國外？', '回診卡可以讓其他家人借用嗎？',
        '門診報到可以遲到多久？', '住院保證金需要多少錢？',
    ]:
        cases.append({'id': f'challenge-{len(cases)+1:03d}', 'query': query, 'answerable': False,
                      'category': 'no_answer', 'relevant_document_ids': [], 'evidence_spans': [],
                      'reviewed_by': '', 'reviewed_at': '', 'review_notes': ''})
    manifest = {'format_version': 1, 'organization_id': 'fictional-prototype-only',
                'branch_id': 'main', 'department_id': 'documents',
                'embedding_model': 'text-embedding-3-small', 'versions': versions,
                'note': NOTICE}
    # Local artifact identity, not a manifest from the authorized online API.
    manifest['manifest_sha256'] = digest(manifest)
    corpus = {'notice': NOTICE, 'manifest_kind': 'offline_synthetic_fixture', 'manifest': manifest, 'sources': sources}
    packet = {'dataset_version': 'DRAFT-prototype-challenge-v1', 'review_status': 'pending_human',
              'notice': NOTICE, 'corpus_version': manifest['manifest_sha256'],
              'index_version': 'offline-representation-challenge-v1', 'embedding_model': 'text-embedding-3-small',
              'retrieval_context': {'branch_id': 'main', 'department_id': 'documents'}, 'cases': cases}
    return packet, corpus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    packet, corpus = build_fixture()
    paths = [args.directory / 'prototype-challenge-v1.json', args.directory / 'prototype-challenge-corpus-v1.json']
    if any(p.exists() for p in paths):
        raise FileExistsError('Choose a fresh directory; never overwrite frozen fixtures')
    args.directory.mkdir(parents=True, exist_ok=True)
    for path, value in zip(paths, (packet, corpus)):
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
