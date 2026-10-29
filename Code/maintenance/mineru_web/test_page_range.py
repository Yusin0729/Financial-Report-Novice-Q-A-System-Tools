"""Page-selection tests using generated PDFs and mocked OCR, not OCR accuracy tests."""
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import Mock
import pypdfium2 as pdfium


class InputError(Exception):
    pass


def run_immediate(coroutine):
    """Test doubles do not suspend or use network/event-loop resources."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError('Test coroutine unexpectedly suspended')


def definitions(path, names, namespace):
    nodes = ast.parse(path.read_text(encoding='utf-8-sig')).body
    selected = [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert len(selected) == len(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)


class PageRangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.pdf'
        with pdfium.PdfDocument.new() as pdf:
            for width in (101, 202, 303, 404):
                pdf.new_page(width, 500).close()
            pdf.save(self.source)
        self.hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.ns = dict(Path=Path, json=json, os=__import__('os'), time=time, re=re,
                       logger=Mock(), gr=type('Gr', (), {'Error': InputError}),
                       read_fn=lambda path: Path(path).read_bytes(),
                       to_pdf=lambda path: path, str_sha256=lambda text: 'test_archive',
                       replace_image_with_base64=lambda text, _: text)
        file = Path(__file__).with_name('gradio_app.py')
        if not file.exists():
            file = Path(__file__).parent / 'mineru/cli/gradio_app.py'
        definitions(file, {'validate_page_range', 'parse_pdf', 'to_markdown', 'safe_stem'}, self.ns)

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.hash)

    def test_inclusive_range_and_blank_end(self):
        validate = self.ns['validate_page_range']
        self.assertEqual(validate(self.source, 2, 3), (2, 3, 4))
        self.assertEqual(validate(self.source, 1, None), (1, 4, 4))
        self.assertEqual(validate(self.source, 1, ''), (1, 4, 4))
        self.assertEqual(validate(self.source, 1, '  '), (1, 4, 4))
        self.assertEqual(validate(self.source, 4, 4), (4, 4, 4))

    def test_invalid_ranges_are_rejected(self):
        for start, end in [(0, 3), (-1, 2), (3, 2), (1, 5), (1.5, 3), (True, 2), (1, float('inf'))]:
            with self.subTest(start=start, end=end), self.assertRaises(InputError):
                self.ns['validate_page_range'](self.source, start, end)

    def test_parse_passes_zero_based_inclusive_range(self):
        async def fake_parse(**kwargs):
            self.assertEqual(kwargs['start_page_id'], 1)
            self.assertEqual(kwargs['end_page_id'], 2)
            self.assertEqual(kwargs['p_lang_list'], ['chinese_cht'])
        def prepare(output, stem, mode):
            self.assertIn('_p2-3_', stem)
            return str(self.root), str(self.root)
        self.ns.update(aio_do_parse=fake_parse, prepare_env=prepare)
        run_immediate(self.ns['parse_pdf'](self.source, str(self.root), 1, 2,
                                        False, True, True, 'chinese_cht', 'pipeline', None))

    def test_page_map_is_created_before_archive(self):
        async def fake_parse(*args):
            self.assertEqual(args[2:4], (1, 2))
            (self.root / 'slice.md').write_text('mock conversion', encoding='utf-8')
            return str(self.root), 'slice'
        def archive(directory, target):
            mapping = json.loads((Path(directory) / 'page_range.json').read_text(encoding='utf-8'))
            self.assertEqual([p['source_pdf_page'] for p in mapping['pages']], [2, 3])
            self.assertEqual([p['mineru_page_idx'] for p in mapping['pages']], [0, 1])
            return 0
        self.ns.update(parse_pdf=fake_parse, compress_directory_to_zip=archive)
        result = run_immediate(self.ns['to_markdown'](str(self.source), 2, 3))
        self.assertEqual(result[1], 'mock conversion')

    def test_missing_upload_rejected(self):
        with self.assertRaises(InputError):
            run_immediate(self.ns['to_markdown'](None, 1, None))

    def test_actual_mineru_pdf_slice_selects_original_pages_2_and_3(self):
        original_root = Path('D:/桌面/pdf轉成markdown/MinerU_Protago-master')
        namespace = dict(pdfium=pdfium, io=io, logger=Mock(),
                         get_end_page_id=lambda end, length: min(length - 1, end))
        definitions(original_root / 'mineru/cli/common.py',
                    {'convert_pdf_bytes_to_bytes_by_pypdfium2'}, namespace)
        data = namespace['convert_pdf_bytes_to_bytes_by_pypdfium2'](self.source.read_bytes(), 1, 2)
        with pdfium.PdfDocument(data) as pdf:
            self.assertEqual(len(pdf), 2)
            widths = []
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    widths.append(round(page.get_width()))
                finally:
                    page.close()
            self.assertEqual(widths, [202, 303])


if __name__ == '__main__':
    unittest.main(verbosity=2)
