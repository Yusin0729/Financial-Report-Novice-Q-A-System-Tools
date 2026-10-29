"""合成規則及檔案流程測試；不以合成結果宣稱真實標題辨識正確。"""
import hashlib
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.markdown_headings import EXCLUDED_ENDINGS
from config.settings import SETTINGS
from functions.markdown_processing.mark_headings import TableBoundaryError, mark_missing_headings
from main import main, run_mark_headings


class HeadingRulesTests(unittest.TestCase):
    def test_spaced_markers_preserve_text_and_candidate_constraints(self):
        for line in ['二十 、 權 益', '( 一 ) 普通 股 股本', '（ 二 ） 方法',
                     '1 2 . 現金', '( 1 ) 方法', 'A . 方法', '( a ) 方法',
                     '- ( 1 ) 方法', '二\t十\u3000、 權 益']:
            with self.subTest(line=line):
                marked = mark_missing_headings(line).markdown
                self.assertEqual(marked, '## ' + line)
                self.assertEqual(mark_missing_headings(marked).markdown, marked)
        for line in ['二十 、 ' + '甲'*21, '( 一 ) 方法。', '( 1 )   ',
                     '4 . 375%']:
            self.assertEqual(mark_missing_headings(line).markdown, line)

    def test_dash_list_four_markers_preserves_original_and_is_idempotent(self):
        for line in ['- (1) 透過損益按公允價值衡量之金融資產', '- 一、公司沿革',
                     '- （一）編製基礎', '- 1. 現金', '  - (1) 衡量方式']:
            with self.subTest(line=line):
                result=mark_missing_headings(line)
                self.assertEqual(result.markdown,'## '+line)
                self.assertEqual(mark_missing_headings(result.markdown).changes,())

    def test_dash_does_not_promote_pages_or_unrecognized_bullet_content(self):
        text='\n'.join(['- 15 -','-15-','- 123 -','  - 2 -  ', '- 15', '- A. 英文',
                        '- 普通列表','- ## 原有標題', '-(1)無列表空白','<!-- PDF_PAGE: 15 -->'])
        self.assertEqual(mark_missing_headings(text).markdown,text.replace('- A. 英文', '## - A. 英文'))

    def test_dash_candidates_still_require_length_and_punctuation_rules(self):
        for text in ['- (1) '+('甲'*21), '- (一) 方法。', '- 1.   ']:
            self.assertEqual(mark_missing_headings(text).markdown,text)
        self.assertEqual(mark_missing_headings('- (1) 方法：').markdown,'## - (1) 方法：')
        text='<table>\n- (1) 方法\n</table>'
        self.assertEqual(mark_missing_headings(text).markdown,text)

    def test_four_types_and_confirmed_brackets_ranges(self):
        for line in ['一、公司沿革', '十百、未驗證中文數值', '(一) 編製基礎', '（二）編製基礎',
                     '1. 現金及約當現金', '0. 零', '01. 前導零', '99. 其他', '(1) 衡量方式', '（01）方法']:
            with self.subTest(line=line):
                self.assertEqual(mark_missing_headings(line).markdown, '## '+line)

    def test_unsupported_numbering_not_expanded(self):
        text='\n'.join(['一.公司沿革', '(一）混搭', '（1)混搭', '100. 超過兩位', '(100)超過兩位',
                        '１.全形數字', '(١)非半形', '零、零', '壹、公司'])
        self.assertEqual(mark_missing_headings(text).markdown, text)

    def test_empty_and_length_20_21_excluding_inner_spaces(self):
        for tail in ['', '   ', '\t', '甲'*21, '甲'*10+' '+'乙'*11]:
            text='一、 '+tail
            self.assertEqual(mark_missing_headings(text).markdown,text)
        for tail in ['甲'*20, '甲'*9+' '+'乙'*10, '甲'*10+' \t\u3000 '+'乙'*10]:
            text='一、  '+tail+'  '
            self.assertEqual(mark_missing_headings(text).markdown,'## '+text)

    def test_colon_paragraph_bypasses_length_and_only_line_end(self):
        for colon in ':：':
            for text in ['(1) 方法'+colon+'  ', '1. '+('甲'*19)+colon]:
                self.assertEqual(mark_missing_headings(text).markdown,'## '+text.rstrip())
            text='1. '+('甲'*20)+colon
            self.assertEqual(mark_missing_headings(text).markdown,'## '+text)
            text='(一) 金額'+colon+'說明'
            self.assertEqual(mark_missing_headings(text).markdown,'## '+text)

    def test_all_exclusions_and_ascii_period_not_excluded(self):
        self.assertEqual(EXCLUDED_ENDINGS,frozenset('，。；！？,;!?」』"\')）]'))
        for ending in EXCLUDED_ENDINGS:
            text='1. 內容'+ending+'  '
            with self.subTest(ending=ending):
                self.assertEqual(mark_missing_headings(text).markdown,text)
        self.assertEqual(mark_missing_headings('1. 內容.').markdown,'## 1. 內容.')

    def test_existing_headings_never_reclassified_or_cleaned(self):
        text='# 1. 舊標題：\n## 一、公司沿革\n   ### (1)舊標題\n#### A\n###### 第六層\n#無空白亦保留'
        self.assertEqual(mark_missing_headings(text).markdown,text)

    def test_no_splitting_merging_or_underlining_conversion(self):
        text='一、短標題 後面整行有很長很長很長很長而且超過限制的內文\n(一)\n下一行\n<u>公司</u>\nA. 不處理。'
        self.assertEqual(mark_missing_headings(text).markdown,text)
        self.assertEqual(mark_missing_headings('1. A B  C').markdown,'## 1. A B  C')

    def test_exact_whitespace_newline_financial_symbols_and_idempotence(self):
        text='\ufeff一、公司沿革\r\n  (一) 新臺幣 -1.5%\n1. (1,234) 金額\r(1) 衡量方式  '
        result=mark_missing_headings(text)
        self.assertTrue(result.markdown.startswith('\ufeff## 一、'))
        self.assertEqual(len(result.changes),4)
        before=text.splitlines(keepends=True);after=result.markdown.splitlines(keepends=True)
        for a,b in zip(before,after):
            if a.startswith('\ufeff'):
                self.assertEqual(b,'\ufeff## '+a[1:])
            else:
                self.assertIn(b, ['# '+a,'## '+a])
        self.assertEqual(mark_missing_headings(result.markdown).markdown,result.markdown)
        self.assertEqual(mark_missing_headings(result.markdown).changes,())


