"""使用者確認的chunk規則；只處理本機tagged，不呼叫模型。"""
from dataclasses import dataclass

CHUNK_SCHEMA_VERSION = 'financial-chunks/3.1'
CHUNK_RULE_VERSION = 'heading-content-chunks/3.3'
CHUNK_MARKDOWN_VERSION = 'chunk-markdown/3.1'
MIN_TAGGING_VERSION = (2, 4)
SEMANTIC_SCHEMA_VERSION = 'financial-chunks/5.0'
SEMANTIC_RULE_VERSION = 'content-end-original/1.4'
SEMANTIC_MARKDOWN_VERSION = 'chunk-markdown/5.0'


@dataclass(frozen=True)
class ChunkSettings:
    target_characters: int = 1000
    grace_page_offset: int = 2  # P35達上限，P37起遇第一個中文句號才強制切。
    sentence_end: str = '。'
    document_period: str = 'Q4'  # 使用者指定doc_id格式；不從正文猜季度。
    mode: str = 'original'
    parent_limit: int = 1500
    child_target: int = 300
    recursive_threshold: int = 700
    text_embedding_mode: str = 'full'
    table_embedding_mode: str = 'full'
