"""EXPERIMENT_ONLY：Excel測試設定；正式環境停用enabled，不影響一般問答。"""
from dataclasses import dataclass

@dataclass(frozen=True)
class EvaluationSettings:
    enabled: bool = True
    max_upload_bytes: int = 5 * 1024 * 1024
    max_uncompressed_bytes: int = 32 * 1024 * 1024
    max_rows: int = 1000
    top_k: int = 20
    total_score: float = 10.0
    excluded_ids: tuple = ('26','88','95','102','113')