class ProtectedContentTests(unittest.TestCase):
    def test_cross_line_single_line_nested_and_attribute_tables_exact(self):
        table='<TABLE data-note="x > <table>">\r\n一、不可更動\n## 原標題\n<table><tr><td>1. 100%</td></tr></table>\n</TABLE>'
        text='一、表前\n'+table+'\n(一)表後\n1. 同行<table>\n二、表中\n</table>尾端\n(1)最後'
        result=mark_missing_headings(text)
        self.assertIn(table,result.markdown)
        self.assertEqual([x.line_number for x in result.changes],[1,7,11])
        self.assertIn('1. 同行<table>\n二、表中\n</table>尾端',result.markdown)

    def test_same_line_open_close_preserves_entire_line(self):
        text='一、前綴 <table><tr><td>(一) 文字</td></tr></table> 尾文\n1. 下一行'
        self.assertEqual(mark_missing_headings(text).markdown,text.replace('\n1.', '\n## 1.'))

    def test_malformed_boundaries_fail_before_returning_partial_output(self):
        for broken in ['<table>\n一、表中', '</table>', '<table/>', '<table',
                       '<table data="unclosed>\n</table>', '<table></table extra>',
                       '<table><table></table>', '<table></table></table>']:
            with self.subTest(broken=broken),self.assertRaises(TableBoundaryError):
                mark_missing_headings('一、前面合法\n'+broken)

    def test_comments_fences_and_indented_code_unchanged(self):
        text='<!-- PDF_PAGE: 15 -->\n<!--\n1. 註解\n<table> 假標籤\n-->\n```html\n<table>\n一、程式\n```\n~~~\n(1) 程式\n~~~\n    1. 縮排程式\n\t(一)程式\n一、真正標題'
        self.assertEqual(mark_missing_headings(text).markdown,text.replace('一、真正標題','## 一、真正標題'))

    def test_fences_within_html_table_are_plain_table_content(self):
        text='<table>\n```\n一、表中\n</table>\n(1)表後'
        self.assertEqual(mark_missing_headings(text).markdown,text.replace('(1)表後','## (1)表後'))


class HeadingFileTests(unittest.TestCase):
    def test_utf8_bytes_preserved_source_unchanged_and_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            settings=replace(SETTINGS,project_root=Path(folder))
            source=settings.markdown_output_dir/'財報'/'run'/'document.md'
            source.parent.mkdir(parents=True)
            data='<note>\r\n一、公司\r\n<table>\r\n1. 原表格 \n</table>\n<!-- PDF_PAGE: 2 -->'.encode('utf-8')
            source.write_bytes(data)
            first=run_mark_headings(source.parent,settings)
            second=run_mark_headings(source,settings)
            self.assertEqual(source.read_bytes(),data)
            self.assertEqual(first['source']['sha256'],hashlib.sha256(data).hexdigest())
            target=Path(first['output_dir'])
            self.assertNotEqual(first['output_dir'],second['output_dir'])
            self.assertTrue(target.is_relative_to(settings.markdown_processed_output_dir/'財報'/'run'/'document'))
            saved=(target/'document.md').read_bytes()
            self.assertEqual(saved,data.replace('一、公司'.encode('utf-8'), '## 一、公司'.encode('utf-8')))
            self.assertTrue((target/'manifest.json').is_file())
            self.assertEqual(first['changes'][0]['line_number'],2)

    def test_export_disabled_and_invalid_table_create_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'sample.md';source.write_bytes('<note>\n一、公司'.encode('utf-8'))
            settings=replace(SETTINGS,project_root=Path(folder),export_enabled=False)
            result=run_mark_headings(source,settings)
            self.assertEqual(result['result'].markdown,'<note>\n## 一、公司')
            self.assertIsNone(result['output_dir'])
            self.assertFalse(settings.markdown_processed_output_dir.exists())
            source.write_bytes(b'<table>')
            with self.assertRaises(TableBoundaryError):
                run_mark_headings(source,replace(settings,export_enabled=True))
            self.assertFalse(settings.markdown_processed_output_dir.exists())

    def test_bad_encoding_is_error_not_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'sample.md';source.write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError):
                run_mark_headings(source,replace(SETTINGS,export_enabled=False))

    def test_menu_and_cli_do_not_run_pdf_conversion(self):
        with patch.object(sys,'argv',['main.py','--mark-headings','sample.md','--no-export']),patch('main.run_mark_headings') as run,patch('main.run_markdown') as pdf:
            self.assertEqual(main(),0)
            self.assertFalse(run.call_args.args[1].export_enabled)
            pdf.assert_not_called()
        with patch.object(sys,'argv',['main.py']),patch('builtins.input',side_effect=['3','0']),patch('main.choose_raw_batch',return_value=Path('batch')),patch('main.process_raw_batch',return_value=[]) as run,patch('main.run_markdown') as pdf:
            self.assertEqual(main(),0)
            run.assert_called_once()
            pdf.assert_not_called()


if __name__ == '__main__':
    unittest.main()
