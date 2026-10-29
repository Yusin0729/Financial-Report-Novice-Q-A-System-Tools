"""純數值行分類供標題排除及疑似表格偵測共用；不改寫原文。"""
import re
import unicodedata

from config.suspected_tables import NUMBER_PATTERN


def is_numeric_line(value):
    value = unicodedata.normalize('NFKC', value)
    value = re.sub(r'\s+', '', value)
    value = re.sub(r'\\([()$,%+.\-])', r'\1', value)
    if value.startswith('(') and value.endswith(')'):
        value = value[1:-1]
    return re.fullmatch(NUMBER_PATTERN, value) is not None
