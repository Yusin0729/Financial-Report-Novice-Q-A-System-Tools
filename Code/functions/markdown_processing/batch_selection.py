"""既有Financial批次的檔案子集；CLI預設仍處理第一層全部來源。"""
from pathlib import Path
from functions.markdown_processing.file_identity import filename_identity


def available_sources(batch, pattern, *, recursive=False):
    batch = batch.resolve()
    paths = batch.rglob(pattern) if recursive else batch.glob(pattern)
    result = []
    for path in paths:
        relative = path.relative_to(batch)
        if (not path.is_file() or not path.resolve().is_relative_to(batch) or
                any(part.lower() == 'record' for part in relative.parts[:-1]) or
                any((batch.joinpath(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts)+1))):
            continue
        result.append(path)
    return sorted(result)


def batch_sources(batch, pattern, source_files=None):
    if source_files is None:
        sources = available_sources(batch, pattern)
    else:
        if (not isinstance(source_files, (list, tuple)) or not source_files or
                any(not isinstance(name, str) for name in source_files) or len(set(source_files)) != len(source_files)):
            raise ValueError('請選取不重複的批次內檔案')
        allowed = {p.relative_to(batch).as_posix(): p for p in available_sources(batch, pattern, recursive=True)}
        if not set(source_files).issubset(allowed):
            raise ValueError('所選檔案不存在、不是本階段來源或超出批次')
        sources = [allowed[name] for name in source_files]
    if not sources:
        raise ValueError(f'批次內沒有可選來源：{pattern}')
    seen = set()
    for path in sources:
        identity = filename_identity(path.name)
        if identity is not None:
            if identity in seen:
                raise ValueError('同批所選檔案的年度與股票代號重複，會使用相同輸出檔名；請分開處理')
            seen.add(identity)
    return sources
