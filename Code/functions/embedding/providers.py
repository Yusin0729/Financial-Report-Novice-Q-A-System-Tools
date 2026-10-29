"""模型適配與回覆檢查；只有建立BgeProvider時才載入第三方模型。

不得以encode的預設截斷取代輸入長度檢查。此模組不負責資料庫或寫檔。
"""
import math


def validate_vectors(vectors, *, expected_count, dimension):
    """拒絕缺筆、維度混用、NaN／Infinity及零向量。"""
    if len(vectors) != expected_count:
        raise ValueError('向量回覆筆數與輸入不符')
    result = []
    for vector in vectors:
        if len(vector) != dimension:
            raise ValueError('向量維度與模型設定不符')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
            raise ValueError('向量包含非數值或非有限值')
        if not any(v != 0 for v in vector):
            raise ValueError('模型回傳零向量')
        result.append([float(v) for v in vector])
    return result


class BgeProvider:
    """本機 BGE，使用模型原生長度上限，不沿用舊碼的1024截斷。"""
    def __init__(self, *, model_name, cache_dir, revision, model=None, download_settings=None, device='cpu'):
        self.model_name, self.cache_dir, self.revision = model_name, cache_dir, revision
        self._model = model
        self.download_settings = download_settings
        from Code.config.devices import select_torch_device
        self.device_selection = select_torch_device(device)
        if model is None:
            try:
                from transformers import AutoTokenizer
            except ImportError as error:
                raise RuntimeError('尚未安裝模型套件；第五階段請使用Code/.venv並參閱Code/README.md') from error
            options = dict(cache_dir=str(cache_dir), revision=revision, trust_remote_code=False)
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True, **options)
            except OSError:
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, **options)
            self.limit, self.dimension = 8192, 1024  # BAAI/bge-m3鎖定版本的官方規格。
        else:
            self.tokenizer = model.tokenizer
            self.limit = model.max_seq_length
            self.dimension = model.get_embedding_dimension()
        if type(self.limit) is not int or self.limit < 1 or type(self.dimension) is not int or self.dimension < 1:
            raise ValueError('無法確認模型的輸入上限或向量維度')

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            from pathlib import Path
            snapshot = Path(self.cache_dir) / ('models--' + self.model_name.replace('/', '--')) / 'snapshots' / str(self.revision)
            cached = all((snapshot / name).is_file() for name in (
                'modules.json', 'config.json', 'sentence_bert_config.json', '1_Pooling/config.json')) and any((snapshot / name).is_file()
                     for name in ('model.safetensors', 'pytorch_model.bin'))
            if not cached and self.download_settings is not None:
                from Code.functions.embedding.model_download import download
                download(self.download_settings)
                cached = True
            model = SentenceTransformer(self.model_name, device=self.device_selection.actual, cache_folder=str(self.cache_dir),
                                        revision=self.revision, trust_remote_code=False, local_files_only=cached)
            if model.max_seq_length != self.limit or model.get_embedding_dimension() != self.dimension:
                raise ValueError('實際模型與已核對的BGE規格不符，未執行encode')
            self._model = model
        return self._model

    @property
    def runtime_config(self):
        return {'requested_device': self.device_selection.requested,
                'device': self.device_selection.actual, 'device_reason': self.device_selection.reason}

    @property
    def profile(self):
        return {'backend': 'bge', 'model': self.model_name, 'revision': self.revision,
                'dimension': self.dimension, 'max_tokens': self.limit, 'normalized': True}

    def count_tokens(self, texts):
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError('embedding輸入必須為非空文字清單')
        encoded = self.tokenizer(texts, add_special_tokens=True, truncation=False, padding=False)
        return [len(ids) for ids in encoded['input_ids']]

    def embed(self, texts, *, batch_size):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError('batch_size必須為正整數')
        counts = self.count_tokens(texts)
        if any(count > self.limit for count in counts):
            raise ValueError('BGE輸入超過模型token上限，未截斷或執行向量化')
        values = self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                   show_progress_bar=False, convert_to_numpy=True).tolist()
        return validate_vectors(values, expected_count=len(texts), dimension=self.dimension)


