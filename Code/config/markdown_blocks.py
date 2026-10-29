"""使用者確認的區塊標籤；保留指定的非對稱 content 結束寫法。"""
import re

# SUB_TITLE 使用 hd2；動態標題從 hd3 起，完整配對且每行一個。
HD_TAG_LINE = re.compile(r'^<hd(?P<level>[2-9]|[1-9]\d+)>(?P<title>[^\r\n]*)</hd(?P=level)>$')
DESCRIPTION_TAG_LINE = re.compile(
    r'^<(?P<kind>table_year|table_direction|content_direction)>'
    r'(?P<title>[^\r\n]*)</(?P=kind)>$'
)

CONTENT_START = '<content_start>'
CONTENT_END = '</content_end>'
TABLE_START = '<table_start>'
FULL_TABLE_START = '<fulltablestart>'
TABLE_END = '<table_end>'
PAGE_START = '<page_start>'
PAGE_END = '<page_end>'

# 相鄰HTML表格之間出現任一接續詞即共用一組table邊界；比對忽略空白。
TABLE_CONTINUATION_MARKERS = ('接次頁', '承前頁')
