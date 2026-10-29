"""新回答直接顯示模型文字；舊結構化報告驗證保留供相容用途。"""
import ast
import re
from decimal import Decimal, localcontext, DecimalException
from Code_2.config.qa import MODE_LABELS


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def citation(value, evidence):
    if (not isinstance(value, dict) or set(value) != {'id', 'quote'} or
            value.get('id') not in evidence or not nonempty(value.get('quote')) or
            value['quote'] not in evidence[value['id']]['text']):
        raise ValueError('回答引用不存在或摘錄不是實際證據原文')
    return value


def number(raw):
    if not isinstance(raw, str) or len(raw) > 100:
        raise ValueError('運算值須為來源數字字串')
    value = raw.strip()
    if not re.fullmatch(r'(?:-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\))%?', value):
        raise ValueError('運算數字格式無效')
    percent = value.endswith('%')
    value = value.removesuffix('%').replace(',', '')
    if value.startswith('('):
        value = '-' + value[1:-1]
    result = Decimal(value)
    return result / 100 if percent else result


def calculate(plan, evidence):
    if (not isinstance(plan, dict) or set(plan) != {'id', 'expression', 'operands'} or
            not re.fullmatch(r'calc[1-9]\d*', str(plan.get('id', ''))) or
            not nonempty(plan.get('expression')) or len(plan['expression']) > 300 or
            not isinstance(plan.get('operands'), list) or not 1 <= len(plan['operands']) <= 20):
        raise ValueError('計算規格無效')
    variables, operands = {}, []
    for i, operand in enumerate(plan['operands']):
        if not isinstance(operand, dict) or set(operand) != {'value', 'unit', 'period', 'citation'}:
            raise ValueError('運算輸入欄位無效')
        cite = citation(operand['citation'], evidence)
        if (not nonempty(operand['unit']) or not nonempty(operand['period']) or
                operand['unit'] == 'unknown' or operand['period'] == 'unknown' or
                operand['unit'] not in cite['quote'] or operand['period'] not in cite['quote']):
            raise ValueError('運算單位或期間缺乏原文證據；請提供含單位與期間的來源')
        value = number(operand['value'])
        # 邊界檢查避免以來源1234中的234、或負數中的正數作依據。
        if not re.search(r'(?<![\d.,(\-])' + re.escape(operand['value']) + r'(?![\d.,)%])', cite['quote']):
            raise ValueError('運算數字不是所引用原文中的完整數值')
        unit = '純數' if operand['value'].endswith('%') else operand['unit']
        variables[f'x{i}'] = (value, unit)
        operands.append(dict(operand))
    tree = ast.parse(plan['expression'], mode='eval')
    if len(list(ast.walk(tree))) > 100:
        raise ValueError('算式過長')
    used = set()

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name) and node.id in variables:
            used.add(node.id)
            return variables[node.id]
        if isinstance(node, ast.BinOp):
            a, ua = visit(node.left)
            b, ub = visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)) and ua == ub:
                return (a + b if isinstance(node.op, ast.Add) else a - b), ua
            if isinstance(node.op, ast.Div) and b != 0 and (ua == ub or ub == '純數'):
                return a / b, ('純數' if ua == ub else ua)
            if isinstance(node.op, ast.Mult) and '純數' in (ua, ub):
                return a * b, (ub if ua == '純數' else ua)
        raise ValueError('算式僅接受來源變數及單位相容的四則運算；不猜測單位換算')
    try:
        with localcontext() as context:
            context.prec = 28
            value, unit = visit(tree)
    except (DecimalException, SyntaxError):
        raise ValueError('運算失敗，未交付猜測結果') from None
    if used != set(variables):
        raise ValueError('算式有未使用的來源輸入')
    return {**plan, 'operands': operands, 'result': format(value, 'f'), 'result_unit': unit,
            'precision': 'Decimal 28位有效數字；除法可能四捨五入',
            'periods': list(dict.fromkeys(o['period'] for o in operands))}


