"""Gemini官方generateContent HTTP介面；只接收已抽出的PDF，僅503有限重試。"""
import base64
import json
import os
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from config.toc import TOC_PROMPT
from schemas import TOC_MAIN_RESPONSE_SCHEMA


def require_api_key(config, *, env_path=None):
    # 保留既有環境變數相容性；有非空環境值時不讀檔。
    key = os.environ.get(config.api_key_env, '').strip()
    if key:
        return key
    path = Path(env_path) if env_path is not None else Path(__file__).resolve().parents[3] / '.env'
    if path.is_file():
        from dotenv import dotenv_values
        try:
            # 不搜尋其他.env、不展開環境變數、不將整份檔案載入os.environ。
            values = dotenv_values(path, encoding='utf-8-sig', interpolate=False)
        except (OSError, UnicodeError):
            raise ValueError('無法讀取專案.env，請確認檔案可讀並使用UTF-8；未傳送文件') from None
        key = (values.get(config.api_key_env) or '').strip()
    if not key:
        raise ValueError(f'尚未設定{config.api_key_env}；請在專案根目錄.env填入金鑰並儲存，未傳送任何文件')
    return key


class _NoRedirect(HTTPRedirectHandler):
    # 避免含金鑰的請求被HTTP重新導向至其他站點。
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def generate_toc(pdf, config, *, env_path=None, attempt_log=None) -> dict:
    key = require_api_key(config, env_path=env_path)
    if type(config.retries) is not int or not 0 <= config.retries <= len(config.retry_delays_seconds):
        raise ValueError('重試上限須介於0與已設定的等待次數之間')
    endpoint = config.endpoint + config.model + ':generateContent'
    if endpoint != 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent':
        raise ValueError('模型或外傳端點未經確認')
    payload = {
        'contents': [{'role': 'user', 'parts': [
            {'inlineData': {'mimeType': 'application/pdf', 'data': base64.b64encode(pdf.data).decode('ascii')}},
            {'text': TOC_PROMPT}]}],
        'generationConfig': {'maxOutputTokens': config.max_output_tokens,
                             'responseMimeType': 'application/json',
                             'responseJsonSchema': TOC_MAIN_RESPONSE_SCHEMA},
    }
    request = Request(endpoint, data=json.dumps(payload).encode('utf-8'), method='POST',
                      headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    attempts = attempt_log if attempt_log is not None else []
    opener = build_opener(_NoRedirect())
    for index in range(config.retries + 1):
        attempt = {'attempt': index + 1, 'status': 'started'}
        attempts.append(attempt)
        try:
            with opener.open(request, timeout=config.timeout_seconds) as response:
                result = json.loads(response.read().decode('utf-8'))
            if not isinstance(result, dict):
                raise ValueError('Gemini回傳不是JSON物件')
        except HTTPError as error:
            # 僅記狀態碼，不讀取可能包含請求內容或憑證的錯誤body。
            code = error.code
            error.close()
            attempt.update(status='http_error', http_status=code)
            if code not in config.retry_http_statuses or index >= config.retries:
                raise RuntimeError(f'Gemini HTTP {code}；共嘗試{index + 1}次，已停止') from None
            delay = config.retry_delays_seconds[index]
            attempt.update(retry_delay_seconds=delay, wait_status='waiting')
            print(f'Gemini HTTP {code}；{delay}秒後進行第{index + 1}/{config.retries}次重試。', flush=True)
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                attempt['wait_status'] = 'interrupted'
                raise
            attempt['wait_status'] = 'completed'
            continue
        except (TimeoutError, socket.timeout):
            attempt['status'] = 'timeout'
            raise RuntimeError('Gemini網路逾時；未自動重試，服務端可能已處理此次請求') from None
        except URLError:
            attempt['status'] = 'connection_error'
            raise RuntimeError('Gemini連線失敗；未自動重試') from None
        except (ValueError, UnicodeError):
            attempt['status'] = 'invalid_response'
            raise
        except KeyboardInterrupt:
            attempt['status'] = 'interrupted'
            raise
        attempt['status'] = 'response_received'
        return result
