"""相容入口；建庫核心已移至 Code，問答共用相同契約。"""
import sys
from Code.functions.embedding import load_prepared as _implementation
sys.modules[__name__] = _implementation
