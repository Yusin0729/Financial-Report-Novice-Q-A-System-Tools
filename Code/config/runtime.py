"""Code前四階段專用環境；第五階段與Code_2沿用Code/.venv。"""
import os
import sys
from pathlib import Path

PDF_ENVIRONMENT_NAME = '.venv_pdf'


def use_current_python():
    value = os.environ.get('FINANCIAL_RAG_RUNTIME_PYTHON', '')
    if value not in ('', 'current'):
        raise ValueError('FINANCIAL_RAG_RUNTIME_PYTHON 僅接受 current 或未設定')
    return value == 'current'


def worker_python(code_dir, *, pdf=False):
    if use_current_python():
        return Path(sys.executable)
    return Path(code_dir) / (PDF_ENVIRONMENT_NAME if pdf else '.venv') / (
        'Scripts/python.exe' if os.name == 'nt' else 'bin/python')

# 核心工作控制，不屬於實驗Output；每批結束清理本批控制檔。
VECTOR_JOB_DIRECTORY = '.runtime/vector_jobs'
