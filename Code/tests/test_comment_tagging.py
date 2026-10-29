"""正文標題與區塊：舊目錄資料不再影響分類，不使用模型。"""
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import TaggingMetadata
from config.settings import SETTINGS
from functions.markdown_processing.comment_tagging import tag_comments
from functions.markdown_processing.tag_batch import tag_processed_batch
from functions.markdown_processing.mark_headings import mark_missing_headings
from test_toc import fixture


def toc_fixture():
    toc = {'status': 'extracted_needs_review', 'source_pages': [2, 3],
           'source_sha256': 'a' * 64, 'pages': fixture()['pages'], 'entries': []}
    for key, parent, title, pages in (
            ('a', '', '九、合併財務報告附註', ''),
            ('b', 'a', '(一) 公司沿革', '1'),
            ('c', 'a', '(二) 會計政策', '1~2'),
            ('d', 'a', '(三) 會計項目', '3')):
        toc['entries'].append(dict(id=key, parent_id=parent, title=title,
                                   printed_pages=pages, note_numbers='', source_pdf_page=2))
    return toc


TABLE = '<table>\n<tr><td>- 1 -</td><td>1. 表格文字</td></tr>\n</table>\n'
TEXT = ('<!-- PDF_PAGE: 1 -->\n## 一 、 公司沿革\n完整前段內文與金額 -1。\n- 1 -\n'
        '## 二、會計政策\n## (一) 金融工具\n## 1. 金融資產\n' + TABLE +
        '<!-- PDF_PAGE: 2 -->\n## (二) 存貨\n- 2 -\n'
        '<!-- PDF_PAGE: 3 -->\n## 三、會計項目\n## (1) 衡量方式\n')


