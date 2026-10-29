"""建庫時選擇搜尋脈絡；來源chunk、切點與metadata不變。"""
from Code.functions.content_context import content_body, context_prefix
from Code.functions.embedding.sections import section_fields
from Code.functions.embedding.table_text import convert_content

MODES = ('body', 'description', 'full')


def validate_modes(modes):
    if (not isinstance(modes, dict) or set(modes) != {'text', 'table'}
            or any(value not in MODES for value in modes.values())):
        raise ValueError('文字及表格脈絡須分別指定body／description／full')
    return dict(modes)


def embedding_text(chunk, mode):
    if mode not in MODES:
        raise ValueError('embedding脈絡模式無效')
    body = convert_content(content_body(chunk))[0]
    context = {**chunk, **section_fields(chunk['title'])}
    prefix = context_prefix(context, mode=mode)
    return (prefix + body).strip()
