"""本機合成標籤／入口驗證，與真實文件人工核對分開記錄。"""
import json
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from html import unescape
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.markdown_processing.tag_markdown import tag_markdown as _tag_markdown,restore_tagged_markdown,text_hash
from schemas import TaggingMetadata,NotesScope
from config.markdown_tagging import TAGGING_VERSION
from functions.markdown_processing.classify_tag_heading import classify_tag_heading
import main

ROOT='## 合併財務報告附註\n'


def synthetic_scope(text):
    # 僅測試夾具：明確使用首個中文章節至EOF；正式流程絕不自動採此規則。
    lines=text.splitlines(keepends=True)
    start=next((i for i,line in enumerate(lines,1)
                if (heading:=classify_tag_heading(line.rstrip('\r\n'))) and heading.role=='section'),1)
    return NotesScope(start,len(lines),text_hash(text),'synthetic_fixture')


def tag_markdown(text,metadata=None):
    if text.startswith('<!-- RAG_TAGGING'):
        return _tag_markdown(text,metadata)
    return _tag_markdown(text,metadata,notes_scope=synthetic_scope(text))



class TaggingTests(unittest.TestCase):
    def test_single_notes_scope_and_excluded_before_after_do_not_enter_hierarchy(self):
        before='## 一、前段報表\r\n<table><tr><td>原表</td></tr></table>\n'
        inside='## 一、公司沿革\n文字\n## 二、通過程序\n'+ROOT+'後續文字\n'
        after='## 一、其他非附註\n尾文'
        text=before+inside+after
        start=len(before.splitlines())+1;end=len((before+inside).splitlines())
        scope=NotesScope(start,end,text_hash(text),'synthetic_confirmed_scope')
        result=_tag_markdown(text,notes_scope=scope)
        self.assertEqual(result.markdown.count('<notes '),1)
        self.assertEqual(result.markdown.count('<excluded '),2)
        self.assertEqual([b.path[-1].title for b in result.blocks if b.kind=='heading'],['一、公司沿革','二、通過程序'])
        self.assertEqual(result.blocks[-1].path[-1].title,'二、通過程序')
        self.assertEqual(restore_tagged_markdown(result.markdown),text)
        self.assertEqual(_tag_markdown(result.markdown).markdown,result.markdown)

    def test_unconfirmed_or_changed_scope_fails_and_cannot_cut_table(self):
        text='## 一、公司\n<table>\n<tr><td>表格</td></tr>\n</table>\n'
        with self.assertRaises(ValueError):_tag_markdown(text)
        for scope in [NotesScope(1,4,'0'*64,'bad_hash'),NotesScope(0,4,text_hash(text),'bad_range'),
                      NotesScope(1,3,text_hash(text),'cuts_table')]:
            with self.subTest(scope=scope),self.assertRaises(ValueError):
                _tag_markdown(text,notes_scope=scope)

    def test_old_tagging_version_can_be_restored_without_reusing_old_hierarchy(self):
        raw='## 合併財務報告附註\n'
        old=(f'<!-- RAG_TAGGING version="markdown-tagging/1.0" original_sha256="{text_hash(raw)}" -->\n'
             '<hd1 generator="financial-rag-tagging" version="markdown-tagging/1.0" id="b000001" added_eol="0">\n'+
             raw+'</hd1><!-- RAG_TAG_END b000001 -->\n')
        self.assertEqual(restore_tagged_markdown(old),raw)
        with self.assertRaises(ValueError):_tag_markdown(old)  # 沒有已確認範圍，不套舊主標起點。

    def test_hd_number_matches_level_and_same_level_replaces(self):
        text=ROOT+'## 四 、重大會計政策\n## (一) 金融工具\n## 1. 資產\n## 2. 負債\n## (二) 存貨\n說明\n'
        result=tag_markdown(text)
        headings=[b for b in result.blocks if b.kind=='heading']
        self.assertEqual([b.path[-1].level for b in headings],[1,2,3,3,2])
        self.assertEqual([x.title for x in result.blocks[-1].path],['四 、重大會計政策','(二) 存貨'])
        self.assertEqual(re.findall(r'^<(hd[0-9]+) ',result.markdown,re.M),['hd1','hd2','hd3','hd3','hd2'])

    def test_new_section_resets_mapping_and_late_main_does_not_reset(self):
        text=ROOT+'## 一、章節\n## (一) 方法\n## 1. 內容\n## 二、其他\n## 1. 事項\n'+ROOT+'## (1) 衡量\n'
        result=tag_markdown(text)
        headings=[b for b in result.blocks if b.kind=='heading']
        self.assertEqual(headings[-2].path[-1].level,2)
        self.assertEqual(headings[-1].path[-1].level,3)
        self.assertNotIn('合併財務報告附註',[x.title for x in headings[-1].path])

    def test_before_notes_and_unnumbered_heading_preserved_without_stack_update(self):
        before='## 一、前段\n前言\n'
        text=before+ROOT+'## 一、公司\n## 重大會計判斷\n# (1) 冒號：\n### (1) 第三層井號\n內文\n'
        result=_tag_markdown(text,notes_scope=NotesScope(4,len(text.splitlines()),text_hash(text),'synthetic_fixture'))
        self.assertIn(before,result.markdown)
        self.assertEqual([b.path[-1].title for b in result.blocks if b.kind=='heading'],['一、公司'])
        self.assertEqual(result.blocks[-1].path[-1].title,'一、公司')
        self.assertEqual({issue['status'] for issue in result.issues},
                         {'unnumbered_heading_preserved'})

    def test_table_unchanged_and_inherits_path_despite_fake_heading(self):
        table='<table data="a > b">\r\n<tr><td>## 二、不是章節</td><td>$(1,000.5) 10%</td></tr>\n</table>'
        result=tag_markdown(ROOT+'## 一、公司\n## (一) 方法\n'+table+'\n')
        block=next(b for b in result.blocks if b.kind=='table')
        self.assertEqual(block.path[-1].title,'(一) 方法')
        self.assertIn(table,result.markdown)
        self.assertEqual(result.markdown.count('<tableblock '),1)
        self.assertEqual(restore_tagged_markdown(result.markdown),ROOT+'## 一、公司\n## (一) 方法\n'+table+'\n')

    def test_metadata_blank_and_period_not_inferred_from_comparison_years(self):
        result=tag_markdown(ROOT+'## 一、公司\n114及113年度比較表\n')
        self.assertIn('company_name="" stock_code="" report_period=""',result.markdown)
        self.assertIn('pdf_pages="" printed_pages=""',result.markdown)

    def test_attribute_special_characters_and_full_path_roundtrip(self):
        text=ROOT+'## 一、A&B "標題"\n文字\n'
        result=tag_markdown(text,TaggingMetadata('A&B "公司"','0012','2025Q4'))
        value=re.findall(r' path="([^"]*)"',result.markdown)[-1]
        path=json.loads(unescape(value))
        self.assertEqual(path[-1]['title'],'一、A&B "標題"')
        self.assertIn('stock_code="0012"',result.markdown)
        self.assertEqual(restore_tagged_markdown(result.markdown),text)

    def test_pdf_page_changes_keep_hierarchy_and_printed_pages_remain_candidates(self):
        text='<!-- PDF_PAGE: 15 -->\n'+ROOT+'## 一、公司\n文字\n- 99 -\n<!-- PDF_PAGE: 16 -->\n接續文字\n'
        result=tag_markdown(text)
        content=[b for b in result.blocks if b.kind=='content']
        self.assertEqual([b.pdf_pages for b in content],[(15,),(16,)])
        self.assertEqual(content[0].path,content[1].path)
        self.assertEqual(result.printed_page_candidates[0]['candidate'],'99')
        self.assertEqual(result.printed_page_candidates[0]['pdf_page'],15)
        self.assertIn('printed_pages=""',result.markdown)

    def test_code_and_comments_do_not_change_hierarchy_or_pdf_page(self):
        text=ROOT+'## 一、公司\n```\n## 二、程式碼\n<!-- PDF_PAGE: 999 -->\n```\n<!--\n## 三、註解\n-->\n文字\n'
        result=tag_markdown(text)
        self.assertEqual(result.blocks[-1].path[-1].title,'一、公司')
        self.assertEqual(result.blocks[-1].pdf_pages,())
        self.assertEqual(restore_tagged_markdown(result.markdown),text)

    def test_cross_page_table_preserves_original_markers(self):
        table='<table>\n<tr><td>1</td></tr>\n<!-- PDF_PAGE: 16 -->\n<tr><td>2</td></tr>\n</table>\n'
        result=tag_markdown('<!-- PDF_PAGE: 15 -->\n'+ROOT+'## 一、公司\n'+table+'接續內文\n')
        block=next(b for b in result.blocks if b.kind=='table')
        self.assertEqual(block.pdf_pages,(15,16))
        self.assertEqual(result.blocks[-1].pdf_pages,(16,))
        self.assertIn(table,result.markdown)

    def test_roundtrip_mixed_newlines_no_final_newline_and_idempotence(self):
        for ending in ['', '\n', '\r\n', '\r']:
            text='前言\r\n'+ROOT+'## 一、章節\r\n內容 (1,234) -6.0%'+ending
            result=tag_markdown(text)
            self.assertEqual(restore_tagged_markdown(result.markdown),text)
            self.assertEqual(tag_markdown(result.markdown).markdown,result.markdown)

    def test_corrupted_generated_output_fails_instead_of_deleting_source(self):
        tagged=tag_markdown(ROOT+'## 一、公司\n內文\n').markdown
        for changed in [tagged.replace('內文','竄改',1),tagged.replace('</hd1>','</hd9>',1),tagged.replace(TAGGING_VERSION,'unknown',1)]:
            with self.assertRaises(ValueError):restore_tagged_markdown(changed)

    def test_missing_root_or_malformed_table_does_not_fake_success(self):
        for text in ['## 一、公司\n內文',ROOT+'<table>未閉合']:
            with self.assertRaises(ValueError):_tag_markdown(text)


