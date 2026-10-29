"""MinerU 2.6.5 PytorchPaddleOCR 最小改寫；僅 CPU det/rec。

原始來源、AGPL-3.0 與 Paddle Apache-2.0 標頭見 mineru_ocr_vendor。
不匯入 MinerU pipeline、全域設定或下載器，不使用外部推論服務。
"""
import hashlib
from pathlib import Path

from config.ocr import MODEL_HASHES, MODEL_PREFIX, MODEL_REPO, MODEL_REVISION, OcrSettings


def model_paths(cache: Path, download: bool = True) -> dict[str, Path]:
    """只下載指定公開權重；固定 revision，驗證 SHA，不使用登入 token。"""
    from huggingface_hub import hf_hub_download
    result = {}
    for name, expected in MODEL_HASHES.items():
        path = Path(hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_PREFIX + name,
                                   revision=MODEL_REVISION, cache_dir=str(cache),
                                   token=False, local_files_only=not download))
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'OCR 模型 SHA-256 不符：{name}；不載入、不退回其他引擎')
        result[name] = path
    return result


class PytorchPaddleOCR:
    """沿用 MinerU 偵測、裁切、辨識；回傳未經 drop_score 篩選的框供診斷。

    修改原 wrapper：CPU 強制、batch 可設定、不合併框、不自動改語言，
    不載入方向／公式模型。門檻由 Docling adapter 統一套用並記錄。
    """
    def __init__(self, cache: Path, config: OcrSettings, threads: int, device: str = 'cpu'):
        if config.profile != 'ch_lite' or config.enable_merge_det_boxes:
            raise ValueError('目前只核准 ch_lite、不合併偵測框')
        import torch
        from .mineru_ocr_vendor.tools.infer import pytorchocr_utility as utility
        from .mineru_ocr_vendor.tools.infer.predict_det import TextDetector
        from .mineru_ocr_vendor.tools.infer.predict_rec import TextRecognizer
        from .mineru_ocr_vendor.tools.infer.predict_system import TextSystem, sorted_boxes
        paths = model_paths(cache)
        torch.set_num_threads(threads)
        args = utility.init_args().parse_args([])
        for key, value in config.__dict__.items():
            setattr(args, key, value)
        if device not in {'cpu', 'cuda'}:
            raise ValueError(f'不支援的 OCR 裝置：{device}')
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('OCR 指定 CUDA，但 PyTorch CUDA 不可用')
        args.device = device
        args.det_model_path = str(paths['ch_PP-OCRv5_det_infer.pth'])
        args.rec_model_path = str(paths['ch_PP-OCRv5_rec_infer.pth'])
        args.rec_char_dict_path = str(Path(__file__).parent / 'mineru_ocr_vendor/pytorchocr/utils/resources/ppocrv5_dict.txt')
        args.use_angle_cls = False
        self.detector = TextDetector(args)
        self.recognizer = TextRecognizer(args)
        self.crop = TextSystem.get_rotate_crop_image
        self.sort = sorted_boxes

    def ocr(self, bgr):
        import numpy as np
        import torch
        with torch.inference_mode():
            boxes, _ = self.detector(bgr)
            if boxes is None or len(boxes) == 0:
                return [[]]
            boxes = self.sort(boxes)
            crops = [self.crop(self, bgr, np.array(box, dtype=np.float32).copy()) for box in boxes]
            results, _ = self.recognizer(crops)
        if len(boxes) != len(results):
            raise ValueError('OCR 偵測框與辨識結果數量不符')
        return [[[np.asarray(box).tolist(), (str(text), float(score))]
                 for box, (text, score) in zip(boxes, results)]]
