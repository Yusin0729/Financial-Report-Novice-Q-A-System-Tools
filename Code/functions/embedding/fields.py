"""明確讀取JSON欄位配置，不沿用舊loader的猜欄位或全轉字串。"""
import configparser
import hashlib
import json
import math
from dataclasses import dataclass
from Code.functions.embedding.prepare import title_context
from Code.functions.embedding.table_text import convert_content


@dataclass(frozen=True)
class FieldRules:
    entries: tuple
    sha256: str

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.entries, ensure_ascii=False).encode('utf-8')).hexdigest()


def load_rules(path):
    raw = path.read_bytes()
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=('#',))
    parser.optionxform = str
    parser.read_string(raw.decode('utf-8-sig'))
    if parser.sections() != ['FIELDS'] or parser.defaults():
        raise ValueError('欄位設定僅接受[FIELDS]區塊，不使用隱藏預設')
    entries = tuple((key, value.strip()) for key, value in parser['FIELDS'].items())
    if not entries or any(role not in ('embedding', 'metadata', 'both', 'ignore') for _, role in entries):
        raise ValueError('欄位模式須為embedding／metadata／both／ignore')
    if not any(role in ('embedding', 'both') for _, role in entries):
        raise ValueError('至少需指定一個embedding欄位')
    # 固定設定檔保留檔案雜湊，供建庫期間偵測檔案被修改。
    return FieldRules(entries, hashlib.sha256(raw).hexdigest())


def value_at(item, path):
    value = item
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f'JSON欄位不存在：{path}')
        value = value[key]
    return value


def as_embedding(value, path):
    if value is None:
        return ''
    if path == 'original_chunk.content':
        return convert_content(value)[0]
    if path == 'original_chunk.title':
        return title_context(value)
    if isinstance(value, str):
        return value.strip()
    if type(value) in (int, float, bool):
        if type(value) is float and not math.isfinite(value):
            raise ValueError(f'非有限數值：{path}')
        return str(value)
    if isinstance(value, list) and all(type(v) in (str, int, float, bool) for v in value):
        return ', '.join(as_embedding(v, path) for v in value)
    raise ValueError(f'{path}是複雜結構；請選文字子欄位，不把整份JSON當正文')


def chroma_value(value, path):
    if type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, list):
        if not value:
            return None  # Chroma不接受空陣列；原型別仍留在payload。
        if len({type(v) for v in value}) == 1 and all(type(v) in (str, int, float, bool) for v in value):
            if any(type(v) is float and not math.isfinite(v) for v in value):
                raise ValueError(f'非有限數值：{path}')
            return list(value)
    if value is None:
        return None
    raise ValueError(f'{path}不能直接當Chroma標籤；請選純量／同型別清單子欄位')


def select_fields(item, rules):
    parts, selected, chroma, omitted = [], {}, {}, []
    for path, role in rules.entries:
        value = value_at(item, path)  # ignore也核對拼字，避免無效設定藏在檔案。
        if role in ('embedding', 'both'):
            text = as_embedding(value, path)
            if text:
                parts.append(text if path == 'embedding_text' else f'{path.split(".")[-1]}: {text}')
        if role in ('metadata', 'both'):
            key = path.split('.')[-1]
            if key.startswith('_sys_') or key in selected:
                raise ValueError(f'標籤名稱重複或使用保留前綴：{key}')
            selected[key] = value
            encoded = chroma_value(value, path)
            if encoded is None:
                omitted.append(path)
            else:
                chroma[key] = encoded
    text = '\n\n'.join(parts).strip()
    if not text:
        raise ValueError(f'{item["chunk_id"]}沒有可向量化文字')
    return {'chunk_id': item['chunk_id'], 'text': text, 'metadata': selected,
            'chroma_metadata': chroma, 'omitted_filter_fields': omitted,
            'original_chunk': item['original_chunk']}
