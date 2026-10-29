"""章節欄位與多路徑格式；不把同層標題串成父子、不建向量。"""
import sys
import hashlib
import unittest
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from schemas import TaggingMetadata
from functions.markdown_processing.comment_tagging import tag_comments
from functions.chunking.chunks import chunk_tagged, validate_chunk_document
from Code_2.functions.embedding.prepare import prepare_document, validate_document

PAGE = '<!-- Page: 2330_2025_P15 -->\n'


def convert(raw):
    tagged = tag_comments(raw, None, TaggingMetadata(report_year='2025', stock_code='2330')).markdown
    return chunk_tagged(tagged, identity=('2025','2330'), source_sha256=hashlib.sha256(tagged.encode()).hexdigest())


class SectionFieldTests(unittest.TestCase):
    def test_sibling_paths_and_markdown_are_distinct(self):
        result = convert('<note>\n'+PAGE+'## 一、政策\n## (一) 金融工具\n'
                         '## 1. 金融資產\n資產正文。\n## 2. 金融負債\n負債正文。\n')
        chunk = result.document['chunks'][0]
        self.assertEqual(chunk['main_section'], '合併財務報告附註')
        self.assertEqual(chunk['sub_section'], '一、政策')
        self.assertEqual(chunk['note_title'], ['(一) 金融工具 > 1. 金融資產', '(一) 金融工具 > 2. 金融負債'])
        self.assertIn('<!-- Main_Section: 合併財務報告附註 -->', result.markdown)
        for path in chunk['note_title']:
            self.assertIn('<!-- Note_Title: '+path+' -->', result.markdown)
        self.assertNotIn('&gt;', result.markdown)
        self.assertNotIn('<hd2>', result.markdown)

    def test_audit_fields_empty_note_and_parent_columns(self):
        result = convert('<會計師查核報告>\n'+PAGE+'## 查核意見\n查核正文。\n')
        chunk = result.document['chunks'][0]
        self.assertEqual((chunk['main_section'], chunk['sub_section'], chunk['note_title']),
                         ('會計師查核報告','查核意見',[]))
        self.assertIn('<!-- Note_Title:  -->', result.markdown)
        self.assertIn('<!-- parent_id:  -->', result.markdown)
        self.assertIn('<!-- part_index:  -->', result.markdown)

    def test_unknown_headings_stay_empty_without_fake_titles(self):
        result = convert('<會計師查核報告>\n'+PAGE+'沒有標題的正文。\n')
        chunk = result.document['chunks'][0]
        self.assertEqual(chunk['sub_section'], '')
        self.assertEqual(chunk['note_title'], [])
        self.assertIsNone(chunk['title']['heading'])
        self.assertIn('<!-- Sub_Section:  -->', result.markdown)

    def test_appendix_uses_actual_hd2_not_appendix_name_for_sub_section(self):
        table = '<table><tr><th>114年度</th></tr><tr><td>123</td></tr></table>\n'
        result = convert('<note>\n'+PAGE+'## 一、其他揭露\n#### 附表一：資料\n'+table)
        items = result.document['chunks']+result.document['parents']
        self.assertTrue(items)
        self.assertTrue(all(c['main_section']=='合併財務報告附註' for c in items))
        self.assertTrue(all(c['sub_section']=='一、其他揭露' for c in items))
        self.assertTrue(all(c['appendix_id']=='附表一' for c in items))

    def test_new_fields_are_validated_and_preparation_preserves_types(self):
        result = convert('<note>\n'+PAGE+'## 一、政策\n## (一) 基礎\n正文。\n')
        prepared = prepare_document(result.document, input_sha256='b'*64)
        meta = prepared['chunks'][0]['metadata']
        self.assertEqual(meta['main_section'], '合併財務報告附註')
        self.assertEqual(meta['sub_section'], '一、政策')
        self.assertEqual(meta['note_title'], ['(一) 基礎'])
        self.assertIsInstance(meta['note_title'], list)
        for field, value in [('main_section','錯誤區域'), ('sub_section','錯誤標題'), ('note_title','不是清單')]:
            doc = deepcopy(result.document)
            doc['chunks'][0][field] = value
            with self.assertRaises(ValueError):
                validate_chunk_document(doc)
            with self.assertRaises(ValueError):
                validate_document(doc)


if __name__ == '__main__':
    unittest.main()