class CommentTagTests(unittest.TestCase):
    def test_appendix_prefix_without_length_limit_and_protected_content(self):
        title = '附表一：' + '長表格名稱' * 10
        protected = '<table><tr><td>附表二：表內文字</td></tr></table>\n```\n附表三\n```\n<!--\n附表四\n-->\n'
        source = '<!-- PDF_PAGE: 1 -->\n## 一、公司沿革\n' + title + '\n詳附表一\n## 附表二\n' + protected + '<!-- PDF_PAGE: 3 -->\n'
        processed = mark_missing_headings(source).markdown
        result = tag_comments(processed, toc_fixture(), TaggingMetadata()).markdown
        self.assertIn('# ' + title + '\n', result)
        self.assertIn('# 附表二\n', result)
        self.assertIn('\n#### 附表二\n', result)
        self.assertIn('詳附表一\n', result)
        self.assertNotIn('# 詳附表一', result)
        self.assertIn('<table><tr><td>附表二：表內文字</td></tr></table>', result)
        self.assertIn('```\n附表三\n```', result)
        self.assertIn('<!--\n附表四\n-->', result)

    def test_cross_page_keeps_dynamic_levels_without_repeating_hd2(self):
        text = ('<!-- Page: 2330_2025_P1 -->\n## 一、會計政策\n'
                '## (一) 金融工具\n## 1. 方法\n正文\n'
                '<!-- Page: 2330_2025_P2 -->\n接續正文\n## 2. 新方法\n'
                '<!-- Page: 2330_2025_P3 -->\n## (1) 細節\n')
        tagged = tag_comments(text, toc_fixture(), TaggingMetadata(report_year='2025', stock_code='2330')).markdown
        self.assertEqual(tagged.count('<hd2>一、會計政策</hd2>'), 1)
        self.assertIn('<hd4>2. 新方法</hd4>', tagged)
        self.assertIn('<hd5>(1) 細節</hd5>', tagged)
        self.assertNotIn('<hd3>2. 新方法</hd3>', tagged)
        for page in (1, 2, 3):
            self.assertIn(f'<!-- Page: 2330_2025_P{page} -->\n<page_start>\n', tagged)

    def test_heading_replacement_preserves_unclassified_and_protected_text(self):
        protected = '<table>\n## 一、表格內\n</table>\n```\n## 一、程式碼\n```\n<!--\n## 一、註解\n-->\n'
        prefix = '<!-- PDF_PAGE: 1 -->\n## (一) 沒有上層\n## 無編號標題\n# 冒號：\n### 其他層級\n'
        source = prefix + protected + '## 一、公司沿革\n原始內文\n## (一) 基礎\n<!-- PDF_PAGE: 3 -->\n'
        tagged = tag_comments(source, toc_fixture(), TaggingMetadata()).markdown
        for block in ('<table>\n## 一、表格內\n</table>',
                      '```\n## 一、程式碼\n```', '<!--\n## 一、註解\n-->'):
            self.assertIn(block, tagged)
        for line in prefix.splitlines()[1:]:
            self.assertIn(line + '\n', tagged)
        self.assertIn('<hd2>一、公司沿革</hd2>', tagged)
        self.assertIn('<hd3>(一) 基礎</hd3>', tagged)
        self.assertNotIn('## 一、公司沿革\n', tagged)
        self.assertNotIn('## (一) 基礎\n', tagged)
        self.assertEqual(tagged.count('原始內文'), 1)

    def test_no_main_title_with_company_history_and_pages(self):
        text = '<!-- PDF_PAGE: 1 -->\n前段\n<!-- PDF_PAGE: 2 -->\n## 一、公司沿革\n## (一) 基礎\n'
        result = tag_comments(text, None, TaggingMetadata())
        self.assertNotIn('MAIN_TITLE:', result.markdown)
        self.assertIn('<hd2>一、公司沿革</hd2>', result.markdown)
        self.assertIn('<hd3>(一) 基礎</hd3>', result.markdown)
        self.assertEqual(result.issues, ())

    def test_company_history_not_required_and_protected_titles_preserved(self):
        text = '<!-- PDF_PAGE: 1 -->\n<table>\n## 一、公司沿革\n</table>\n## 一、其他事項\n'
        result = tag_comments(text, None, TaggingMetadata())
        self.assertIn('<table>\n## 一、公司沿革\n</table>', result.markdown)
        self.assertIn('<hd2>一、其他事項</hd2>', result.markdown)
        self.assertNotIn('MAIN_TITLE:', result.markdown)

    def test_legacy_temporary_setting_no_longer_changes_main_behavior(self):
        with patch('config.markdown_tagging.TEMPORARY_MAIN_FALLBACK_ENABLED', True):
            self.assertNotIn('MAIN_TITLE:', tag_comments(TEXT, None, TaggingMetadata()).markdown)

    def test_hd_rendering_replaces_recognized_headings_and_keeps_main(self):
        text = ('<!-- PDF_PAGE: 1 -->\n## 一、A & B <公司>\n'
                '## (一) 方法\n## 1. 細節\n## (1) 例外\n'
                '<!-- PDF_PAGE: 3 -->\n')
        tagged = tag_comments(text, toc_fixture(), TaggingMetadata()).markdown
        self.assertIn('<hd2>一、A &amp; B &lt;公司&gt;</hd2>', tagged)
        self.assertNotIn('## 一、A & B <公司>\n', tagged)
        for title in ('(一) 方法', '1. 細節', '(1) 例外'):
            self.assertNotIn('## ' + title + '\n', tagged)
        self.assertIn('<hd3>(一) 方法</hd3>', tagged)
        self.assertIn('<hd4>1. 細節</hd4>', tagged)
        self.assertIn('<hd5>(1) 例外</hd5>', tagged)
        self.assertNotIn('MAIN_TITLE:', tagged)
        self.assertNotIn('<hd1>', tagged)
        self.assertNotIn('<!-- SUB_TITLE:', tagged)
        self.assertNotIn('<!-- HEADING_', tagged)

    def test_existing_hd_is_rejected_but_table_code_and_comment_literals_are_preserved(self):
        for token in ('<hd2>小標</hd2>', '<hd3></hd3>', '<hd10>深層</hd10>'):
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError, '重複'):
                    tag_comments('<!-- PDF_PAGE: 1 -->\n' + token + '\n', toc_fixture(), TaggingMetadata())
        literal = '<hd2>示例</hd2>\n'
        source = ('<!-- PDF_PAGE: 1 -->\n<table>\n' + literal + '</table>\n'
                  '```html\n' + literal + '```\n<!--\n' + literal + '-->\n<!-- PDF_PAGE: 3 -->\n')
        tagged = tag_comments(source, toc_fixture(), TaggingMetadata()).markdown
        self.assertEqual(tagged.count(literal), 3)

    def test_subtitle_from_spaced_body_chinese_number_and_dynamic_reset_with_main_only_json(self):
        toc = toc_fixture()
        toc['entries'] = [dict(toc['entries'][0], printed_pages='1~3')]
        toc.update(schema_version='financial-toc/2.0', extraction_mode='main_titles')
        titles = ['一、公司沿革', '一 、公司沿革', '一、 公司沿革', '一 、 公司沿革', '十 一 、 重要事項']
        for title in titles:
            with self.subTest(title=title):
                text = ('<!-- Page: 2330_2025_P1 -->\n## ' + title + '\n'
                        '## (一) 基礎\n## 1. 方法\n'
                        '<!-- Page: 2330_2025_P2 -->\n接續內文\n'
                        '## 二 、 新小標\n## (1) 新方法\n'
                        '<!-- Page: 2330_2025_P3 -->\n')
                tagged = tag_comments(text, toc, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
                self.assertIn(f'<hd2>{title}</hd2>\n', tagged)
                self.assertNotRegex(tagged, r'<hd\d+>\s*</hd\d+>')
                self.assertNotIn(f'## {title}\n', tagged)
                self.assertIn('<hd3>(一) 基礎</hd3>', tagged)
                self.assertIn('<hd4>1. 方法</hd4>', tagged)
                self.assertIn('<hd3>(1) 新方法</hd3>', tagged)
                self.assertIn('<!-- Page: 2330_2025_P2 -->\n<page_start>', tagged)
                self.assertEqual(tagged.count(f'<hd2>{title}</hd2>'), 1)
                self.assertNotIn('<hd3>' + title + '</hd3>', tagged)

    def test_toc_page_changes_do_not_reset_heading_hierarchy(self):
        toc = toc_fixture()
        text = '<!-- PDF_PAGE: 1 -->\n## 一、舊章\n## (一) 舊下層\n<!-- PDF_PAGE: 2 -->\n## (二) 接續\n## 二、新章\n## 1. 新下層\n'
        result = tag_comments(text, toc, TaggingMetadata())
        self.assertIn('<hd3>(二) 接續</hd3>', result.markdown)
        self.assertIn('<hd3>1. 新下層</hd3>', result.markdown)
        self.assertNotRegex(result.markdown, r'<hd\d+>\s*</hd\d+>')

    def test_chinese_subtitle_inside_code_or_table_is_not_classified(self):
        toc = toc_fixture()
        text = '<!-- PDF_PAGE: 1 -->\n<table>\n## 一、表內標題\n</table>\n```\n## 二、程式碼\n```\n## 三 、 真正小標\n<!-- PDF_PAGE: 3 -->\n'
        tagged = tag_comments(text, toc, TaggingMetadata()).markdown
        self.assertNotIn('<hd2>一、表內標題</hd2>', tagged)
        self.assertNotIn('<hd2>二、程式碼</hd2>', tagged)
        self.assertIn('<hd2>三 、 真正小標</hd2>', tagged)

    def test_page_based_tags_dynamic_headings_and_source_footers_preserved(self):
        result = tag_comments(TEXT, toc_fixture(), TaggingMetadata(report_year='2025', stock_code='2330'))
        tagged = result.markdown
        self.assertNotIn('MAIN_TITLE:', tagged)
        self.assertIn('<hd2>一 、 公司沿革</hd2>', tagged)
        self.assertIn('<hd2>二、會計政策</hd2>', tagged)
        self.assertIn('<hd3>(一) 金融工具</hd3>', tagged)
        self.assertIn('<hd4>1. 金融資產</hd4>', tagged)
        self.assertIn('<hd3>(二) 存貨</hd3>', tagged)
        self.assertIn('<hd2>三、會計項目</hd2>', tagged)
        self.assertIn('<hd3>(1) 衡量方式</hd3>', tagged)
        self.assertNotIn('<hd2>(一) 公司沿革</hd2>', tagged)
        self.assertIn(TABLE, tagged)
        self.assertIn('\n- 1 -\n', tagged)
        self.assertIn('\n- 2 -\n', tagged)
        self.assertIn('金額 -1。', tagged)
        self.assertEqual(len(result.removed_page_lines), 0)
        for page in (1, 2, 3):
            self.assertEqual(tagged.count(f'<!-- PDF_PAGE: {page} -->'), 1)
        self.assertNotIn('&quot;', tagged)
        self.assertNotIn('<tableblock', tagged)
        with self.assertRaisesRegex(ValueError, '重複'):
            tag_comments(tagged, toc_fixture(), TaggingMetadata())

    def test_toc_context_ignores_body_title_matching_and_note_numbers(self):
        for text in (TEXT.replace('## 一 、 公司沿革\n', '## 一、公司沿革\n## 一、公司沿革\n'),
                     TEXT.replace('## 二、會計政策\n', '未知章節\n')):
            toc = toc_fixture()
            toc['entries'][2]['note_numbers'] = '故意不作為判斷依據'
            result = tag_comments(text, toc, TaggingMetadata())
            first_page = result.markdown.split('<!-- PDF_PAGE: 2 -->')[0]
            self.assertNotIn('<hd2>(一) 公司沿革</hd2>', first_page)
            self.assertNotIn('<hd2>(二) 會計政策</hd2>', first_page)
            if '## 二、會計政策' not in text:
                self.assertNotIn('<hd2>二、會計政策</hd2>', first_page)
            else:
                self.assertIn('<hd2>二、會計政策</hd2>', first_page)

    def test_code_footers_preserved_and_toc_ranges_unused(self):
        toc = toc_fixture()
        toc['entries'][1]['printed_pages'] = '1~99'
        result = tag_comments(TEXT, toc, TaggingMetadata())
        self.assertIn(TABLE, result.markdown)
        self.assertIn('\n- 1 -\n', result.markdown)
        self.assertNotIn('MAIN_TITLE:', result.markdown)

    def test_unknown_sub_pages_and_missing_pdf_page_are_explicit(self):
        toc = toc_fixture()
        toc['entries'][1]['printed_pages'] = ''
        result = tag_comments(TEXT, toc, TaggingMetadata())
        self.assertNotIn('<hd2>(一) 公司沿革</hd2>', result.markdown)
        self.assertIn('<hd2>一 、 公司沿革</hd2>', result.markdown)
        with self.assertRaisesRegex(ValueError, '沒有可靠'):
            tag_comments('正文\n- 1 -\n', toc_fixture(), TaggingMetadata())


class CommentTagBatchTests(unittest.TestCase):
    def test_continued_table_join_evidence_is_exported_in_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch = self.make_batch(tmp)
            text = ('<!-- PDF_PAGE: 1 -->\n## 一、公司沿革\n' + TABLE +
                    '（接 次 頁）\n<!-- PDF_PAGE: 2 -->\n' + TABLE + '<!-- PDF_PAGE: 3 -->\n')
            (batch / '2025_2330_processed.md').write_bytes(text.encode('utf-8'))
            origin_path = batch / 'Record/2025_2330_reocrd'
            origin = json.loads(origin_path.read_text(encoding='utf-8'))
            origin['output_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
            origin_path.write_text(json.dumps(origin), encoding='utf-8')
            results = tag_processed_batch(batch, settings)
            self.assertEqual(results[0]['status'], 'tagged_needs_review')
            output = Path(results[0]['output_dir'])
            record = json.loads((output / 'Record/2025_2330_reocrd').read_text(encoding='utf-8'))
            self.assertEqual(record['block_counts']['table'], 1)
            self.assertEqual(record['table_continuation_joins'][0]['markers'], ['接次頁'])
            tagged = (output / '2025_2330_tagged.md').read_text(encoding='utf-8')
            self.assertEqual(tagged.count(TABLE), 2)

    def make_batch(self, folder, missing_toc=False):
        settings = replace(SETTINGS, project_root=Path(folder))
        batch = settings.markdown_processed_output_dir / 'Financial_20261022_16-01-35'
        (batch / 'Record').mkdir(parents=True)
        (batch / '2025_2330_processed.md').write_bytes(TEXT.encode('utf-8'))
        if not missing_toc:
            (batch / '2025_2330_tablerefer.json').write_text(json.dumps(toc_fixture()), encoding='utf-8')
        origin = dict(batch=batch.name, status='processed_needs_review',
                      output_sha256=hashlib.sha256(TEXT.encode('utf-8')).hexdigest(),
                      original_pdf_sha256='a' * 64)
        (batch / 'Record' / '2025_2330_reocrd').write_text(json.dumps(origin), encoding='utf-8')
        return settings, batch

    def test_output_names_record_inside_batch_and_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch = self.make_batch(tmp)
            with patch('functions.integrations.gemini_toc.generate_toc', side_effect=AssertionError('禁止API')) as api:
                records = tag_processed_batch(batch, settings)
                api.assert_not_called()
            self.assertEqual(records[0]['status'], 'tagged_needs_review')
            out = Path(records[0]['output_dir'])
            self.assertTrue((out / '2025_2330_tagged.md').is_file())
            self.assertTrue((out / 'Record' / '2025_2330_reocrd').is_file())
            self.assertFalse((settings.markdown_tagged_output_dir / 'Record').exists())
            self.assertEqual((batch / '2025_2330_processed.md').read_bytes(), TEXT.encode('utf-8'))
            with self.assertRaises(FileExistsError):
                tag_processed_batch(batch, settings, output_batch=out)

    def test_missing_json_uses_temporary_fallback_and_no_export_still_returns_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch = self.make_batch(tmp, missing_toc=True)
            results = tag_processed_batch(batch, settings)
            self.assertEqual(results[0]['status'], 'tagged_needs_review')
            self.assertTrue(list(settings.markdown_tagged_output_dir.rglob('*_tagged.md')))
            self.assertFalse(results[0]['temporary_fallback'])
        with tempfile.TemporaryDirectory() as tmp:
            settings, batch = self.make_batch(tmp)
            results = tag_processed_batch(batch, replace(settings, export_enabled=False))
            self.assertIsNotNone(results[0]['result'])
            self.assertFalse(settings.markdown_tagged_output_dir.exists())

    def test_failed_gemini_or_invalid_json_uses_fallback_but_source_mismatch_is_blocked(self):
        for mode in ('gemini_failed', 'invalid_json', 'invalid_structure', 'wrong_pdf', 'wrong_markdown', 'no_heading'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                settings, batch = self.make_batch(tmp)
                toc_path = batch / '2025_2330_tablerefer.json'
                origin_path = batch / 'Record/2025_2330_reocrd'
                origin = json.loads(origin_path.read_text(encoding='utf-8'))
                if mode == 'gemini_failed':
                    origin['status'] = 'processed_toc_failed'
                    toc_path.unlink()
                elif mode == 'invalid_json':
                    toc_path.write_text('{', encoding='utf-8')
                elif mode == 'invalid_structure':
                    toc_path.write_text('{}', encoding='utf-8')
                elif mode == 'wrong_pdf':
                    toc = toc_fixture()
                    toc['source_sha256'] = 'b' * 64
                    toc_path.write_text(json.dumps(toc), encoding='utf-8')
                elif mode == 'wrong_markdown':
                    origin['output_sha256'] = 'b' * 64
                elif mode == 'no_heading':
                    text = TEXT.replace('公司沿革', '其他內容')
                    (batch / '2025_2330_processed.md').write_bytes(text.encode('utf-8'))
                    origin['output_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
                    toc_path.unlink()
                origin_path.write_text(json.dumps(origin), encoding='utf-8')
                with patch('functions.integrations.gemini_toc.generate_toc', side_effect=AssertionError('禁止API')):
                    results = tag_processed_batch(batch, settings)
                expected = 'tagged_needs_review'
                self.assertEqual(results[0]['status'], expected)
                output_files = list(settings.markdown_tagged_output_dir.rglob('*_tagged.md'))
                self.assertEqual(bool(output_files), expected != 'needs_confirmation')
                if mode == 'wrong_pdf':
                    self.assertNotIn('toc_record_issue', results[0])
                if mode == 'wrong_markdown':
                    self.assertIn('雜湊', results[0]['source_record_issue'])


if __name__ == '__main__':
    unittest.main()
