"""本機網頁設定；僅loopback，不發布或新增依賴。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class WebSettings:
    host: str = '127.0.0.1'
    port: int = 8765
    max_request_bytes: int = 65536
    history_limit: int = 100
    max_job_events: int = 200
    max_report_bytes: int = 32 * 1024 * 1024
    poll_milliseconds: int = 1000
