"""前處理與建庫設定；CPU、批次大小、模型、逾時與路徑集中於此。"""
from dataclasses import dataclass, field
from pathlib import Path
from Code.config.devices import default_device
from Code.config.runtime import VECTOR_JOB_DIRECTORY

PREPARED_SCHEMA = 'financial-embedding-prepared/2.0'
PREPARE_RULE = 'embedding-prepare/2.0'
CHUNK_SCHEMA = 'financial-chunks/2.0'
INDEX_RULE = 'financial-index/2.0'
BATCH_PATTERN = r'Financial_(?:(?:raw|processed|tagged|chunk)_)?\d{8}_(?:(?:[01]\d|2[0-3])-[0-5]\d-[0-5]\d|\d{3,})'


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parents[2]
    export_enabled: bool = True  # EXPERIMENT_ONLY
    default_backend: str = 'bge'  # main可改選bge／voyage／both。
    bge_model: str = 'BAAI/bge-m3'
    bge_revision: str = '5617a9f61b028005a4858fdac845db406aefb181'
    bge_batch_size: int = 1  # 約16GB RAM，CPU每批一筆；不是總文件限制。
    compute_device: str = field(default_factory=default_device)
    cpu_threads: int = 8
    hf_disable_xet: bool = True  # Windows首下載改一般HTTP，避免Xet通道停滯。
    hf_http_chunk_bytes: int = 16 * 1024 * 1024
    hf_http_timeout: float = 60.0
    hf_http_workers: int = 4  # 僅公開模型下載；財報仍逐份處理。
    voyage_model: str = 'voyage-finance-2'
    voyage_context_tokens: int = 32000
    voyage_batch_tokens: int = 120000
    voyage_batch_size: int = 16
    voyage_timeout: float = 120.0
    voyage_max_retries: int = 0  # 不自行重送可能已計費的請求。
    allow_voyage_api: bool = False  # 本次使用者要求不呼叫真實API。
    embedding_profile: str | None = None  # 僅保存設定ID，絕不把金鑰放入工作／輸出。

    @property
    def vector_job_dir(self):
        return self.project_root / VECTOR_JOB_DIRECTORY

    @property
    def input_dir(self):
        return self.project_root / 'Output' / 'markdown_chunk'

    @property
    def output_dir(self):
        return self.project_root / 'Output' / 'embedding_prepared'

    @property
    def fields_file(self):
        return self.project_root / 'Code' / 'config' / 'embedding_fields.txt'

    @property
    def vector_root(self):
        return self.project_root / 'VectorStore' / 'chroma'

    @property
    def response_dir(self):
        return self.project_root / 'Output' / 'Response'

    @property
    def question_bank_path(self):
        return self.project_root / 'Data' / 'question_bank.sqlite'

    @property
    def model_cache(self):
        return self.project_root / 'Code_2' / '.cache' / 'embedding'
