"""取得明確確認的文件範圍，不自動將第一個一、或全文末尾當附註。"""
from config.markdown_scopes import CONFIRMED_NOTES_SCOPES
from schemas import NotesScope
from .tag_markdown import restore_tagged_markdown,text_hash


def confirmed_notes_scope(text: str) -> NotesScope | None:
    digest=text_hash(restore_tagged_markdown(text))
    entry=CONFIRMED_NOTES_SCOPES.get(digest)
    return NotesScope(entry[0],entry[1],digest,entry[2]) if entry else None
