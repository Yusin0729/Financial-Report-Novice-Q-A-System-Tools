"""獨立工作程序：JSON經stdin傳入；不把問題、金鑰或HTTP body寫入程序日誌。"""
import contextlib
import json
import re
import sys
from Code_2.config.embedding import Settings
from Code_2.functions.web.service import validate_task, execute_task, task_outcome


def emit(event):
    sys.__stdout__.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
    sys.__stdout__.flush()


class Progress:
    def __init__(self):
        self.pending = ''

    def write(self, text):
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            match = re.fullmatch(r'向量化 ([\w.-]+)：(\d+)–(\d+)/(\d+)', line.strip())
            if match:
                doc, start, end, total = match.groups()
                emit({'type': 'progress', 'message': f'正在向量化 {doc}：第{start}至{end}筆，共{total}筆'})
            elif re.fullmatch(r'索引比較 \d+/\d+：(bge|voyage) financial_[a-f0-9]{24}',line.strip()):
                emit({'type':'progress','message':line.strip()})
            elif re.fullmatch(r'舊報告重排序 \d+/\d+：ID .{1,100}',line.strip()):
                emit({'type':'progress','message':line.strip()})
            elif re.fullmatch(r'批次測試 \d+/\d+：ID .{1,100}',line.strip()):
                emit({'type':'progress','message':line.strip()})
            elif line.startswith('準備模型 '):
                emit({'type': 'progress', 'message': '準備模型；首次使用可能下載公開權重，請稍候。'})
        # 不回傳其他套件的原始輸出，避免意外暴露憑證／HTTP資料。
        if len(self.pending) > 4096:
            self.pending = ''
        return len(text)

    def flush(self):
        pass


def main():
    try:
        data = json.loads(sys.stdin.read())
        settings = Settings()
        task = validate_task(data, settings)
        emit({'type': 'progress', 'message': {'prepare': '正在核對來源並執行前處理。',
              'embed': '正在核對來源、欄位設定與模型長度。', 'query': '正在依所選模式執行查詢。', 'evaluate': '正在逐題測試並記錄來源命中。', 'make-charts':'正在使用既有排名製作圖表報告；不呼叫模型。', 'rerank-report':'正在沿用舊報告候選重排序；不重新檢索。'}[task['action']]})
        with contextlib.redirect_stdout(Progress()), contextlib.redirect_stderr(Progress()):
            result = execute_task(task, settings)
        emit({'type': 'result', 'outcome': task_outcome(result), 'result': result})
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # 預期／未知錯誤皆只傳安全類型；詳細可讀失敗資訊由既有核心結果提供。
        emit({'type': 'failure', 'message': f'工作未完成（{type(error).__name__}），未自動重試。'})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
