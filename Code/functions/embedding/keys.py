"""只解析指定專案.env中的VOYAGE_API_KEY，不載入其他欄位或展開變數。"""
import os
import re
from io import StringIO


def voyage_key(project_root):
    return service_key(project_root, 'VOYAGE_API_KEY')


def service_key(project_root, name):
    if name not in ('VOYAGE_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY') and not re.fullmatch(r'FINRAG_KEY_[a-f0-9]{32}', name):
        raise ValueError('不支援的金鑰名稱')
    key = os.environ.get(name, '').strip()
    if key:
        return key
    path = project_root / '.env'
    selected = []
    if path.is_file():
        with path.open(encoding='utf-8-sig') as stream:
            for line in stream:
                if re.match(r'^\s*(?:export\s+)?' + re.escape(name) + r'\s*=', line):
                    selected.append(line)
    if len(selected) > 1:
        raise ValueError(f'{name}重複設定，請保留一個值')
    from dotenv import dotenv_values
    key = (dotenv_values(stream=StringIO(''.join(selected)), interpolate=False).get(name) or '').strip()
    if not key:
        raise ValueError(f'缺少{name}；請在專案根目錄.env或環境變數設定')
    return key
