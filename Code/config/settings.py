"""
程式主要目的與功能：
本程式定義專案的全域設定與路徑配置（Settings 類別），集中管理：
1. 專案根目錄、財報來源目錄、實驗輸出目錄（markdown_raw）與 Docling 快取目錄。
2. 本機 PDF 轉換參數：CPU 執行緒數、批次大小、Markdown 管線表格、預設關閉的 OCR 開關與繁中／英文語言。
3. 實驗輸出開關（export_enabled）。

使用之外部套件與用途：
- 本模組僅使用 Python 內建標準庫（dataclasses 用於定義唯讀設定結構，pathlib 用於物件導向路徑操作），未依賴第三方外部套件。
"""

from dataclasses import dataclass, field
from pathlib import Path
from .devices import default_device
from .runtime import VECTOR_JOB_DIRECTORY
from config.ocr import OcrSettings
from config.toc import TocSettings
from config.chunking import ChunkSettings


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parents[2]
    export_enabled: bool = True  # EXPERIMENT_ONLY：只控制檢查產物的寫檔。
    ocr_enabled: bool = False
    ocr: OcrSettings = OcrSettings()
    toc: TocSettings = TocSettings()
    chunking: ChunkSettings = ChunkSettings()
    pdf_cpu_threads: int = 8
    pdf_batch_size: int = 1
    pdf_parser: str = 'docling'
    table_format: str = "html"
    table_mode: str = 'accurate'
    compute_device: str = field(default_factory=default_device)

    @property
    def vector_job_dir(self):
        return self.project_root / VECTOR_JOB_DIRECTORY

    @property
    def source_dir(self) -> Path:
        return self.project_root / "Financial Statements"

    @property
    def env_file(self) -> Path:
        """本機專案金鑰檔；內容不得寫入manifest或日誌。"""
        return self.project_root / '.env'

    @property
    def toc_output_dir(self) -> Path:
        """EXPERIMENT_ONLY：目錄JSON與兩頁PDF檢查產物。"""
        return self.project_root / 'Output' / 'json'

    @property
    def markdown_output_dir(self) -> Path:
        """EXPERIMENT_ONLY：PDF 初始轉換產物，尚未做後續處理或加標籤。"""
        return self.project_root / "Output" / "markdown_raw"

    @property
    def markdown_processed_output_dir(self) -> Path:
        """EXPERIMENT_ONLY：既有 Markdown 的補標記等已確認處理產物。"""
        return self.project_root / "Output" / "markdown_processed"

    @property
    def markdown_tagged_output_dir(self) -> Path:
        """EXPERIMENT_ONLY：自訂hd階層標籤與原文包裝結果。"""
        return self.project_root / "Output" / "markdown_tagged"

    @property
    def markdown_chunk_output_dir(self) -> Path:
        """EXPERIMENT_ONLY：同批chunk Markdown、JSON與Record。"""
        return self.project_root / 'Output' / 'markdown_chunk'

    @property
    def docling_cache_dir(self) -> Path:
        return self.project_root / "Code" / ".cache" / "docling"

    @property
    def ocr_cache_dir(self) -> Path:
        return self.project_root / "Code" / ".cache" / "mineru_ocr"

    def pdf_manifest(self) -> dict:
        return {
            "engine": self.pdf_parser, "pipeline": "standard", "device": self.compute_device,
            "pdf_backend": "pdf-inspector" if self.pdf_parser == 'inspector' else "pypdfium2",
            "ocr_enabled": self.ocr_enabled, "ocr_scale": self.ocr.scale,
            "ocr_engine": "mineru_paddle_torch" if self.ocr_enabled else None,
            "ocr_profile": self.ocr.manifest() if self.ocr_enabled else None,
            "force_full_page_ocr": False, "table_format": "markdown" if self.pdf_parser == 'inspector' else self.table_format,
            "fallback_table_format": self.table_format if self.pdf_parser == 'inspector' else None, "table_mode": self.table_mode,
            "cpu_threads": self.pdf_cpu_threads if self.pdf_parser == 'docling' else None,
            "fallback_cpu_threads": self.pdf_cpu_threads if self.pdf_parser == 'inspector' else None,
            "batch_size": self.pdf_batch_size if self.pdf_parser == 'docling' else None,
            "remote_services": False, "export_enabled": self.export_enabled,
        }



SETTINGS = Settings()
