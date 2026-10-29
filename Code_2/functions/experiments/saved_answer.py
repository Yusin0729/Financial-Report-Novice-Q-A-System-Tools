"""EXPERIMENT_ONLY：以已保存的重排序報告產生盲測回答。

只讀來源報告的 ID、Question 與 query.evidence；刻意不讀取評分用 reference/Answer。
"""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from Code_2.config.embedding import Settings
from Code_2.config.qa import QASettings, PROMPT_VERSION
from Code_2.functions.qa.services import GeminiAnswerer
from Code_2.functions.qa.answers import validate_answer, render_answer
from Code.functions.embedding.keys import service_key

TAIPEI = timezone(timedelta(hours=8), 'Asia/Taipei')


def run(source_dir, *, root=None, answer_model='gemini-3.1-flash-lite'):
    """EXPERIMENT_ONLY：盲測回答；不存入或讀取測試集標準答案。"""
    project = Path(root or Path(__file__).resolve().parents[3]).resolve()
    from Code_2.functions.web.service import report_path
    source = report_path(Settings(project_root=project), source_dir, 'result.json')
    source_data = json.loads(source.read_text(encoding='utf-8'))
    rows = []
    for row in source_data.get('rows', []):
        # 刻意只取這三個欄位；不觸碰 reference（其中包含 Answer）。
        question = row.get('Question')
        query = row.get('query') or {}
        evidence = query.get('evidence') or []
        if not isinstance(question, str) or not question.strip() or not isinstance(evidence, list):
            continue
        rows.append((str(row.get('ID', '')), question, evidence))
    qa = QASettings(answer_model=answer_model, answer_provider='gemini',
                    rerank_enabled=False, rerank_profile=None, answer_profile=None)
    answerer = GeminiAnswerer(service_key(project, 'GEMINI_API_KEY'), qa)
    output = project / 'Output' / 'reponse_answer' / ('qa_' + datetime.now(TAIPEI).strftime('%Y%m%d_%H-%M-%S_%f'))
    output.mkdir(parents=True, exist_ok=False)
    result_rows = []
    for idx, (qid, question, evidence) in enumerate(rows, 1):
        try:
            answer, usage = answerer.answer(question, evidence)
            answer = validate_answer(answer, evidence)
            result_rows.append({'ID': qid, 'Question': question, 'status': answer['status'],
                                'answer': answer, 'evidence': evidence, 'generation': usage})
        except Exception as error:
            result_rows.append({'ID': qid, 'Question': question, 'status': 'failed',
                                'error': str(error), 'evidence': evidence})
        print(f'{idx}/{len(rows)}', flush=True)
    payload = {'schema_version': 'financial-blind-answer/1.0',
               'source_run': source_dir,
               'source_report_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'report_kind': 'saved_report_blind_answer',
               'answer_model': answer_model, 'answer_provider': 'gemini',
               'prompt_version': PROMPT_VERSION, 'answer_count': len(result_rows),
               'completed_count': sum(r['status'] != 'failed' for r in result_rows),
               'failed_count': sum(r['status'] == 'failed' for r in result_rows),
               'rows': result_rows,
               'created_at': datetime.now(TAIPEI).isoformat()}
    (output / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 盲測回答報告', '', f'- 來源測報：`{source_dir}`',
             f'- 回答模型：`{answer_model}`', '- 測試集標準答案：未讀取', '']
    for row in result_rows:
        lines += [f'## ID {row["ID"]}', '', row['Question'], '']
        if row['status'] == 'failed':
            lines += [f'執行失敗：{row.get("error", "未知錯誤")}', '']
            continue
        view = {'status': row['status'], 'answer': row['answer'], 'evidence': row['evidence'],
                'mode': 'answer', 'answer_model': answer_model, 'answer_provider': 'gemini',
                'prompt_version': PROMPT_VERSION}
        lines += [render_answer(view), '']
    (output / 'answer.md').write_text('\n'.join(lines), encoding='utf-8')
    from Code_2.functions.experiments.question_reports import payloads
    views = {'rows': [{'ID': r['ID'], 'Question': r['Question'], 'query': {**r, 'mode': 'answer'}} for r in result_rows]}
    for path, raw in payloads({'json': output/'result.json', 'project_root': project}, views).items():
        with path.open('xb') as stream:
            stream.write(raw)
    return output, payload
