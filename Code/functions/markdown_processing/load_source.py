"""來源 Markdown 載入與追溯；不改寫來源，維持 UTF-8／BOM／換行。"""
import hashlib
from pathlib import Path


def is_selectable_markdown(source: Path) -> bool:
    """保留舊入口，只將含實體頁序的新 raw 列為可選，避免舊無頁序 raw 混入。"""
    from config.markdown_files import MARKDOWN_ROLE_SUFFIXES
    if not source.is_file():
        return False
    if source.name == 'document.md' or source.name.endswith(MARKDOWN_ROLE_SUFFIXES):
        return True
    if source.name.endswith('_raw.md'):
        from functions.markdown_processing.page_markers import parse_page_marker
        with source.open(encoding='utf-8-sig') as stream:
            first = stream.read(4096).lstrip().splitlines()
            for line in first:
                if not line.strip() or line.strip() in ('<會計師查核報告>', '<note>', '<合併財務報告附註>'):
                    continue
                return parse_page_marker(line) is not None
            return False
    return False


def load_source(path: Path):
    source = path.resolve()
    if source.is_dir():
        candidates=[p for p in source.iterdir() if is_selectable_markdown(p)]
        if len(candidates)!=1:
            raise ValueError('資料夾沒有唯一的頁序版／processed／tagged Markdown，請明確指定檔案')
        source=candidates[0]
    if source.suffix.lower() != '.md' or not source.is_file():
        raise ValueError('請指定既有 .md 檔，或包含唯一處理結果的資料夾')
    data = source.read_bytes()
    # 嚴格 UTF-8，編碼錯誤不取代字元，以免改寫財務內容。
    return source, data.decode('utf-8'), hashlib.sha256(data).hexdigest()
