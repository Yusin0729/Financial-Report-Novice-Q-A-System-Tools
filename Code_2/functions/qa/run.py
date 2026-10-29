"""單題問答操作邊界：只回傳結果，不產生實驗測報。"""
from Code_2.functions.qa.pipeline import ask


def run_question(question, settings, *, ask_function=None, **kwargs):
    try:
        result = (ask_function or ask)(question, settings, **kwargs)
    except (Exception, KeyboardInterrupt) as error:
        result = {'schema_version': 'financial-qa/1.1', 'original_question': question,
                  'mode': kwargs.get('mode', 'answer'), 'completed_stages': [],
                  'status': 'failed', 'stage': 'question_execution',
                  'error': f'問答未正常完成（{type(error).__name__}）；未重試',
                  'evidence': [], 'retrieved_evidence': []}
    # 單題不保留目錄或輸出檔；題庫向量快取仍由核心正常處理。
    return {**result, 'export_status': 'disabled'}
