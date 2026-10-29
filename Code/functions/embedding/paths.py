"""舊平面批次及已確認的同批兩模式目錄；不接受任意深度路徑。"""
from pathlib import Path
import re
from Code.config.embedding import BATCH_PATTERN

MODES = ('original', 'parent_child')


def batch_location(path, root):
    root = Path(root).resolve()
    original = Path(path)
    path = original.resolve()
    if original.is_symlink() or not path.is_relative_to(root) or not path.is_dir():
        raise ValueError('來源不是指定輸出目錄內的有效批次')
    relative = path.relative_to(root)
    parts = relative.parts
    if (len(parts) not in (1,2) or not re.fullmatch(BATCH_PATTERN, parts[0])
            or (len(parts) == 2 and parts[1] not in MODES)):
        raise ValueError('請選Financial批次或其original／parent_child模式目錄')
    return parts[0], parts[1] if len(parts) == 2 else None, relative


def source_files(batch, pattern):
    files = list(batch.glob(pattern))
    if batch.name not in MODES:
        for mode in MODES:
            folder = batch / mode
            if folder.is_dir() and not folder.is_symlink():
                files.extend(folder.glob(pattern))
    if any(p.is_symlink() or p.resolve().parent != p.parent.resolve() for p in files):
        raise ValueError('來源連結超出所選模式目錄')
    return sorted(files)


def locations(root):
    root = Path(root)
    if not root.is_dir():
        return []
    result = []
    for batch in root.iterdir():
        if (not batch.is_dir() or batch.is_symlink() or batch.resolve().parent != root.resolve()
                or not re.fullmatch(BATCH_PATTERN, batch.name)):
            continue
        result.append(batch)
        result.extend(batch / mode for mode in MODES if (batch / mode).is_dir() and not (batch / mode).is_symlink())
    return sorted(result)


def outer_batch(source):
    return source.parent.parent.name if source.parent.name in MODES else source.parent.name
