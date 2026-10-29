"""已確認的 CPU ch_lite 模型與參數；不含文件資料。"""
from dataclasses import asdict, dataclass

MODEL_REPO = 'opendatalab/PDF-Extract-Kit-1.0'
MODEL_REVISION = 'ed6b654c018d742e65a17671e379c5e6ecc87ec9'
MODEL_PREFIX = 'models/OCR/paddleocr_torch/'
MODEL_HASHES = {
    'ch_PP-OCRv5_det_infer.pth': 'df848ed5060bac4d0f6e58572aea97d92e909a8a87cf292849237b0e84f6ffdb',
    'ch_PP-OCRv5_rec_infer.pth': 'd20ee8dac2ca63e2d1989b02ecc42595c71d61bf8dd8c8ddc5ad2ee68e7b5be2',
}


@dataclass(frozen=True)
class OcrSettings:
    profile: str = 'ch_lite'
    scale: float = 3.0
    rec_batch_num: int = 1
    drop_score: float = 0.5
    enable_merge_det_boxes: bool = False
    det_db_thresh: float = 0.3
    det_db_box_thresh: float = 0.3
    det_db_unclip_ratio: float = 1.8
    use_dilation: bool = True
    det_limit_side_len: int = 960
    det_limit_type: str = 'max'

    def manifest(self):
        return {**asdict(self), 'device': 'auto', 'repo': MODEL_REPO,
                'revision': MODEL_REVISION, 'sha256': dict(MODEL_HASHES),
                'orientation_classifier': False, 'formula': False}
