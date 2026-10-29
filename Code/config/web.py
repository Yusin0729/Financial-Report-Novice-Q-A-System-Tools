"""本機介面設定；只綁定 loopback，不對外提供服務。"""
HOST = '127.0.0.1'
PORT = 0  # 由作業系統分配可用埠，避免占用其他工具。
MAX_REQUEST_BYTES = 65536
POLL_INTERVAL_MS = 1500
DEFAULT_OCR_ENABLED = True  # 網頁初始勾選；不改CLI既有預設。
CHUNK_SLIDER_MAXIMA = {'parent_limit': 3000, 'recursive_threshold': 1500, 'child_target': 1000}
