"""已確認命名約定的解析與輸出檔名；公司、季度與期間不推定。"""
import re
from pathlib import Path
from config.markdown_files import FILENAME_PREFIX_PATTERN, PDF_STEM_PATTERN

_PREFIX = re.compile(FILENAME_PREFIX_PATTERN)
_PDF_STEM = re.compile(PDF_STEM_PATTERN)


def filename_identity(name: str) -> tuple[str, str] | None:
    match = _PREFIX.match(Path(name).name)
    return (match['year'],match['stock']) if match else None


def source_identity(source: Path) -> tuple[str, str] | None:
    """僅命名時向上找舊財報目錄；標籤metadata只讀檔名本身。"""
    for name in (source.name,*(parent.name for parent in source.parents)):
        identity=filename_identity(name)
        if identity:
            return identity
        match=_PDF_STEM.fullmatch(Path(name).stem)
        if match:
            return match['year'],match['stock']
    return None


def markdown_filename(source: Path, role: str, fallback: str = 'document.md') -> str:
    identity=source_identity(source)
    return f'{identity[0]}_{identity[1]}_{role}.md' if identity else fallback
