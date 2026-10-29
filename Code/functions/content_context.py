"""第四階段content首行；來源欄位仍保存原有標籤及位置，不重新判定年度。"""
import re
import unicodedata


SCHEMA = 'financial-chunks/4.1'
RULE = 'hierarchical-semantic-chunks/4.2-context'

# 顯示用年度片段：不匹配裸數字、金額、百分比或「耐用年限10年」等期間。
_DIGITS = '0-9〇零○一二三四五六七八九十百'
_TOKEN = rf'(?:[0-9]{{2,4}}|[〇零○一二三四五六七八九十百]{{2,7}})'
_ITEM = rf'(?:(?:中華民國|民國|西元))?{_TOKEN}'
_YEAR_FRAGMENT = re.compile(
    rf'(?<![{_DIGITS}])(?:{_ITEM}(?:年度?)?[、及與和～~至/\-])*{_ITEM}年度'
    rf'|(?<![{_DIGITS}])(?:{_ITEM}(?:年度?)?[、及與和～~至/\-])+{_ITEM}年'
    rf'|(?<![{_DIGITS}])(?:中華民國|民國|西元){_TOKEN}年(?!度)'
    rf'|(?<![{_DIGITS}]){_ITEM}年(?=[0-9]{{1,2}}月[0-9]{{1,2}}日)'
    rf'|(?<![{_DIGITS}]){_ITEM}[./](?=[0-9]{{1,2}}[./][0-9]{{1,2}}(?![0-9]))'
)


def description_without_years(text):
    """移除說明的明列年度；只改生成首行，不改來源說明、正文或years。

    只在比對時忽略空白及全半形差異，再映回原字元，保留金額等其他字樣。
    日期只移除年份部分，保留月日資訊。
    """
    compact, positions = [], []
    for index, char in enumerate(text):
        for normalized in unicodedata.normalize('NFKC', char):
            if not normalized.isspace():
                compact.append(normalized)
                positions.append(index)
    intervals = [(positions[m.start()], positions[m.end()-1]+1)
                 for m in _YEAR_FRAGMENT.finditer(''.join(compact))]
    parts, cursor = [], 0
    for start, end in intervals:
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    value = ''.join(parts).strip()
    return '' if re.fullmatch(r'[\s、，,；;：:]*', value) else value


def context_prefix(chunk, *, remove_years=True, include_identity=False, mode='full'):
    if mode not in ('body', 'description', 'full'):
        raise ValueError('embedding脈絡模式無效')
    if mode == 'body':
        return ''
    identity = re.fullmatch(r'\d{4}Q[1-4]_(\d+)_Financial_Report', chunk['doc_id'])
    if identity is None:
        raise ValueError('缺少可靠股票代號，不能生成content首行')
    fields = []
    # 舊首行只供既有產物驗證；新產物不把這三項寫入content。
    if include_identity:
        fields.extend([('年度', '、'.join(map(str, chunk['years']))),
                       ('股票代號', identity[1]), ('Main_Section', chunk['main_section'])])
    if mode == 'full':
        fields.extend([('Sub_Section', chunk['sub_section']),
                       ('Note_Title', '；'.join(chunk['note_title']))])
    # 表格只採既有回查選出的說明；directions是來源紀錄，不再另印一遍。
    descriptions = ([chunk.get('table_context', '')] if chunk['content_type'] == 'table'
                    else [r['text'] for r in chunk.get('directions', [])])
    seen = set()
    values = []
    for value in descriptions:
        if remove_years:
            value = description_without_years(value)
        key = re.sub(r'\s+', '', value)
        if key and key not in seen:
            values.append(' '.join(value.splitlines()))
            seen.add(key)
    fields.append(('說明', '；'.join(values)))
    line = '｜'.join(f'{name}：{" ".join(value.splitlines())}'
                    for name, value in fields if value)
    return line + '\n' if line else ''


def content_body(chunk):
    """只移除有明確欄位且通過重算驗證的生成首行；舊版正文逐字返回。"""
    prefix = chunk.get('content_prefix')
    if prefix is None:
        return chunk['content']
    mode = chunk.get('embedding_context_mode')
    allowed = ((context_prefix(chunk, mode=mode),) if mode is not None else
               tuple(context_prefix(chunk, remove_years=remove, include_identity=identity)
                     for remove in (True, False) for identity in (False, True)))
    if (not isinstance(prefix, str) or prefix not in allowed
            or not chunk['content'].startswith(prefix)):
        raise ValueError('content首行與來源欄位不符')
    return chunk['content'][len(prefix):]


def validate_context_modes(doc):
    modes = doc.get('embedding_context_modes')
    if 'embedding_context_modes' in doc and (not isinstance(modes, dict) or
            set(modes) != {'text','table'} or any(v not in ('body','description','full') for v in modes.values())):
        raise ValueError('文字／表格embedding脈絡設定無效')
    for chunk in doc.get('chunks', []) + doc.get('parents', []):
        if modes is None:
            if 'embedding_context_mode' in chunk:
                raise ValueError('chunk脈絡模式缺少文件設定')
        elif chunk.get('embedding_context_mode') != modes['table' if chunk.get('content_type')=='table' else 'text']:
            raise ValueError('chunk脈絡模式與文件設定不符')


def add_context(chunk, mode=None):
    if 'content_prefix' in chunk:
        raise ValueError('chunk已有content首行，拒絕重複加入')
    if mode is not None:
        chunk['embedding_context_mode'] = mode
    chunk['content_prefix'] = context_prefix(chunk, mode=mode or 'full')
    chunk['content'] = chunk['content_prefix'] + chunk['content']
