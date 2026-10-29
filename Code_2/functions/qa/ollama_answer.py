"""Local-only Ollama fallback; no model downloads, remote hosts, or truncation."""
import json
import urllib.error
import urllib.request
from Code_2.config.qa import gemini_prompt


class OllamaAnswerer:
    def __init__(self, settings, opener=None):
        self.settings = settings
        from Code_2.functions.qa.services import NoRedirect
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def answer(self, question, evidence):
        qa = self.settings
        model = qa.ollama_model
        if not isinstance(model, str) or not model.strip() or len(model) > 200 or model.endswith('-cloud'):
            raise ValueError('Ollama備援須指定已安裝的本機模型')
        prompt = gemini_prompt(qa.gemini_system_prompt)
        content = json.dumps({'original_question': question,
                              'evidence': [{k: e[k] for k in ('id', 'doc_id', 'page', 'text')} for e in evidence]}, ensure_ascii=False)
        # Conservative byte bound for the installed Llama byte-level tokenizer.
        # Reject rather than allow Ollama to silently drop the start of evidence.
        upper_bound = len((prompt + content).encode('utf-8')) + 512
        if upper_bound + qa.max_output_tokens > qa.ollama_context_tokens:
            raise ValueError(f'Ollama完整證據可能超出上下文{qa.ollama_context_tokens} tokens；未截斷或送出')
        body = {'model': model, 'stream': False,
                'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': content}],
                'options': {'num_ctx': qa.ollama_context_tokens, 'num_predict': qa.max_output_tokens}}
        request = urllib.request.Request('http://127.0.0.1:11434/api/chat',
                    data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with self.opener.open(request, timeout=qa.ollama_timeout) as response:
                raw = response.read(qa.max_response_bytes + 1)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Ollama HTTP {error.code}；請確認本機模型已安裝且可用') from None
        except Exception as error:
            raise RuntimeError(f'Ollama連線失敗（{type(error).__name__}）；請啟動Ollama，並確認本機模型{model}可用') from None
        if len(raw) > qa.max_response_bytes:
            raise ValueError('Ollama回覆過大')
        try:
            response = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ValueError('Ollama回覆格式無效') from None
        if not isinstance(response, dict) or response.get('done') is not True or response.get('done_reason') != 'stop':
            raise ValueError('Ollama未正常完成或輸出截斷；不交付部分答案')
        text = (response.get('message') or {}).get('content')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Ollama未回傳回答文字')
        usage = {'provider': 'ollama', 'model': response.get('model', model), 'system_prompt': prompt,
                 'input_tokens': response.get('prompt_eval_count'), 'output_tokens': response.get('eval_count'),
                 'total_duration_ns': response.get('total_duration'), 'context_tokens': qa.ollama_context_tokens,
                 'local_inference': True}
        return {'status': 'answered', 'format': 'markdown', 'text': text, 'calculation_source': 'llm'}, usage
