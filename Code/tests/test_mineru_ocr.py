"""無模型工程測試；不代表實際 OCR 或財報品質通過。"""
import sys
import unittest
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling_core.types.doc import BoundingBox, CoordOrigin
from functions.integrations.docling_mineru_ocr import MineruOcrModel, MineruOcrOptions, result_cells
from PIL import Image


def bbox(l=10.25, t=20.5, r=110.75, b=71.0):
    return BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT)


def model(enabled=True):
    return MineruOcrModel(enabled=enabled, artifacts_path=None,
                          options=MineruOcrOptions(cache_dir='unused', parameters=asdict(SETTINGS.ocr)),
                          accelerator_options=AcceleratorOptions(device='cpu'))


class GeometryTests(unittest.TestCase):
    def test_actual_dimensions_offset_rotation_and_financial_text(self):
        quad = [[3, 6], [300, 9], [297, 150], [0, 147]]
        text = '新臺幣 (1,234.50) -6.00 100% 114年度'
        cells, lines = result_cells([[[quad, (text, .91)]]], bbox(), (302, 152), 7, .5)
        self.assertEqual(cells[0].text, text)
        self.assertEqual(cells[0].index, 7)
        self.assertAlmostEqual(cells[0].rect.r_x0, 10.25+3/302*100.5)
        self.assertAlmostEqual(cells[0].rect.r_y0, 20.5+6/152*50.5)
        self.assertNotEqual(cells[0].rect.r_y0, cells[0].rect.r_y1)
        self.assertEqual(lines[0]['confidence'], .91)

    def test_low_confidence_and_empty_are_not_success(self):
        quad = [[0, 0], [10, 0], [10, 10], [0, 10]]
        cells, lines = result_cells([[[quad, ('(10%)', .49)]]], bbox(), (302, 152), 0, .5)
        self.assertEqual(cells, [])
        self.assertFalse(lines[0]['accepted'])
        self.assertEqual(result_cells([None], bbox(), (302, 152), 0, .5), ([], []))

    def test_invalid_scores_coordinates_and_format_fail(self):
        for result in [None, [], [[[ [[0,0],[999,0],[10,10],[0,10]], ('x',.9) ]]],
                       [[[ [[0,0],[10,0],[10,10],[0,10]], ('x',float('nan')) ]]]]:
            with self.subTest(result=result), self.assertRaises((ValueError, TypeError)):
                result_cells(result, bbox(), (302,152), 0, .5)


class StageTests(unittest.TestCase):
    def setup_page(self):
        native_quad = [[0,0],[20,0],[20,10],[0,10]]
        native, _ = result_cells([[[native_quad, ('native', 1.)]]], bbox(0,0,100,100), (100,100), 0, .5)
        native[0].from_ocr = False
        parsed = NS(textline_cells=native, has_lines=True)
        page = NS(page_no=1, size=NS(height=100, width=100), parsed_page=parsed,
                  cells=native, _backend=Mock())
        page._backend.is_valid.return_value=True
        page._backend.get_page_image.return_value=Image.new('RGB',(300,300),'white')
        conv = NS(confidence=NS(pages=defaultdict(NS)))
        return page, conv

    def test_mixed_native_duplicate_removed_scan_retained(self):
        stage = model()
        stage.engine = Mock()
        stage.engine.ocr.return_value = [[
            [[[0,0],[60,0],[60,30],[0,30]], ('native',.9)],
            [[[90,90],[240,90],[240,120],[90,120]], ('scan (100%)',.95)],
        ]]
        page, conv = self.setup_page()
        with patch.object(stage,'get_ocr_rects', return_value=[bbox(0,0,100,100)]):
            self.assertEqual(list(stage(conv,[page])), [page])
        texts = [c.text for c in page.parsed_page.textline_cells]
        self.assertEqual(texts,['native','scan (100%)'])
        self.assertEqual(stage.diagnostics[0]['ocr_cells_after_merge'],1)

    def test_no_regions_does_not_initialize_engine(self):
        stage = model()
        page, conv = self.setup_page()
        with patch.object(stage,'get_ocr_rects', return_value=[]):
            list(stage(conv,[page]))
        self.assertIsNone(stage.engine)

    def test_exception_and_empty_distinct_and_partial_overlap_reported(self):
        for response in [[], None, 'partial']:
            stage = model()
            stage.engine = Mock()
            page,conv=self.setup_page()
            if response is None:
                stage.engine.ocr.side_effect=RuntimeError('simulated failure')
            elif response == 'partial':
                stage.engine.ocr.return_value=[[[[[30,0],[90,0],[90,30],[30,30]],('overlap',.9)]]]
            else:
                stage.engine.ocr.return_value=[[]]
            with patch.object(stage,'get_ocr_rects',return_value=[bbox(0,0,100,100)]):
                if response is None:
                    with self.assertRaisesRegex(RuntimeError,'第 1 頁失敗'):
                        list(stage(conv,[page]))
                    self.assertEqual(stage.diagnostics[0]['status'],'failed')
                else:
                    list(stage(conv,[page]))
                    expected='partial_overlap_needs_review' if response == 'partial' else 'ocr_no_text'
                    self.assertEqual(stage.diagnostics[0]['status'],expected)


if __name__ == '__main__':
    unittest.main()
