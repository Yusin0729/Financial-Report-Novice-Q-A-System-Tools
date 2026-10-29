"""已確認的階層及自訂標籤格式，不抽取或猜測財報metadata。"""
from config.markdown_headings import CN_NUMERALS
HIERARCHY_VERSION = 'markdown-hierarchy/2.1'
SECTION_LEVEL = 1
FIRST_DYNAMIC_LEVEL = 2
DYNAMIC_MARKER_TYPES = frozenset({
    'parenthesized_chinese', 'number_dot', 'parenthesized_number',
    'english_dot', 'parenthesized_english',
})
MAIN_TITLE = '合併財務報告附註'
SECTION_PATTERN = rf'^[{CN_NUMERALS}](?:[ \t\u3000]*[{CN_NUMERALS}])*[ \t\u3000]*、'
TAGGING_VERSION = 'markdown-tagging/2.0'
RESTORABLE_VERSIONS = frozenset({'markdown-tagging/1.0', TAGGING_VERSION})
TAG_GENERATOR = 'financial-rag-tagging'
CONTENT_TAG = 'content'
TABLE_TAG = 'tableblock'

# TEMPORARY_FALLBACK：Gemini目錄不可用時的暫時規則，後續可集中停用／替換。
TEMPORARY_MAIN_FALLBACK_ENABLED = True
TEMPORARY_MAIN_FALLBACK_TITLE = '合併財務報表附錄'
TEMPORARY_MAIN_FALLBACK_VERSION = 'company-history-page/1.0'
