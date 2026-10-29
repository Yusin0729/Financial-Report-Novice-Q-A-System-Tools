"""Local BGE cross-encoder; scores complete query/document pairs without truncation."""
import math
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _tokenizer_from_cache(model_name, revision, cache_dir):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(model_name, revision=revision,
                                        cache_dir=cache_dir, trust_remote_code=False)


@lru_cache(maxsize=1)
def _model_from_cache(model_name, revision, cache_dir, device='cpu'):
    import torch
    from transformers import AutoModelForSequenceClassification
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, revision=revision, cache_dir=cache_dir, trust_remote_code=False,
        use_safetensors=True, dtype=torch.float32)
    return model.to(device).eval()


class BgeRerankError(ValueError):
    """Only controlled messages without document text or credentials."""


class BgeReranker:
    def __init__(self, settings, qa, *, tokenizer=None, model=None):
        self.settings, self.qa = settings, qa
        self.tokenizer, self.model = tokenizer, model
        if (type(qa.bge_rerank_batch_size) is not int or qa.bge_rerank_batch_size < 1
                or type(settings.cpu_threads) is not int or settings.cpu_threads < 1
                or not 1 <= qa.bge_rerank_max_tokens <= 8192):
            raise BgeRerankError('BGE重排序批次、執行緒或長度設定無效')
        from Code.config.devices import select_torch_device
        try:
            self.device_selection = select_torch_device(settings.compute_device)
        except (ValueError, RuntimeError) as error:
            raise BgeRerankError(str(error)) from None
        self.cache = settings.project_root / qa.bge_rerank_cache_dir

    def _tokenizer(self):
        if self.tokenizer is None:
            try:
                if self.settings.hf_disable_xet:
                    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
                self.tokenizer = _tokenizer_from_cache(self.qa.bge_rerank_model,
                    self.qa.bge_rerank_revision, str(self.cache))
            except Exception as error:
                raise BgeRerankError(f'BGE重排序tokenizer載入失敗（{type(error).__name__}）；請確認公開模型下載或本機快取') from None
        return self.tokenizer

    def _model(self):
        if self.model is None:
            try:
                self.model = _model_from_cache(self.qa.bge_rerank_model,
                    self.qa.bge_rerank_revision, str(self.cache), self.device_selection.actual)
            except Exception as error:
                raise BgeRerankError(f'BGE重排序模型載入失敗（{type(error).__name__}）；請確認公開模型下載、本機快取或記憶體') from None
        return self.model

    def rerank(self, question, evidence):
        if not isinstance(question, str) or not question.strip() or not evidence:
            raise BgeRerankError('BGE重排序缺少問題或候選')
        if any(not isinstance(e.get('text'), str) or not e['text'].strip() for e in evidence):
            raise BgeRerankError('BGE重排序候選文字無效')
        tokenizer = self._tokenizer()
        limit = min(self.qa.bge_rerank_max_tokens, int(tokenizer.model_max_length))
        encodings, lengths = [], []
        # Validate every full pair before expensive inference. Never use truncation=True.
        for number, item in enumerate(evidence, 1):
            encoded = tokenizer(question, item['text'], add_special_tokens=True,
                                truncation=False, return_attention_mask=True)
            length = len(encoded['input_ids'])
            if length > limit:
                raise BgeRerankError(f'BGE重排序第{number}個候選含{length} tokens，超過{limit}上限；未截斷、未改用其他模型')
            encodings.append(encoded)
            lengths.append(length)
        model = self._model()
        import torch
        torch.set_num_threads(self.settings.cpu_threads)
        scores = []
        try:
            with torch.inference_mode():
                for start in range(0, len(encodings), self.qa.bge_rerank_batch_size):
                    batch = tokenizer.pad(encodings[start:start+self.qa.bge_rerank_batch_size],
                                          padding=True, return_tensors='pt')
                    batch = {key: value.to(self.device_selection.actual) for key, value in batch.items()}
                    values = model(**batch).logits.reshape(-1).float().cpu().tolist()
                    if len(values) != min(self.qa.bge_rerank_batch_size, len(encodings)-start):
                        raise BgeRerankError('BGE重排序回覆分數筆數不符')
                    scores.extend(values)
        except BgeRerankError:
            raise
        except Exception as error:
            raise BgeRerankError(f'BGE重排序推論失敗（{type(error).__name__}）；未截斷、未重試') from None
        if any(not math.isfinite(v) for v in scores):
            raise BgeRerankError('BGE重排序產生非有限分數')
        selected = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:self.qa.evidence_k]
        output = []
        for rank, index in enumerate(selected, 1):
            logit = scores[index]
            value = 1/(1+math.exp(-logit)) if logit >= 0 else math.exp(logit)/(1+math.exp(logit))
            output.append({**evidence[index], 'rerank_rank': rank, 'rerank_score': value,
                           'rerank_raw_score': logit})
        return output, {'provider': 'bge', 'model': self.qa.bge_rerank_model,
            'model_revision': self.qa.bge_rerank_revision, 'api_called': False,
            'total_tokens': 0, 'local_input_tokens': sum(lengths), 'input_pair_count': len(evidence),
            'max_pair_tokens': max(lengths), 'max_tokens': limit, 'truncation': False,
            'device': self.device_selection.actual, 'requested_device': self.device_selection.requested,
            'device_reason': self.device_selection.reason, 'cpu_threads': self.settings.cpu_threads,
            'batch_size': self.qa.bge_rerank_batch_size, 'score_transform': 'sigmoid',
            'ranking_score': 'raw_logit', 'tie_break': 'input_order'}
