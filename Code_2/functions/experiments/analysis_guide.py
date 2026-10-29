"""EXPERIMENT_ONLY：供外部 LLM 閱讀的批次測報索引；不參與檢索或評分。

移除時取消 eval_run.export_batch 的呼叫；分題原始資料仍在 result.json。
"""
from statistics import mean


STAGES = (('retrieval', '原始檢索'), ('returned', '父項召回後'), ('rerank', '重排序'))


def _value(value):
    return '無法計分' if value is None else str(value)


def render_analysis_guide(result):
    rows = result.get('rows', [])
    settings = result.get('settings', {})
    lines = [
        '# 獨立測試分析報告',
        '',
        '本檔可獨立閱讀本次實驗設定、計分規則、各階段統計與逐題結果。完整候選文字與回答證據另存同資料夾的 ID_*.json／ID_*.md，機器資料為 result.json，Excel核對表為 results.xlsx。',
        '要分析特定題目的原文品質，請將該題 ID_*.md 或 JSON 一併提供給 LLM。不同模型的上下文長度不同，無法保證一次載入全部題目的完整證據；未提供的證據不能視為不存在。',
        '',
        '## 執行條件',
        f"- 來源測試集：{result.get('filename', '未知')}；工作表：{result.get('sheet', '未知')}；來源 SHA256：{result.get('source_sha256', '未知')}",
        f"- 索引：{result.get('index', {}).get('backend', settings.get('backend', '未知'))}／{result.get('index', {}).get('collection', settings.get('collection', '未知'))}",
        f"- 模式：{settings.get('mode', '未知')}；向量召回 K：{settings.get('retrieve_k', '未知')}；保留證據數：{settings.get('evidence_k', '未知')}",
        f"- 評分版本：{result.get('scoring_rule', '未知')}；狀態：{result.get('status', '未知')}；總耗時：{result.get('elapsed_seconds', '未知')} 秒",
        f"- 題數：{len(rows)}；可評分：{result.get('summary', {}).get('scored', '未知')}；失敗：{result.get('summary', {}).get('failed', '未知')}；未執行：{result.get('summary', {}).get('not_run', '未知')}",
        '',
        '- 重排序模型／設定：' + str(settings.get('rerank_model') or next((r.get('query',{}).get('rerank_model') for r in rows if r.get('query',{}).get('rerank_model')), '未知')) + '；不同重排模型的分數尺度不可直接比較。',
        '## 分數意義與分析限制',
        '- 一個年度×標準標題為一個目標；原始分數＝10×命中目標數／目標總數。沒有標準標題的題目無法計分。',
        '- 排名加權分數使用首次有效命中名次；新版按理想名次延後的幅度扣「該項配分／原始向量召回K」，舊報告保留來源扣分。各階段以scoring_rule及rank_penalty為準；同一必回父項的子項去重。分數並非回答正確率。',
        '- 標題忽略開頭編號，比對完整名稱；股號與內容年度須符合。Page 只供來源核對，不作得分門檻。若此報告使用舊版 scoring_rule，請以 result.json 中的規則與逐題分數為準。',
        '- 若題目有Required_Numbers，新版numbers-only/1.0只核對必要數字，可由多個chunk補齊，不以股號、年度、標題或頁碼限制得分；舊版1.2仍依來源metadata判定，完整命中名次採最後補齊數字的有效名次；重複數字不加分，number_hits保存各數字來源。1.0／1.1舊結果仍是單一候選判定，不自動改分。不是比對Answer；缺少數字定義者無法計分。',
        '- 原始檢索、父項召回後、重排序分開比較。重排序若從舊報告執行，前兩階段是來源基準，不是本次重新檢索；重排序分數沿用來源的向量召回 K。',
        '- Evidence_Type 與 Cross_Page_Table 是人工標準分類，不參與模型、檢索或得分；unknown 不能當成非跨頁。',
        '- 未命中但可評分的題目以 0 分計入；失敗、未執行與無法計分不計入平均。不要把不同計入題數的平均直接當作同一題群的提升。',
        '- API token 用量與本機 tokenizer 的內容 token 估算分開；只依實際記錄解讀費用及耗時。',
        '',
        '## 各階段摘要',
        '|階段|可評分題數|原始平均／10|加權平均／10|完整命中題數|零分題數|',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for key, label in STAGES:
        scored = [r['scores'][key] for r in rows if r.get('status') not in ('failed', 'not_run', 'corpus_unavailable')
                  and r.get('scores', {}).get(key, {}).get('score') is not None]
        if not scored:
            continue
        raw = [s['raw_score'] for s in scored if s.get('raw_score') is not None]
        lines.append(f"|{label}|{len(scored)}|{round(mean(raw), 4) if raw else '無法計分'}|"
                     f"{round(mean(s['score'] for s in scored), 4)}|"
                     f"{sum(bool(s.get('complete')) for s in scored)}|{sum(s.get('raw_score') == 0 for s in scored)}|")
    lines += ['', '## 逐題速覽',
              '|ID|題目|標準類型|跨頁|狀態|原始檢索 原始／加權|父項召回 原始／加權|重排序 原始／加權|重排序缺少目標|',
              '|---|---|---|---|---|---|---|---|---|']
    for row in rows:
        ref = row.get('reference') or {}
        scores = row.get('scores') or {}
        def pair(stage):
            value = scores.get(stage)
            return (_value(value.get('raw_score')) + '／' + _value(value.get('score'))) if value else '未執行'
        missing = scores.get('rerank', scores.get('returned', {})).get('missing_targets', [])
        question = str(row.get('Question', '')).replace('|', '\\|').replace('\n', ' ')
        lines.append('|'.join(('', str(row.get('ID', '')), question,
            str(ref.get('Evidence_Type') or '未標註'), str(ref.get('Cross_Page_Table') or '未標註'),
            str(row.get('status', '未知')), pair('retrieval'), pair('returned'), pair('rerank'),
            '；'.join(missing).replace('|', '\\|') or '無', '')))
    lines += ['', '## 逐題評分明細']
    for row in rows:
        lines += ['', f"### ID {row.get('ID', '未知')}：{row.get('Question', '')}",
                  f"狀態：{row.get('status', '未知')}；耗時：{row.get('elapsed_seconds', '未知')} 秒"]
        if row.get('error'):
            lines.append('錯誤／未執行原因：' + str(row['error']))
        for stage, label in STAGES:
            s = row.get('scores', {}).get(stage)
            if not s:
                continue
            lines.append(f"- {label}：原始 {_value(s.get('raw_score'))}／10；加權 {_value(s.get('score'))}／10；"
                         f"年度×標題 {s.get('target_coverage', '未知')}；頁碼核對 {s.get('page_coverage', '未知')}；"
                         f"缺少 {'；'.join(s.get('missing_targets', [])) or '無'}。")
            if stage == 'rerank' or (stage == 'returned' and 'rerank' not in row.get('scores', {})):
                hits = s.get('target_hits', {})
                lines.append('- 首次有效命中名次：' +
                             ('；'.join(f'{name} → Top {rank}' for name, rank in hits.items()) or '無'))
                lines.append('- 命中候選：' +
                             ('；'.join(f"Top {c['effective_rank']} {c['chunk_id']}"
                                       for c in s.get('top20', []) if c.get('matched_targets')) or '無'))
    lines += ['', '## 建議交給 LLM 的分析任務',
              '請以本檔與指定 ID 的分題檔為證據，先報告各階段樣本數、原始／加權平均和完整命中率，再列出低分題的缺少年度×標題、首次有效名次、頁碼核對、證據類型與耗時。區分檢索未命中、重排序淘汰、證據已有但回答失敗；對無法由報告證實的原因標為待查，不猜測表格或文字辨識是否正確。']
    return '\n'.join(lines) + '\n'
