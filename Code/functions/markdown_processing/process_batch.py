"""第二階段固定入口：目錄選頁已在第一階段完成，不呼叫 Gemini。"""
from functions.markdown_processing.process_batch_local import list_raw_batches, process_raw_batch

__all__ = ['list_raw_batches', 'process_raw_batch']
