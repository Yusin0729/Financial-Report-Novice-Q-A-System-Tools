"""Voyage重排序與Gemini文字回答；不要求JSON或由程式驗算。"""
import json
import math
import urllib.error
import urllib.request
from Code_2.config.qa import SYSTEM_PROMPT, RESPONSE_SCHEMA, gemini_prompt


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class VoyageReranker:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    def rerank(self, question, evidence):
        # SDK的rerank預設會截斷；明確關閉，由服務端精確檢查模型長度限制。
        try:
            response = self.client.rerank(query=question, documents=[e['text'] for e in evidence],
                                          model=self.settings.rerank_model,
                                          top_k=min(self.settings.evidence_k, len(evidence)), truncation=False)
        except Exception as error:
            raise RuntimeError(f'Voyage重排序失敗（{type(error).__name__}）；未截斷、未重試') from None
        expected = min(self.settings.evidence_k, len(evidence))
        seen, output = set(), []
        if len(response.results) != expected:
            raise ValueError('重排序回覆筆數不符')
        for rank, row in enumerate(response.results, 1):
            index, score = row.index, row.relevance_score
            if (type(index) is not int or not 0 <= index < len(evidence) or index in seen or
                    type(score) not in (int, float) or not math.isfinite(score)):
                raise ValueError('重排序回覆索引或分數無效')
            seen.add(index)
            output.append({**evidence[index], 'rerank_rank': rank, 'rerank_score': score})
        if any(a['rerank_score'] < b['rerank_score'] for a, b in zip(output, output[1:])):
            raise ValueError('重排序分數未依序排列')
        return output, {'model': self.settings.rerank_model, 'total_tokens': getattr(response, 'total_tokens', None)}


class GeminiAnswerer:
    def __init__(self, key, settings, opener=None):
        self.key, self.settings = key, settings
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def post(self, method, body):
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.settings.answer_model}:{method}'
        request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                         headers={'Content-Type': 'application/json', 'x-goog-api-key': self.key},
                                         method='POST')
        try:
            with self.opener.open(request, timeout=self.settings.timeout) as response:
                raw = response.read(self.settings.max_response_bytes + 1)
            if len(raw) > self.settings.max_response_bytes:
                raise ValueError('Gemini回覆過大')
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Gemini HTTP {error.code}；額度／權限／服務異常，已停止，未重試或切換模型') from None
        except Exception as error:
            raise RuntimeError(f'Gemini請求失敗（{type(error).__name__}）；已停止，未重試') from None

    def answer(self, question, evidence):
        prompt = gemini_prompt(self.settings.gemini_system_prompt)
        self.last_attempt = {'model': self.settings.answer_model, 'system_prompt': prompt,
                             'prompt_source': 'custom' if self.settings.gemini_system_prompt is not None else 'default'}
        content = json.dumps({'original_question': question,
                              'evidence': [{k: e[k] for k in ('id', 'doc_id', 'page', 'text')} for e in evidence]},
                             ensure_ascii=False)
        body = {'systemInstruction': {'parts': [{'text': prompt}]},
                'contents': [{'role': 'user', 'parts': [{'text': content}]}],
                'generationConfig': {'maxOutputTokens': self.settings.max_output_tokens}}
        counted = self.post('countTokens', {'generateContentRequest': {
            **body, 'model': 'models/' + self.settings.answer_model}})
        tokens = counted.get('totalTokens')
        if type(tokens) is not int or tokens < 1:
            raise ValueError('Gemini未回傳有效輸入token數')
        self.last_attempt['input_tokens'] = tokens
        if tokens > self.settings.max_input_tokens:
            raise ValueError(f'回答輸入{tokens} tokens超過預算{self.settings.max_input_tokens}，未截斷或生成')
        response = self.post('generateContent', body)
        self.last_attempt.update(model_version=response.get('modelVersion'), usage=response.get('usageMetadata', {}))
        candidates = response.get('candidates', [])
        if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
            raise ValueError('Gemini未正常完成，可能拒答或輸出截斷；不交付部分答案')
        parts = candidates[0].get('content', {}).get('parts', [])
        text = ''.join(p.get('text', '') for p in parts if not p.get('thought', False))
        if not text.strip():
            raise ValueError('Gemini未回傳回答文字')
        return {'status': 'answered', 'format': 'markdown', 'text': text,
                'calculation_source': 'llm'}, dict(self.last_attempt)
