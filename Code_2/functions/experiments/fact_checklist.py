"""EXPERIMENT_ONLY：從離線稽核建立跨切法標準證據草稿，不參與核心檢索。

只將既有人工稽核整理成可追溯清單，不把錨點共現冒充語意驗證。
移除時刪除此獨立CLI及README對應說明；正式問答沒有呼叫。
"""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path


def plain(text):
    return html.unescape(re.sub(r'<[^>]+>', ' ', text))


def canonical(text):
    return re.sub(r'[\s,，|]', '', plain(str(text)))


def snippets(content, anchors):
    text = canonical(content)
    result = []
    for anchor in anchors:
        token = canonical(anchor)
        position = text.find(token)
        result.append({'anchor': anchor, 'context': None if position < 0 else
                       text[max(0, position-100):position+len(token)+100],
                       'note': '正規化片段只供核對；不等於已確認列名、年度或正負值。'})
    return result


def build(audit, source, excluded):
    nodes = {c['chunk_id'].split('__')[-1]: c for c in source['chunks']}
    questions = []
    for row in audit['rows']:
        if row['ID'] in excluded:
            continue
        groups = []
        for index, fact in enumerate(row['top50_facts'], 1):
            node = nodes.get(fact['source_node'])
            # 識別碼由題號與事實序號構成，不使用任一切法chunk_id。
            groups.append({
                'evidence_id': f"Q{int(row['ID']):03d}-E{index:02d}",
                'description': fact['label'] if not re.fullmatch(r'[ct]\d+', fact['label'])
                               else '需核對以下數值／文字所屬的科目、年度及單位',
                'anchors': fact['anchors'],
                'reference': {
                    'doc_id': source['doc_id'], 'pages': fact['pages'],
                    'sub_section': node.get('sub_section') if node else None,
                    'note_title': node.get('note_title') if node else None,
                    'content_type': node.get('content_type') if node else None,
                    'context': snippets(node['content'], fact['anchors']) if node else [],
                },
                'confirmed_assertions': [],
                'review_status': '待逐項確認科目_內容年度_數值_單位_條件',
                'prior_top50_anchor_matches': fact['hits'],
                'prior_top50_anchor_present': fact['present'],
                'source_trace_only': fact['source_node'],
            })
        questions.append({
            'ID': row['ID'], 'Question': row['Question'], 'reference_answer': row['Answer'],
            'formula': row['formula'], 'previous_audit_status': row['top50_status'],
            'note': row['note'], 'evidence_groups': groups,
            'anchor_coverage': {'found': sum(g['prior_top50_anchor_present'] for g in groups),
                                'required': len(groups)},
            'confirmed_evidence_score': None,
        })
    return {
        'schema_version': 'financial-fact-checklist/0.1-draft',
        'status': '草稿_非自動語意評分結果', 'questions': questions,
        'rules': {
            'scope': '完整Top50及必回父項，不使用最後選取的前10筆',
            'matching_identity': '必要事實，不比對chunk_id；頁碼及章節供來源核對',
            'confirmed_assertion_fields': ['stock_code', 'content_year', 'metric',
                                           'value', 'unit', 'condition', 'source_quote'],
            'cross_chunk': '同一題各項必要事實可在不同chunk；同一事實只計一次',
            'cross_report': '來源財報年不同仍可支持相同內容年度；必須逐項核對原文，不能只看years metadata',
            'missing_definition': '未知不補值，待確認事實不當成已命中或確定未命中',
            'answer_access': '標準答案只供離線核對，不送入檢索、重排或回答模型',
        },
        'limitations': [
            '沿用既有稽核必要值分組，尚未逐項拆成獨立、已確認的年度×科目×單位斷言。',
            'prior_top50_anchor_present只表示同一候選找到錨點，不代表語意完整率。',
            'prior_top50_anchor_matches及source_trace_only只供追查，不是跨切法命中條件。',
            '未逐格核對全部原PDF，不對尚待確認的92題宣稱正式答案證據命中率。',
        ],
    }


def markdown(data):
    lines = ['# 92題標準證據清單草稿', '',
             '本清單是既有稽核的結構化草稿。每題的必要年度、科目、數值、單位與篩選條件，仍須逐項確認後才能作為正式跨切法評分標準。',
             '既有錨點檢查及人工稽核結論僅供追查，不等於新評分器已完成。', '',
             '## 建議判定', '',
             '依確認後的必要事實計算找到項數／總項數；全部找到才算完整命中。來源chunk_id只記錄這次找到的位置，不參與標準比對。', '',
             '## 待確認事項', ''] + ['- '+x for x in data['limitations']]
    for question in data['questions']:
        lines += ['', '## ID '+question['ID'], '', question['Question'], '',
                  '標準答案：'+str(question['reference_answer']),
                  '公式／條件：'+question['formula'],
                  '既有Top50人工稽核：'+question['previous_audit_status'],
                  '補充：'+(question['note'] or '無'), '']
        for group in question['evidence_groups']:
            ref = group['reference']
            lines += [f"### {group['evidence_id']}：{group['description']}", '',
                      f"核對來源：{ref['doc_id']}，PDF頁序{ref['pages']}",
                      '核對錨點：'+ '、'.join(group['anchors']),
                      '狀態：'+group['review_status'], '']
            for context in ref['context']:
                lines.append(f"- {context['anchor']}：{context['context'] or '未找到'}")
    return '\n\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--chunks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exclude', nargs='*', default=[])
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    source = json.loads(args.chunks.read_text(encoding='utf-8'))
    result = build(audit, source, set(args.exclude))
    result['provenance'] = {
        'audit_sha256': hashlib.sha256(args.audit.read_bytes()).hexdigest(),
        'chunks_sha256': hashlib.sha256(args.chunks.read_bytes()).hexdigest(),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'標準證據清單_草稿.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'標準證據清單_草稿.md').write_text(markdown(result), encoding='utf-8')
    print(json.dumps({'questions': len(result['questions']), 'output': str(args.output),
                      'status': result['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
