"""
程式主要目的與功能：
本程式定義 PDF 轉 Markdown 階段的共用記憶體資料模型（Data Schemas）：
1. MarkdownPage: 封裝單頁 PDF 實體頁碼、該頁 Markdown 文字、文字擷取狀態與元素識別碼參照。
2. MarkdownDocument: 封裝全份文件原始 Markdown、帶頁序標記 Markdown、逐頁物件清單、警告訊息及底層 Docling 文件物件。

使用之外部套件與用途：
- 本模組僅使用 Python 內建標準庫（dataclasses 提供不可變資料容器定義與 dict 轉換），未依賴第三方外部套件。
"""

from dataclasses import asdict, dataclass

MARKDOWN_SCHEMA_VERSION = "pdf-markdown/1.0"


@dataclass(frozen=True)
class TocPdf:
    """兩頁目錄 PDF 與原始來源對應；可由本機抽頁或經驗證的既有抽頁載入。"""
    data: bytes
    source_sha256: str
    extracted_sha256: str
    source_page_count: int
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class TocResult:
    toc: dict
    raw_response: dict
    response_text: str
    status: str


# 目錄專用JSON，不是正文／chunk schema。字串空值保留未知，不推算頁碼。
TOC_RESPONSE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['pages', 'entries'],
    'properties': {
        'pages': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['source_pdf_page', 'classification', 'issues'],
            'properties': {
                'source_pdf_page': {'type': 'integer', 'enum': [2, 3]},
                'classification': {'type': 'string', 'enum': ['toc', 'not_toc', 'unreadable']},
                'issues': {'type': 'array', 'items': {'type': 'string'}},
            }}},
        'entries': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['id', 'parent_id', 'title', 'printed_pages', 'note_numbers', 'source_pdf_page'],
            'properties': {
                'id': {'type': 'string'}, 'parent_id': {'type': 'string'},
                'title': {'type': 'string'}, 'printed_pages': {'type': 'string'},
                'note_numbers': {'type': 'string'},
                'source_pdf_page': {'type': 'integer', 'enum': [2, 3]},
            }}},
    },
}

# 新 API 僅輸出大標；通用舊 schema 保留供讀取歷史 parent_id 階層 JSON。
from copy import deepcopy
TOC_MAIN_RESPONSE_SCHEMA = deepcopy(TOC_RESPONSE_SCHEMA)
TOC_MAIN_RESPONSE_SCHEMA['properties']['entries']['items']['properties']['parent_id']['enum'] = ['']
TOC_MAIN_RESPONSE_SCHEMA['properties']['entries']['items']['properties']['note_numbers']['enum'] = ['']


@dataclass(frozen=True)
class MarkdownPage:
    pdf_page: int
    markdown: str
    status: str
    item_refs: tuple[str, ...]
    cross_page_item_refs: tuple[str, ...]

    def metadata(self) -> dict:
        return {key: value for key, value in asdict(self).items() if key != "markdown"}


@dataclass(frozen=True)
class MarkdownDocument:
    """核心記憶體結果；頁序從 1 起算，沒有推測印刷頁碼。"""

    raw_markdown: str
    markdown: str
    pages: tuple[MarkdownPage, ...]
    warnings: tuple[str, ...]
    # 原始結構保留 provenance、表格欄列及 OCR 原文，供下一階段使用；不必寫入 Output。
    docling_document: object


@dataclass(frozen=True)
class HeadingChange:
    line_number: int  # Markdown 行號，絕非 PDF 頁序。
    original: str  # 不含末尾換行；冒號合併時可含原段落內部換行。
    modified: str
    reason: str


@dataclass(frozen=True)
class HeadingMarkResult:
    markdown: str
    changes: tuple[HeadingChange, ...]
    rule_version: str


@dataclass(frozen=True)
class HeadingPathItem:
    """邏輯階層與Markdown井號數量無關；不推定公司、年份或頁序。"""
    level: int
    title: str
    marker_type: str | None


@dataclass(frozen=True)
class TagHeading:
    role: str  # main / section / dynamic / untracked
    title: str
    marker_type: str | None = None


@dataclass(frozen=True)
class TaggingMetadata:
    company_name: str = ''
    stock_code: str = ''
    report_period: str = ''  # 文件所屬期間，絕不以比較年度推定。
    report_year: str = ''  # 從已確認的檔名前綴取得，不代表季別或全年範圍。


@dataclass(frozen=True)
class CommentTagResult:
    markdown: str
    version: str
    removed_page_lines: tuple[dict, ...]
    issues: tuple[dict, ...]
    block_counts: dict[str, int] | None = None
    boundary_added_newlines: int = 0
    table_continuation_joins: tuple[dict, ...] = ()


@dataclass(frozen=True)
class TaggedBlock:
    kind: str
    start_line: int
    end_line: int
    path: tuple[HeadingPathItem, ...]
    pdf_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class TaggingResult:
    markdown: str
    version: str
    blocks: tuple[TaggedBlock, ...]
    issues: tuple[dict, ...]
    printed_page_candidates: tuple[dict, ...]
    original_sha256: str
    notes_scope: 'NotesScope | None' = None


@dataclass(frozen=True)
class NotesScope:
    """明確確認的原Markdown範圍（1起算含起訖）；不是PDF頁碼。"""
    start_line: int
    end_line: int
    source_sha256: str
    evidence: str