class VoyageProvider:
    """建庫使用document；問答使用query，兩者皆不截斷。"""
    def __init__(self, *, client, model_name, max_tokens, batch_tokens):
        self.client, self.model_name = client, model_name
        self.limit, self.batch_tokens, self.dimension = max_tokens, batch_tokens, 1024

    @property
    def profile(self):
        return {'backend': 'voyage', 'model': self.model_name, 'dimension': self.dimension,
                'max_tokens': self.limit, 'input_type': 'document', 'truncation': False}

    def count_tokens(self, texts):
        # Voyage會在document前加此前綴；計數包含前綴，不漏算模型實際輸入。
        return [self.client.count_tokens(['Represent the document for retrieval: ' + text], model=self.model_name)
                for text in texts]

    def embed(self, texts, *, batch_size):
        counts = self.count_tokens(texts)
        if len(texts) > batch_size or any(c > self.limit for c in counts) or sum(counts) > self.batch_tokens:
            raise ValueError('Voyage請求超過單筆／批次token或筆數上限，未送出')
        try:
            response = self.client.embed(texts, model=self.model_name, input_type='document', truncation=False)
        except Exception as error:
            # SDK錯誤可能包含HTTP body；不回顯金鑰或財報文字。
            raise RuntimeError(f'Voyage呼叫失敗（{type(error).__name__}），未自動重試') from None
        return validate_vectors(response.embeddings, expected_count=len(texts), dimension=self.dimension)

    def embed_query(self, question):
        if not isinstance(question, str) or not question.strip():
            raise ValueError('問題不得空白')
        count = self.client.count_tokens(['Represent the query for retrieving supporting documents: ' + question],
                                         model=self.model_name)
        if type(count) is not int or not 0 < count <= self.limit:
            raise ValueError('Voyage問題超過token上限或無法計數，未送出')
        try:
            response = self.client.embed([question], model=self.model_name, input_type='query', truncation=False)
        except Exception as error:
            raise RuntimeError(f'Voyage查詢向量失敗（{type(error).__name__}），未重試') from None
        self.last_query_usage = {'model': self.model_name, 'total_tokens': getattr(response, 'total_tokens', None)}
        return validate_vectors(response.embeddings, expected_count=1, dimension=self.dimension)[0]


def create_provider(backend, settings):
    if backend == 'bge':
        import os
        if settings.hf_disable_xet:
            os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
        import torch
        torch.set_num_threads(settings.cpu_threads)
        return BgeProvider(model_name=settings.bge_model, cache_dir=settings.model_cache,
                           revision=settings.bge_revision, download_settings=settings, device=settings.compute_device)
    if backend != 'voyage':
        raise ValueError('模型只接受bge或voyage')
    if not settings.allow_voyage_api:
        raise ValueError('Voyage真實API尚未啟用；本次不外傳財報。需要時明確加--allow-voyage-api')
    import voyageai
    from Code.functions.embedding.keys import voyage_key
    if settings.embedding_profile:
        from Code.functions.embedding.api_settings import resolve_profile
        profile, key = resolve_profile(settings.project_root, settings.embedding_profile, 'embedding')
        if profile['provider'] != 'voyage' or profile['model'] != settings.voyage_model:
            raise ValueError('Embedding設定與索引模型不符，未替換模型')
    else:
        key = voyage_key(settings.project_root)
    client = voyageai.Client(api_key=key, timeout=settings.voyage_timeout,
                             max_retries=settings.voyage_max_retries)
    return VoyageProvider(client=client, model_name=settings.voyage_model,
                          max_tokens=settings.voyage_context_tokens, batch_tokens=settings.voyage_batch_tokens)
