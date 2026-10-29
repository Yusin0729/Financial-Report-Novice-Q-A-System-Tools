"""只列出既有來源目錄內的 PDF／Financial 批次。"""
import re
from config.output_layout import BATCH_NAME_PATTERN
from functions.chunking.filenames import CHUNK_GLOB, parse_chunk_filename
from functions.markdown_processing.batch_selection import available_sources, batch_sources

STAGES = {
    'raw': ('PDF → Markdown', 'source_dir', 'markdown_output_dir', None),
    'processed': ('補標題與清頁碼', 'markdown_output_dir', 'markdown_processed_output_dir', '*_raw.md'),
    'tagged': ('加上階層標籤', 'markdown_processed_output_dir', 'markdown_tagged_output_dir', '*_processed.md'),
    'embed': ('向量建庫', 'markdown_chunk_output_dir', 'markdown_chunk_output_dir', CHUNK_GLOB),
    'chunk': ('切分 chunk', 'markdown_tagged_output_dir', 'markdown_chunk_output_dir', '*_tagged.md'),
}

def catalog(settings, stage):
    if stage not in STAGES:
        raise ValueError('未知階段')
    _, source_attr, _, pattern = STAGES[stage]
    root = getattr(settings, source_attr).resolve()
    if not root.is_dir():
        return []
    paths = root.rglob('*') if stage == 'raw' else root.iterdir()
    result = []
    for path in sorted(paths):
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            continue
        if stage == 'raw':
            relative = path.relative_to(root)
            if (not path.is_file() or path.suffix.lower() != '.pdf' or
                    any(root.joinpath(*relative.parts[:i]).is_symlink() for i in range(1, len(relative.parts)+1))):
                continue
            result.append({'id': relative.as_posix(), 'count': 1})
        else:
            if not path.is_dir() or path.is_symlink() or not re.fullmatch(BATCH_NAME_PATTERN, path.name):
                continue
            for source in available_sources(path, pattern, recursive=True):
                if stage == 'embed' and parse_chunk_filename(source.name) is None:
                    continue
                result.append({'id': source.relative_to(root).as_posix(), 'count': 1})
    return result

def selected_paths(settings, stage, ids):
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids):
        raise ValueError('請勾選資料')
    if len(ids) != len(set(ids)):
        raise ValueError('選取資料重複')
    allowed = {row['id'] for row in catalog(settings, stage)}
    if not set(ids).issubset(allowed):
        raise ValueError('選取資料已不存在或不在來源清單，請重新整理')
    root = getattr(settings, STAGES[stage][1]).resolve()
    if stage not in ('raw', 'embed'):
        groups = {}
        for item in ids:
            batch, relative = item.split('/', 1)
            groups.setdefault(batch, []).append(relative)
        for batch, files in groups.items():
            batch_sources(root / batch, STAGES[stage][3], files)
        from functions.markdown_processing.file_identity import filename_identity
        identities = [filename_identity(item.rsplit('/', 1)[-1]) for item in ids]
        if None in identities or len(set(identities)) != len(identities):
            raise ValueError('所選財報年度與股票代號缺失或重複，會使用相同輸出檔名；請分開處理')
    return [root / item for item in ids]
