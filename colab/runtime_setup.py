"""Colab helpers: preserve the supplied CUDA torch; keep active SQLite local."""
from pathlib import Path
import os
import subprocess
import sys
import importlib.metadata
import re
import zipfile
from datetime import datetime, timezone


def install_dependencies(root):
    root = Path(root)
    # Resolve all project requirements together. Refuse incompatible torch constraints
    # rather than replacing Colab's CUDA distribution with the Windows CPU pin.
    protected = ('torch', 'torchvision', 'torchaudio')
    constraints = []
    for name in protected:
        try:
            constraints.append(name + '==' + importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:
            if name == 'torch':
                raise RuntimeError('請先選擇 Colab GPU 執行階段；找不到預裝 PyTorch')
    requirements = []
    for file in ('Code/requirements.txt', 'Code_2/requirements.txt'):
        for line in (root/file).read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name = re.split(r'[<>=!~;\[ ]', line, maxsplit=1)[0].lower().replace('_','-')
            if name not in protected and line not in requirements:
                requirements.append(line)
    temp = root/'.runtime/colab'
    temp.mkdir(parents=True, exist_ok=True)
    (temp/'constraints.txt').write_text('\n'.join(constraints), encoding='utf-8')
    (temp/'requirements.txt').write_text('\n'.join(requirements), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(temp/'requirements.txt'),
                    '-c', str(temp/'constraints.txt')], check=True)


def configure(device='auto'):
    os.environ['FINANCIAL_RAG_DEVICE'] = device
    os.environ['FINANCIAL_RAG_RUNTIME_PYTHON'] = 'current'
    from Code.config.devices import select_torch_device
    import torch
    selected = select_torch_device(device)
    result = {'requested': device, 'device': selected.actual, 'reason': selected.reason,
              'torch': torch.__version__, 'cuda': torch.version.cuda}
    if selected.actual == 'cuda':
        result['gpu'] = torch.cuda.get_device_name(0)
    return result


def copy_inputs(root, drive_folder):
    """Copy only missing inputs; never overwrite work or use Drive as the live DB."""
    import shutil
    root, drive_folder = Path(root), Path(drive_folder)
    count = 0
    for name in ('Financial Statements', 'Output', 'Data', 'VectorStore'):
        source = drive_folder/name
        if not source.is_dir():
            continue
        target = root/name
        if name in ('Data', 'VectorStore') and target.exists():
            raise ValueError(f'{name} 已存在；不合併題庫或向量資料庫，請先使用新的 Colab 工作目錄')
        for file in source.rglob('*'):
            if not file.is_file() or file.is_symlink():
                continue
            dest = target/file.relative_to(source)
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
                count += 1
    return count


def backup(root, drive_folder):
    """Call only after workers have exited; excludes API profiles and .env."""
    root, drive_folder = Path(root), Path(drive_folder)
    drive_folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    path = drive_folder/f'Financial_RAG_data_{stamp}.zip'
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('Financial Statements', 'Output', 'outputs', 'Data', 'VectorStore'):
            source = root/name
            if source.is_dir():
                for file in source.rglob('*'):
                    if file.is_file() and not file.is_symlink():
                        archive.write(file, file.relative_to(root).as_posix())
    return path
