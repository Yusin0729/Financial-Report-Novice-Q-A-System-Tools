"""EXPERIMENT_ONLY：取消時追蹤本次新檔；CLI無observer時仍採exclusive建立。"""
import os
from contextlib import contextmanager
from contextvars import ContextVar

_prepare = ContextVar('financial_output_prepare', default=None)


@contextmanager
def output_observer(callback):
    token = _prepare.set(callback)
    try:
        yield
    finally:
        _prepare.reset(token)


@contextmanager
def exclusive_output(path, mode='xb', **kwargs):
    observer = _prepare.get()
    if observer is None:
        with path.open(mode, **kwargs) as stream:
            yield stream
        return
    # 本機服務先以xb建立並登記擁有權，worker收到確認後才寫入。
    identity = observer(path)
    with path.open('r+b' if 'b' in mode else 'r+', **kwargs) as stream:
        stat = os.fstat(stream.fileno())
        if [stat.st_dev, stat.st_ino] != identity:
            raise ValueError('實驗輸出擁有權改變，未寫入')
        yield stream