class TaggingEntryTests(unittest.TestCase):
    def test_export_disabled_and_separate_runs_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            settings=replace(SETTINGS,project_root=Path(folder))
            source=settings.markdown_processed_output_dir/'財報'/'run'/'document.md'
            source.parent.mkdir(parents=True)
            text=ROOT+'## 一、公司\n內容\n'
            source.write_bytes(text.encode('utf-8'))
            result=main.run_tag_markdown(source,replace(settings,export_enabled=False),notes_scope=synthetic_scope(text))
            self.assertIsNone(result['output_dir'])
            self.assertFalse(settings.markdown_tagged_output_dir.exists())
            first=main.run_tag_markdown(source,settings,notes_scope=synthetic_scope(text));second=main.run_tag_markdown(source,settings,notes_scope=synthetic_scope(text))
            self.assertNotEqual(first['output_dir'],second['output_dir'])
            self.assertTrue(Path(first['output_dir']).is_relative_to(settings.markdown_tagged_output_dir))
            self.assertEqual(source.read_bytes(),text.encode('utf-8'))
            self.assertTrue((Path(first['output_dir'])/'manifest.json').is_file())

    def test_cli_and_menu_use_tagging_not_pdf(self):
        with patch.object(sys,'argv',['main.py','--tag-markdown','sample.md','--no-export']),patch('main.run_tag_markdown') as run,patch('main.run_markdown') as pdf:
            self.assertEqual(main.main(),0)
            self.assertFalse(run.call_args.args[1].export_enabled)
            pdf.assert_not_called()
        with patch.object(sys,'argv',['main.py']),patch('builtins.input',side_effect=['4','0']),patch('main.choose_processed_batch',return_value=Path('batch')) as choose,patch('main.tag_processed_batch',return_value=[]) as run:
            self.assertEqual(main.main(),0)
            run.assert_called_once()
            self.assertEqual(choose.call_args.args[0],SETTINGS)


if __name__=='__main__':unittest.main()
