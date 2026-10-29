"""第三階段新分類契約；驗證分類優先、階層及下游原文保留。"""
import re
import hashlib
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.settings import SETTINGS
from functions.markdown_processing.comment_tagging import tag_comments
from functions.markdown_processing.tag_batch import tag_processed_batch
from functions.markdown_processing.note_processing import process_note_content
from functions.chunking.chunks import chunk_tagged
from config.chunking import ChunkSettings
from schemas import TaggingMetadata

PAGE = '<!-- Page: 2330_2025_P15 -->\n'
META = TaggingMetadata(report_year='2025', stock_code='2330')


class TaggingV3Tests(unittest.TestCase):
    def tag(self, body):
        return tag_comments(PAGE+body, None, META)

    def test_blank_paragraphs_stay_in_content_until_heading_or_table(self):
        result=self.tag('## 一、政策\n第一段\n\n第二段\n'
                        '## (一) 其他\n第三段\n\n第四段\n'
                        '<table><tr><td>123</td></tr></table>\n表後正文\n')
        self.assertEqual(result.version,'markdown-comment-tagging/3.3')
        contents=re.findall(r'<content_start>\n(.*?)</content_end>',result.markdown,re.S)
        self.assertEqual(len(contents),3)
        self.assertEqual(contents[0],'第一段\n\n第二段\n')
        self.assertEqual(contents[1],'第三段\n\n第四段\n')
        self.assertNotIn('<table', ''.join(contents))

    def test_date_year_and_multi_year_description_are_distinct(self):
        for title, kind in [('民國一一四年度', 'table_year'),
                            ('112 年 12 月 31 日', 'table_year'),
                            ('112及111年度', 'table_direction'),
                            ('112及111年度，所得稅組成如下：', 'table_direction'),
                            ('項目 A & B 如下：', 'content_direction')]:
            out = self.tag('##'+title+'\n').markdown
            safe = title.replace('&', '&amp;')
            self.assertIn(f'<{kind}>{safe}</{kind}>', out)
            self.assertNotIn('##'+title, out)

    def test_numbered_colon_priority_and_english_dynamic_levels(self):
        body = ('##一 、公司沿革\n## ( 一 ) 編製基礎：\n'
                '## 1. 方法\n## (1) 細節\n## A. 英文\n## (a) 英文括號\n'
                '## B. 同層返回\n## 二、其他\n## (B) 新節第一型\n')
        out = self.tag(body).markdown
        for expected in ('<hd2>一 、公司沿革</hd2>', '<hd3>( 一 ) 編製基礎：</hd3>',
                         '<hd4>1. 方法</hd4>', '<hd5>(1) 細節</hd5>',
                         '<hd6>A. 英文</hd6>', '<hd7>(a) 英文括號</hd7>',
                         '<hd6>B. 同層返回</hd6>', '<hd3>(B) 新節第一型</hd3>'):
            self.assertIn(expected, out)
        self.assertNotIn('<content_direction>( 一 )', out)

    def test_description_does_not_change_dynamic_path(self):
        out = self.tag('## 一、公司沿革\n## (一) 基礎\n## 112年度\n'
                       '## 條件如下：\n## 1. 內容\n').markdown
        self.assertIn('<hd4>1. 內容</hd4>', out)
        self.assertIn('<table_year>112年度</table_year>', out)
        self.assertIn('<content_direction>條件如下：</content_direction>', out)

    def test_special_tags_outside_body_and_existing_markers_preserved(self):
        out = self.tag('<note>\n<合併財務報告附註>\n## 一、公司沿革\n正文\n'
                       '## 112年度\n## 條件如下：\n'
                       '### 註一：原文\n#### 附 表 一：說明\n').markdown
        self.assertIn('<note>', out)
        self.assertIn('<合併財務報告附註>', out)
        self.assertIn('### 註一：原文', out)
        self.assertIn('#### 附 表 一：說明', out)
        for body in re.findall(r'<content_start>\n(.*?)</content_end>', out, re.S):
            self.assertNotIn('<table_year>', body)
            self.assertNotIn('<content_direction>', body)

    def test_protected_year_and_no_heading_unchanged(self):
        for literal in ('<table>\n## 112年度\n</table>\n',
                        '<cannotfindtable>\n## 112年度\n</cannotfindtable>\n',
                        '```\n## 112年度\n```\n', '    ## 112年度\n',
                        '<!--\n## 112年度\n-->\n', '112年度\n'):
            out = self.tag(literal).markdown
            self.assertIn(literal, out)
            self.assertNotIn('<table_year>', out)

    def test_no_main_toc_and_no_company_history_required(self):
        for toc in (None, {}, {'status': 'invalid'}):
            out = tag_comments(PAGE+'## 一、其他\n', toc, META).markdown
            self.assertNotIn('MAIN_TITLE:', out)
            self.assertIn('<hd2>一、其他</hd2>', out)

    def test_new_tags_reject_repeated_tagging(self):
        for tag in ('table_year', 'table_direction', 'content_direction'):
            with self.assertRaisesRegex(ValueError, '重複'):
                self.tag(f'<{tag}>內容</{tag}>\n')

    def test_second_stage_cleanup_before_third_and_chunk_preserves_labels(self):
        raw = '<會計師查核報告>\n<note>\n'+PAGE+'## 一、公司沿革\n## - (1) 方法\n## 112年度\n正文。\n'
        processed, _, _ = process_note_content(raw)
        self.assertIn('## (1) 方法', processed.markdown)
        self.assertNotIn('## - ', processed.markdown)
        out = tag_comments(processed.markdown, None, META).markdown
        self.assertIn('<hd3>(1) 方法</hd3>', out)
        result = chunk_tagged(out, identity=('2025', '2330'),
                              source_sha256=hashlib.sha256(out.encode('utf-8')).hexdigest(),
                              config=ChunkSettings())
        self.assertIn('<!-- table_year: 112年度 -->', result.markdown)
        self.assertNotIn('<table_year>', result.document['chunks'][0]['content'])

    def test_batch_never_opens_toc_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(SETTINGS, project_root=Path(tmp), export_enabled=False)
            batch = settings.markdown_processed_output_dir/'Financial_20261025_10-00-00'
            batch.mkdir(parents=True)
            (batch/'2025_2330_processed.md').write_text(PAGE+'## 一、其他\n', encoding='utf-8')
            # 若還嘗試讀目錄，目錄而非檔案會使read_bytes失敗。
            (batch/'2025_2330_tablerefer.json').mkdir()
            row = tag_processed_batch(batch, settings)[0]
            self.assertEqual(row['status'], 'tagged_needs_review')
            self.assertEqual(row['main_title_source'], 'disabled')
            self.assertFalse(settings.markdown_tagged_output_dir.exists())


if __name__ == '__main__':
    unittest.main()
