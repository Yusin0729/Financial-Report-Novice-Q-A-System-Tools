"""Docling 2.140 自訂 OCR stage：PDF-aware 區域、CPU OCR、原生文字優先。"""
from pathlib import Path
import time
from typing import ClassVar

import numpy as np
from docling.datamodel.pipeline_options import OcrMode, OcrOptions
from docling.models.base_ocr_model import BaseOcrModel
from docling_core.types.doc import CoordOrigin
from docling_core.types.doc.page import BoundingRectangle, TextCell

from config.ocr import OcrSettings


class MineruOcrOptions(OcrOptions):
    kind: ClassVar[str] = 'mineru_paddle_torch'
    canonicalize_lang: ClassVar[bool] = False
    lang: list[str] = ['ch_lite']
    mode: OcrMode = OcrMode.PDF_AWARE_LAYOUT_REGIONS
    cache_dir: str
    parameters: dict
    cpu_threads: int = 2
    device: str = 'cpu'


def result_cells(result, crop, image_size, first_index, threshold):
    """依實際影像尺寸轉回 PDF TOPLEFT 點座標，保留四個角及原文。"""
    if not isinstance(result, list) or len(result) != 1:
        raise ValueError('OCR 回傳格式不是單張圖片的巢狀結果')
    lines = result[0]
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise ValueError('OCR 行結果格式錯誤')
    width, height = image_size
    if width <= 0 or height <= 0 or crop.r <= crop.l or crop.b <= crop.t:
        raise ValueError('OCR 裁切尺寸無效')
    cells, diagnostics = [], []
    for line in lines:
        if not isinstance(line, (list, tuple)) or len(line) != 2 or len(line[1]) != 2:
            raise ValueError('OCR 框／文字／分數格式錯誤')
        box, (text, score) = line
        box = np.asarray(box, dtype=float)
        score = float(score)
        if box.shape != (4, 2) or not np.isfinite(box).all() or not np.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('OCR 座標或信心分數非法')
        if (box < 0).any() or (box[:, 0] > width).any() or (box[:, 1] > height).any():
            raise ValueError('OCR 框超出實際裁切影像')
        if not isinstance(text, str):
            raise ValueError('OCR 文字型別錯誤')
        points = box / [width, height] * [crop.r-crop.l, crop.b-crop.t] + [crop.l, crop.t]
        edge1, edge2 = points[1]-points[0], points[3]-points[0]
        if abs(edge1[0]*edge2[1]-edge1[1]*edge2[0]) <= 0:
            raise ValueError('OCR 框面積為零')
        accepted = bool(text.strip()) and score >= threshold
        diagnostics.append({'text': text, 'confidence': score, 'pixel_quad': box.tolist(),
                            'pdf_quad': points.tolist(), 'accepted': accepted})
        if accepted:
            coords = {f'r_{axis}{i}': float(points[i, j]) for i in range(4) for j, axis in enumerate(('x', 'y'))}
            cells.append(TextCell(index=first_index+len(cells), text=text, orig=text, from_ocr=True,
                                  confidence=score, rect=BoundingRectangle(**coords, coord_origin=CoordOrigin.TOPLEFT)))
    return cells, diagnostics


