"""第一階段新頁序註解及後續新舊格式相容；不載入轉換模型。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from functions.markdown_processing.page_markers import format_page_marker, parse_page_marker
from functions.markdown_processing.load_source import is_selectable_markdown
from functions.ingestion.pdf_to_markdown import serialize_document
from functions.markdown_processing.comment_tagging import tag_comments
from schemas import TaggingMetadata
from test_markdown import sample_document
from test_comment_tagging import TEXT, toc_fixture


class PageMarkerTests(unittest.TestCase):
    def test_docling_serializer_generates_requested_identity_and_physical_page(self):
        result = serialize_document(sample_document(), 3, 'html', pdf_identity=('2025', '2330'))
        for page in (1, 2, 3):
            self.assertIn(f'<!-- Page: 2330_2025_P{page} -->', result.markdown)
        self.assertNotIn('<!-- PDF_PAGE:', result.markdown)
        self.assertIn('NO_TEXT_EXTRACTED', result.markdown)
        self.assertIn('colspan="2"', result.markdown)
        self.assertNotIn('<!-- Page:', result.raw_markdown)

    def test_parser_accepts_legacy_and_new_and_rejects_wrong_identity(self):
        self.assertEqual(format_page_marker(2, ('2025', '2330')), '<!-- Page: 2330_2025_P2 -->')
        self.assertEqual(parse_page_marker('<!-- PDF_PAGE: 2 -->'), 2)
        self.assertEqual(parse_page_marker('<!-- Page: 2330_2025_P2 -->'), 2)
        self.assertIsNone(parse_page_marker('<!-- Page: 2330_2025_P0 -->'))
        with self.assertRaisesRegex(ValueError, '不符'):
            parse_page_marker('<!-- Page: 2330_2025_P2 -->', expected_identity=('2024', '2330'))

    def test_new_raw_is_selectable_and_tagging_preserves_new_markers(self):
        text = TEXT
        for page in (1, 2, 3):
            text = text.replace(f'<!-- PDF_PAGE: {page} -->', format_page_marker(page, ('2025', '2330')))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / '2025_2330_raw.md'
            source.write_text(text, encoding='utf-8')
            self.assertTrue(is_selectable_markdown(source))
        result = tag_comments(text, toc_fixture(), TaggingMetadata(report_year='2025', stock_code='2330'))
        for page in (1, 2, 3):
            self.assertEqual(result.markdown.count(format_page_marker(page, ('2025', '2330'))), 1)
        self.assertIn('<hd2>一 、 公司沿革</hd2>', result.markdown)


if __name__ == '__main__':
    unittest.main()
