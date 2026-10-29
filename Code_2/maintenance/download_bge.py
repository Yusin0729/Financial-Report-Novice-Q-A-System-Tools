"""手動補齊鎖定BGE快取；一般建庫也會自動呼叫相同的分段下載功能。"""
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Code_2.config.embedding import Settings
from Code_2.functions.embedding.model_download import download

if __name__ == '__main__':
    download(Settings())