class MineruOcrModel(BaseOcrModel):
    def __init__(self, *, enabled, artifacts_path, options, accelerator_options):
        super().__init__(enabled=enabled, artifacts_path=artifacts_path,
                         options=options, accelerator_options=accelerator_options)
        if options.mode != OcrMode.PDF_AWARE_LAYOUT_REGIONS or options.lang != ['ch_lite']:
            raise ValueError('本次只核准 PDF-aware 區域 OCR 與 ch_lite')
        self.engine = None
        self.diagnostics = []

    @classmethod
    def get_options_type(cls):
        return MineruOcrOptions

    def __call__(self, conv_res, page_batch):
        if not self.enabled:
            yield from page_batch
            return
        for page in page_batch:
            started = time.perf_counter()
            model_load_seconds = 0.0
            model_load_calls = 0
            diagnostic = {'pdf_page': page.page_no, 'status': 'no_ocr_regions', 'regions': []}
            self.diagnostics.append(diagnostic)
            try:
                if page._backend is None or not page._backend.is_valid():
                    raise ValueError('OCR 頁面 backend 無效')
                rects = [r for r in self.get_ocr_rects(page) if r.area() > 0]
                all_cells = []
                for rect in rects:
                    region = {'crop': rect.model_dump(mode='json'), 'status': 'started'}
                    diagnostic['regions'].append(region)
                    if self.engine is None:
                        load_started = time.perf_counter()
                        model_load_calls += 1
                        try:
                            from .mineru_paddle import PytorchPaddleOCR
                            self.engine = PytorchPaddleOCR(Path(self.options.cache_dir),
                                                          OcrSettings(**self.options.parameters), self.options.cpu_threads,
                                                          self.options.device)
                        finally:
                            model_load_seconds += time.perf_counter() - load_started
                    image = page._backend.get_page_image(scale=self.options.scale, cropbox=rect).convert('RGB')
                    region['image_size'] = list(image.size)
                    result = self.engine.ocr(np.asarray(image)[:, :, ::-1].copy())
                    cells, lines = result_cells(result, rect, image.size, len(all_cells), self.options.parameters['drop_score'])
                    region['lines'] = lines
                    region['status'] = 'recognized' if cells else ('low_confidence' if lines else 'ocr_no_text')
                    all_cells.extend(cells)
                # Docling 依 PDF_FIRST 處理交疊，記錄部分相交風險；不自動改寫原文。
                native = page.parsed_page.textline_cells if page.parsed_page else []
                diagnostic['partial_overlap_count'] = count_partial_overlaps(all_cells, native, page.size.height)
                self.post_process_cells(all_cells, page, conv_res)
                kept = [c for c in page.parsed_page.textline_cells if c.from_ocr] if page.parsed_page else []
                diagnostic.update(ocr_cells_before_merge=len(all_cells), ocr_cells_after_merge=len(kept))
                if rects:
                    diagnostic['status'] = 'recognized_needs_review' if all_cells else 'ocr_no_text'
                if diagnostic['partial_overlap_count']:
                    diagnostic['status'] = 'partial_overlap_needs_review'
            except Exception as exc:
                diagnostic.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                raise RuntimeError(f'MinerU OCR 第 {page.page_no} 頁失敗：{exc}') from exc
            finally:
                diagnostic['timing'] = {'ocr_seconds': max(0.0, time.perf_counter()-started-model_load_seconds),
                                        'model_load_seconds': model_load_seconds, 'model_load_calls': model_load_calls}
            yield page


def count_partial_overlaps(ocr_cells, native_cells, page_height):
    count = 0
    for ocr in ocr_cells:
        a = ocr.rect.to_bounding_box().to_top_left_origin(page_height=page_height)
        for native in native_cells:
            if getattr(native, 'from_ocr', False):
                continue
            b = native.rect.to_bounding_box().to_top_left_origin(page_height=page_height)
            intersection = max(0, min(a.r, b.r)-max(a.l, b.l)) * max(0, min(a.b, b.b)-max(a.t, b.t))
            if 0 < intersection < a.area():
                count += 1
                break
    return count


def register_ocr():
    from docling.models.factories import get_ocr_factory
    factory = get_ocr_factory(allow_external_plugins=False)
    if MineruOcrOptions not in factory.classes:
        factory.register(MineruOcrModel, plugin_name='financial_report_local', plugin_module_name=__name__)


def collect_diagnostics(converter):
    return [item for pipeline in converter.initialized_pipelines.values()
            for item in getattr(getattr(pipeline, 'ocr_model', None), 'diagnostics', [])]
