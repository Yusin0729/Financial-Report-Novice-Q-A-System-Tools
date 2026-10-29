"""EXPERIMENT_ONLY：每題獨立JSON／Markdown；移除時取消export_output、eval_run呼叫。"""
import json
import re
from Code_2.functions.experiments.evidence_report import EvidenceReportContext


def payloads(paths, result):
    if result.get('rows') is not None:
        from Code_2.functions.experiments.model_input_reports import payloads as model_inputs
        return model_inputs(paths,result)
    from Code_2.config.embedding import Settings
    context = EvidenceReportContext(Settings(project_root=paths['project_root']))
    rows = result.get('rows')
    if rows is None:
        rows = [{'ID': '1', 'Question': result.get('original_question', ''), 'query': result}]
    output, names = {}, set()
    for number, row in enumerate(rows, 1):
        query = row.get('query') or {}
        identity = str(row.get('ID', number))
        label = identity.zfill(3) if re.fullmatch(r'\d+', identity) else f'{number:03d}'
        stem = 'ID_' + label
        if stem in names:
            stem += '_' + str(number)
        names.add(stem)
        evidence = [context.enrich(e) for e in query.get('evidence', [])]
        children = [context.enrich(e) for e in query.get('reranked_children', [])]
        record = {'ID': identity, 'Question': row.get('Question', query.get('original_question', '')),
                  'status': query.get('status', row.get('status')), 'mode': query.get('mode'),
                  'error': query.get('error', row.get('error')), 'query_embedding': query.get('query_embedding'),
                  'selected_child_ids': query.get('selected_child_ids', []),
                  'retrieved_evidence': query.get('retrieved_evidence', []),
                  'reranked_children': children, 'evidence': evidence,
                  'rerank': query.get('rerank'), 'generation': query.get('generation')}
        reference = row.get('reference') or {}
        record['evidence_type'] = reference.get('Evidence_Type') or None
        record['cross_page_table'] = reference.get('Cross_Page_Table') or None
        if 'scores' in row:
            # EXPERIMENT_ONLY：逐題保存各階段的評分明細，包含全部有效候選及每項貢獻。
            record.update(scoring_rule=result.get('scoring_rule'),
                          score_stage=row.get('score_stage'), scores=row['scores'],
                          reference={key: reference.get(key) for key in
                              ('Page', 'Doc_Id', 'Years', 'Evidence_Main_Section',
                               'Evidence_Sub_Section', 'Evidence_Note_Title',
                               'Evidence_Type', 'Cross_Page_Table','Required_Numbers',
                               'Required_Numbers_Status','Required_Numbers_Note','Required_Numbers_Source')},
                          retrieve_k=result.get('settings', {}).get('retrieve_k'),
                          timings=row.get('timings', {}), usage=row.get('usage', {}),
                          elapsed_seconds=row.get('elapsed_seconds'),
                          source_run=result.get('source_run'),
                          candidate_unit=result.get('candidate_unit'),
                          parent_expansion_stage=result.get('parent_expansion_stage'))
        if 'answer' in query:
            record['answer'] = query['answer']
        lines = [f'# ID {identity}', record['Question'], f"狀態：{record['status']}"]
        if record['evidence_type']:
            lines.append('標準證據類型：'+record['evidence_type']+'；跨頁表格：'+(record['cross_page_table'] or 'unknown'))
        cache = (record['query_embedding'] or {}).get('cache')
        if cache is not None:
            lines.append('問題向量題庫：' + ('命中快取，本次未重新向量化' if cache['hit'] else '未命中，已生成並保存'))
        if record['error']:
            lines.append(str(record['error']))
        if 'scores' in record:
            lines.extend(['## 評分依據',
                f"版本：{record.get('scoring_rule') or '未知'}；向量召回 K：{record.get('retrieve_k') or '未知'}；"
                f"最終評分階段：{record.get('score_stage') or '未知'}",
                '原始分數按年度×標題命中比例計算；新版排名加權採首次有效名次，每晚於理想名次一名扣該項配分/K，舊階段保留來源扣分，見逐階段版本與每名扣分。'
                ' 同一必回父項的子項去重；頁碼只供核對。兩種分數均非回答正確率。',
                f"標準年度：{reference.get('Years') or '未指定'}；股號來源：{reference.get('Doc_Id') or '未指定'}；"
                f"標準標題：{reference.get('Evidence_Note_Title') or '未指定'}；"
                f"標準頁碼：{reference.get('Page') or '未指定'}",
                '|階段|原始分數／10|排名加權／10|年度×標題命中|缺少項目|',
                '|---|---:|---:|---|---|'])
            for stage, label in (('retrieval', '原始檢索'), ('returned', '父項召回後'), ('rerank', '重排序')):
                score = record['scores'].get(stage)
                if not score:
                    continue
                lines.append(f"|{label}|{score.get('raw_score')}|{score.get('score')}|"
                             f"{score.get('target_coverage')}|{'；'.join(score.get('missing_targets', [])) or '無'}|")
                if score.get('numeric_targets') is not None:
                    if score.get('numeric_aggregation')=='all-chunks-union':
                        lines.append('本階段只以必要數字判定，可跨chunk補齊；不以股號、年度、標題或頁碼擋分。分組名稱只供識別，補齊名次採最後必要數字的有效排名。')
                    else:
                        lines.append('來源舊版依年度、標題及必要數字判定；以保存的scoring_rule為準。')
                    if score.get('scoring_note'):lines.append(score['scoring_note'])
                    for candidate in score.get('top20',[]):
                        for check in candidate.get('numeric_checks',[]):
                            lines.append(f"- {candidate['chunk_id']}｜{check['target']}｜必要數字：{check['required_numbers']}｜本組缺少：{check['missing_numbers']}｜累積缺少：{check.get('cumulative_missing_numbers',check['missing_numbers'])}｜本名次補齊：{check['matched']}")
                    if score.get('number_hits'):
                        lines.append('各必要數字首次來源：'+json.dumps(score['number_hits'],ensure_ascii=False))
                lines.extend([f'### {label}：逐項得分與名次',
                    f"本階段評分版本：{score.get('scoring_rule', record.get('scoring_rule'))}",
                    f"頁碼核對：{score.get('page_coverage')}；未找到："
                    f"{'、'.join(score.get('missing_pages', [])) or '無'}；"
                    f"每名扣分：{score.get('rank_penalty')}",
                    '|年度×標題|有效名次|理想名次|原始得分|排名加權得分|',
                    '|---|---:|---:|---:|---:|'])
                for item in score.get('contributions', []):
                    lines.append(f"|{item['target']}|{item['rank']}|{item['ideal_rank']}|"
                                 f"{item['raw_score']}|{item['score']}|")
                lines.extend(['命中候選（有效名次已去除重複必回父項）：',
                    '|有效名次|原名次|chunk_id|來源文件|內容年度|PDF頁序|命中年度×標題|',
                    '|---:|---:|---|---|---|---|---|'])
                for item in score.get('top20', []):
                    lines.append(f"|{item['effective_rank']}|{item['original_rank']}|{item['chunk_id']}|"
                                 f"{item['doc_id']}|{item.get('years', [])}|{item.get('page', [])}|"
                                 f"{'；'.join(item.get('matched_targets', [])) or '無'}|")
            if record.get('source_run'):
                lines.append('此重排序沿用來源報告的檢索與父項召回；未重新檢索。'
                             ' 前兩階段分數是來源基準，只有重排序是本次執行。')
            lines.append(f"本題耗時：{record.get('elapsed_seconds')}秒；分段耗時："
                         f"{json.dumps(record.get('timings', {}), ensure_ascii=False)}；"
                         f"API用量：{json.dumps(record.get('usage', {}), ensure_ascii=False)}")
        for title, values in (('重排序選中的子項', children), ('回答證據', evidence)):
            if values:
                lines.append('## ' + title)
            for e in values:
                lines.extend([f"### [{e['id']}] {e['chunk_id']}",
                    f"來源文件：{e['doc_id']}｜PDF頁序：{e['page']}｜檢索排名：{e.get('retrieval_rank')}｜重排排名：{e.get('rerank_rank', '未執行')}",
                    e['report_text']])
        if 'answer' in record:
            from Code_2.functions.qa.answers import render_answer
            lines.extend(['## 回答', render_answer(query)])
        root = paths['json'].parent
        output[root / (stem + '.json')] = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        output[root / (stem + '.md')] = ('\n\n'.join(lines) + '\n').encode('utf-8')
    return output
