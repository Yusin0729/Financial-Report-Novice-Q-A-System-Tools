"""首下載阻塞時的公開權重分段下載工具，完成後核對官方SHA才使用。

不讀財報、不使用金鑰、不刪既有快取；下載未完成不能冒充完整模型。
"""
import hashlib
import json
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def download(settings):
    model, revision = settings.bge_model, settings.bge_revision
    metadata = get_json(f'https://huggingface.co/api/models/{model}/revision/{revision}?blobs=true',
                        settings.hf_http_timeout)
    info = next(f for f in metadata['siblings'] if f['rfilename'] == 'pytorch_model.bin')
    size, expected = info['size'], info['lfs']['sha256']
    root = settings.model_cache / ('models--' + model.replace('/', '--')) / 'snapshots' / revision
    target = root / 'pytorch_model.bin'
    root.mkdir(parents=True, exist_ok=True)
    part = root / 'pytorch_model.bin.http.part'
    if target.exists():
        if digest(target) != expected:
            raise ValueError('既有權重SHA不符，未覆寫；請先確認快取處理方式')
        print('既有權重SHA正確，不重新下載。', flush=True)
    else:
        start = part.stat().st_size if part.exists() else 0
        if start > size:
            raise ValueError('暫存檔超過預期大小，未覆寫')
        def fetch(start):
            end = min(start + settings.hf_http_chunk_bytes, size) - 1
            url = (f'https://huggingface.co/{model}/resolve/{revision}/pytorch_model.bin'
                   f'?download=true&range_start={start}')
            request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
            with urllib.request.urlopen(request, timeout=settings.hf_http_timeout) as response:
                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                    raise ValueError('伺服器未回傳正確分段範圍，未寫入該段')
                block = response.read(end - start + 2)
            if len(block) != end - start + 1:
                raise ValueError('下載片段長度不符，未寫入該段')
            return end + 1, block
        # 每輪最多4段留在記憶體，按原順序寫入；中止後暫存仍為連續前綴。
        with part.open('ab') as output, ThreadPoolExecutor(max_workers=settings.hf_http_workers) as workers:
            while start < size:
                stops = range(start, min(start + settings.hf_http_workers * settings.hf_http_chunk_bytes, size),
                              settings.hf_http_chunk_bytes)
                for next_start, block in workers.map(fetch, stops):
                    output.write(block)
                    output.flush()
                    start = next_start
                    print(f'公開權重下載：{start}/{size} bytes', flush=True)
        if digest(part) != expected:
            raise ValueError('權重SHA不符，未標為可用；暫存保留供檢查')
        if target.exists():
            raise FileExistsError('其他程序已建立權重，未覆寫')
        part.rename(target)
        print('公開權重SHA核對通過。', flush=True)
    # Tokenizer／模組設定由provider下載；補足鎖定版本的標準Pooling設定。
    for name in ('modules.json', 'sentence_bert_config.json', 'config_sentence_transformers.json',
                 'config.json', '1_Pooling/config.json'):
        path = root / name
        if not path.exists():
            config = get_json(f'https://huggingface.co/{model}/resolve/{revision}/{name}', settings.hf_http_timeout)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as stream:
                json.dump(config, stream)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