def validate_answer(answer, sources):
    # Direct-text responses do not enter legacy quote/calculation validation.
    if isinstance(answer, dict) and answer.get('format') == 'markdown':
        if not isinstance(answer.get('text'), str) or not answer['text'].strip():
            raise ValueError('LLM未回傳回答文字')
        return answer
    evidence = {e['id']: e for e in sources}
    if (not isinstance(answer, dict) or set(answer) != {'status', 'reason', 'claims', 'calculations'} or
            answer['status'] not in ('answered', 'insufficient_evidence') or
            not isinstance(answer['reason'], str) or not isinstance(answer['claims'], list) or
            not isinstance(answer['calculations'], list)):
        raise ValueError('回答格式無效')
    if len(answer['calculations']) > 20 or len(answer['claims']) > 50:
        raise ValueError('回答項目過多')
    computed = {}
    for plan in answer['calculations']:
        result = calculate(plan, evidence)
        if result['id'] in computed:
            raise ValueError('計算id重複')
        computed[result['id']] = result
    claims, used = [], set()
    for claim in answer['claims']:
        if (not isinstance(claim, dict) or set(claim) != {'text', 'kind', 'citations'} or
                not nonempty(claim['text']) or claim['kind'] not in ('quoted', 'calculated', 'inference') or
                not isinstance(claim['citations'], list) or not claim['citations']):
            raise ValueError('每項事實或推論必須附來源')
        for cite in claim['citations']:
            citation(cite, evidence)
        # 衍生數字只能由已驗證算式代入，阻擋沒有引文依據的數字。
        numeric_pattern = r'(?<!\d)-?\d[\d,]*(?:\.\d+)?%?'
        raw_claim = re.sub(r'\{\{calc[1-9]\d*\}\}', '', claim['text'])
        cited_numbers = {n.replace(',', '') for c in claim['citations']
                         for n in re.findall(numeric_pattern, c['quote'])}
        if any(n.replace(',', '') not in cited_numbers for n in re.findall(numeric_pattern, raw_claim)):
            raise ValueError('回答包含引文未出現的數字；衍生數字須交程式計算')
        ids = re.findall(r'\{\{(calc[1-9]\d*)\}\}', claim['text'])
        if any(cid not in computed for cid in ids) or (claim['kind'] == 'calculated' and not ids):
            raise ValueError('計算引用缺失')
        if ids and claim['kind'] != 'calculated':
            raise ValueError('計算結果須標為calculated')
        text = claim['text']
        cited = {c['id'] for c in claim['citations']}
        for cid in ids:
            result = computed[cid]
            if any(o['citation']['id'] not in cited for o in result['operands']):
                raise ValueError('計算事實未引用全部輸入來源')
            text = text.replace('{{' + cid + '}}', f'{result["result"]}（{result["result_unit"]}）')
            used.add(cid)
        if '{{' in text or '}}' in text:
            raise ValueError('未解決的回答佔位符')
        claims.append({**claim, 'text': text})
    if used != set(computed):
        raise ValueError('有未使用的計算')
    if answer['status'] == 'answered' and not claims:
        raise ValueError('回答成功但沒有附來源事實')
    if answer['status'] == 'insufficient_evidence' and not answer['reason'].strip():
        raise ValueError('證據不足須說明原因')
    return {**answer, 'claims': claims, 'calculations': list(computed.values())}


def render_answer(result):
    if result['status'] == 'failed':
        return f'問答失敗（{result["stage"]}）：{result["error"]}'
    if result['status'] == 'no_results':
        return result['message']
    if result['status'] in ('retrieved', 'reranked'):
        reranked = result['status'] == 'reranked'
        sources = result['evidence'] if reranked else result['retrieved_evidence']
        lines = [('重排序已完成' if reranked else '向量檢索排序已完成') + f'，共{len(sources)}塊。',
                 '已依所選模式停止，未生成回答。']
        for source in sources:
            rank = source['rerank_rank'] if reranked else source['retrieval_rank']
            score = (f'重排序相關性分數：{source["rerank_score"]}；原召回第{source["retrieval_rank"]}名'
                     if reranked else f'餘弦距離：{source["retrieval_distance"]}')
            lines.extend([f'第{rank}名 [{source["id"]}] {source["chunk_id"]}｜{score}',
                          f'{source["doc_id"]}｜PDF實體頁序 {", ".join(map(str, source["page"]))}', source['text']])
        return '\n\n'.join(lines)
    answer = result['answer']
    if answer.get('format') == 'markdown':
        return answer['text']
    incomplete = answer['status'] == 'insufficient_evidence'
    lines = ['有證據支持的部分' if incomplete and answer['claims'] else '證據不足' if incomplete else '回答']
    if answer['reason'] and not incomplete:
        lines.append(answer['reason'])
    cited = set()
    for claim in answer['claims']:
        ids = list(dict.fromkeys(c['id'] for c in claim['citations']))
        cited.update(ids)
        prefix = {'quoted': '', 'inference': '推論：', 'calculated': '程式計算：'}[claim['kind']]
        lines.append(prefix + claim['text'] + ' ' + ''.join(f'[{cid}]' for cid in ids))
    if incomplete:
        lines.append('缺少的資料／尚無法確認的部分\n' + answer['reason'])
    for e in result['evidence']:
        if e['id'] in cited:
            lines.append(f'[{e["id"]}] {e["doc_id"]}｜PDF實體頁序 {", ".join(map(str, e["page"]))}｜{e["chunk_id"]}')
    for calc in answer['calculations']:
        values = '; '.join(f'x{i}={o["value"]} {o["unit"]}（{o["period"]}）' for i, o in enumerate(calc['operands']))
        lines.append(f'{calc["id"]}：{calc["expression"]}；{values}；結果 {calc["result"]} {calc["result_unit"]}')
    return '\n\n'.join(lines)


