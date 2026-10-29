"""舊啟動入口相容：統一開啟Code_2網站，核心與既有CLI保留。"""
import os
import subprocess
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent.parent
    python=root/'Code/.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    return subprocess.call([str(python),'-X','utf8',str(root/'Code_2/gui.py'),'--open-browser'],cwd=root)


if __name__=='__main__':
    raise SystemExit(main())