def render_qa_report(result):
    """人可讀的完整實驗報告；不要求使用者閱讀JSON。"""
    mode = result.get('mode', 'answer')
    # 舊紀錄沒有completed_stages時，僅從實際保存欄位辨識已完成部分。
    completed = result.get('completed_stages')
    if completed is None:
        completed = [stage for stage, field in (('query_embedding', 'query_embedding'),
                     ('retrieval', 'retrieved_evidence'), ('rerank', 'rerank'), ('answer', 'answer')) if field in result]
    lines = ['# 財報查詢紀錄', '時間（台北）：' + result['created_at'],
             '## 原始問題', result.get('original_question', ''), '## 執行結果', render_answer(result),
             '## 本題執行設定',
             '- 執行模式：' + MODE_LABELS.get(mode, str(mode)),
             '- 問題重寫：停用',
             '- 問答狀態：' + {'answered': '已回答，待品質核對',
                                  'insufficient_evidence': '證據不足／部分回答',
                                  'failed': '執行失敗', 'retrieved': '已完成向量排序，依模式停止',
                                  'reranked': '已完成重排序，依模式停止',
                                  'no_results': '檢索完成但無候選，未執行後續階段'}.get(result['status'], result['status']),
             '- 查詢索引模型：' + result.get('backend', '尚未選定'),
             '- 索引：' + result.get('collection', '尚未選定'),
             '- 重排序模型設定：' + result.get('rerank_model', '未設定'),
             '- 回答模型設定：' + result.get('answer_model', '未設定'),
             '- 實際回答模型：' + str(result.get('generation', {}).get('provider', result.get('answer_provider', '未知'))) + ' / ' + str(result.get('generation', {}).get('model', result.get('answer_model', '未知'))),
             '- Ollama備援：' + ('是；Gemini失敗原因：' + str(result.get('generation', {}).get('primary_attempt', {}).get('error', '未知')) if result.get('generation', {}).get('fallback_used') else '否'),
             '- 提示詞版本：' + result.get('prompt_version', '未知')]
    if result.get('report_kind') == 'saved_rerank':
        lines.extend(['## 舊報告來源', str(result.get('source_run')),
                      '沿用已保存的候選全文；本次只呼叫重排序，沒有重新embedding／檢索或回答。'])
    answer_provider = 'Ollama' if result.get('generation', {}).get('provider') == 'ollama' else ('GPT' if result.get('answer_provider') == 'openai' else 'Gemini')
    lines.extend(['## 階段執行情況', '| 階段 | 狀態 |', '| --- | --- |'])
    for key, label in (('query_embedding', '問題向量'), ('retrieval', '向量檢索與初步排序'),
                       ('rerank', '重排序'), ('answer', answer_provider+'回答與引用驗證')):
        if key in completed:
            state = '已完成'
        elif key == 'rerank' and result.get('rerank_skipped'):
            state = '使用者選擇略過，依向量排名取證據'
        elif (key == 'rerank' and mode == 'retrieve') or (key == 'answer' and mode != 'answer'):
            state = '所選模式不執行'
        elif key in ('rerank', 'answer') and not result.get('retrieved_evidence') and 'retrieval' in completed:
            state = '無候選，不執行'
        else:
            state = '未完成／因前階段失敗未執行' if result['status'] == 'failed' else '未執行'
        lines.append(f'| {label} | {state} |')
    filters = result.get('filters')
    conditions = filters.get('$and', [filters]) if filters else []
    labels = {'stock_code': '股票代號', 'years': '內容年度', 'report_year': '報告年度（舊紀錄）'}
    readable_filters = '；'.join(labels.get(k, k) + '：' + str(v.get('$contains', v) if isinstance(v, dict) else v) for c in conditions for k, v in c.items())
    lines.extend(['- 篩選條件：' + (readable_filters or '未限制公司／內容年度'),
                  f'- 候選上限：{result.get("retrieve_k", "未知")}；回答證據上限：{result.get("evidence_k", "未知")}',
                  '- 額外帶回標題父項：' + ('是' if result.get('include_heading_parent') else '否'),
                  '## 初步召回結果',
                  '餘弦距離越小表示向量越接近；不能當成答案正確率，也不能和重排序分數直接比較。'])
    sources = result.get('retrieved_evidence', [])
    if not sources:
        lines.append('尚無可用的召回片段。')
    for source in sources:
        lines.extend([f'### 第{source["retrieval_rank"]}筆 [{source["id"]}]',
                      f'文件：{source["doc_id"]}；PDF實體頁序：{", ".join(map(str, source["page"]))}',
                      f'Chunk：{source["chunk_id"]}；餘弦距離：{source["retrieval_distance"]}',
                      '完整可讀片段：', source['text']])
    lines.extend(['## 重排序結果', '以下為所選模型的相關性排序；分數不代表答案正確率，不同模型分數尺度不可直接比較。'])
    if result.get('rerank_skipped'):
        lines.append('已略過重排序；依向量檢索順序取指定數量的證據，不提供重排分數。')
    elif not result.get('rerank'):
        lines.append('所選模式只排序，不執行重排序。' if mode == 'retrieve' else
                     '無候選，不執行重排序。' if not sources and 'retrieval' in completed else '重排序尚未完成。')
    for source in result.get('evidence', []):
        if result.get('rerank_skipped'):
            lines.append(f'- 向量第{source["retrieval_rank"]}名 [{source["id"]}] {source["chunk_id"]}；餘弦距離：{source["retrieval_distance"]}')
            continue
        lines.append(f'- 第{source.get("rerank_rank", "未知")}名 [{source["id"]}] '
                     f'{source["chunk_id"]}；相關性分數：{source.get("rerank_score", "未知")}；'
                     f'原召回排名：{source["retrieval_rank"]}')
    lines.extend(['## 模型用量', '未回報的用量為未知，不視為0；本報告不估算帳單或免費額度餘額。'])
    if result.get('query_embedding', {}).get('cache', {}).get('hit'):
        lines.append('- 問題向量命中題庫快取，本次未重新向量化；問題embedding API tokens：0。')
    elif result.get('backend') == 'voyage':
        lines.append('- Voyage問題向量處理tokens：' + str(result.get('query_embedding', {}).get('usage', {}).get('total_tokens') or '未知'))
    else:
        lines.append('- 問題向量使用本機BGE，未呼叫Voyage查詢向量API。')
    if result.get('rerank_skipped'):
        lines.append('使用者選擇略過重排序，未呼叫服務，重排序用量不適用。')
    elif result.get('rerank', {}).get('provider') == 'bge':
        local = result['rerank']
        lines.append('- BGE本機重排序；API tokens：0；本機輸入tokens：' + str(local.get('local_input_tokens', '未知')))
        lines.append('- 本機模型版本：' + str(local.get('model_revision', '未知')) + '；未截斷：' + str(not local.get('truncation', True)))
    elif mode != 'retrieve':
        lines.append('- Voyage重排序處理tokens：' + str(result.get('rerank', {}).get('total_tokens') or '未知／未執行'))
    else:
        lines.append('所選模式不執行重排序，重排序用量不適用。')
    if mode == 'answer':
        lines.extend(['- '+answer_provider+'輸入預檢tokens：' + str(result.get('generation', {}).get('input_tokens') or '未知／未執行'),
                      '- '+answer_provider+'實際模型版本：' + str(result.get('generation', {}).get('model_version') or '未知／未執行')])
        usage = result.get('generation', {}).get('usage', {})
        token_fields = (('input_tokens','輸入tokens'),('output_tokens','輸出tokens（含推理）'),('total_tokens','總tokens')) if result.get('answer_provider')=='openai' else (('promptTokenCount','輸入tokens'),('candidatesTokenCount','回答tokens'),('thoughtsTokenCount','思考tokens'),('totalTokenCount','總tokens'))
        for key, label in token_fields:
            lines.append(f'- {answer_provider} {label}：{usage.get(key, "未知")}')
    else:
        lines.append(f'所選模式不執行{answer_provider}，沒有呼叫token預檢或生成回答；{answer_provider}用量不適用。')
    if result['status'] == 'failed':
        lines.extend(['## 失敗位置', '階段：' + result['stage'], result['error'],
                      '本次流程已停止；模型切換情況見上方設定及generation紀錄。以上保留失敗前已完成的資料。'])
    lines.extend(['## 核對限制', '引用存在與摘錄相符不代表語意已人工驗收；請核對財務期間、單位、欄位及來源。'])
    return '\n\n'.join(lines) + '\n'
