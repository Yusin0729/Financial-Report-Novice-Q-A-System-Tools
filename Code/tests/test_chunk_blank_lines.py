"""空行最後清理，不改切分、來源或父子契約；不呼叫模型。"""
import unittest
from test_hierarchical_modes import run
from functions.content_context import content_body
from functions.chunking.blank_lines import remove_blank_lines
from functions.chunking.chunks import validate_chunk_document
from Code.functions.embedding.prepare import prepare_document


class ChunkBlankLineTests(unittest.TestCase):
    def check_document(self, doc):
        validate_chunk_document(doc)
        prepare_document(doc, input_sha256='a' * 64)
        for item in doc['chunks'] + doc['parents']:
            self.assertTrue(all(line.strip() for line in content_body(item).splitlines()))
        return doc

    def test_both_modes_keep_inline_spaces_and_nonempty_lines(self):
        for mode in ('original', 'parent_child'):
            with self.subTest(mode=mode):
                doc = self.check_document(run('甲 乙\n\n \t\n丙 (1,234.50)\n', mode).document)
                self.assertEqual(content_body(doc['chunks'][0]), '甲 乙\n丙 (1,234.50)\n')
                self.assertTrue(doc['removed_blank_line_spans'])

    def test_split_still_uses_original_blank_boundary(self):
        doc = self.check_document(run('甲'*400+'\n\n'+'乙'*400+'\n', 'parent_child').document)
        self.assertEqual([c['body_char_count'] for c in doc['chunks']], [400, 400])
        self.assertEqual(content_body(doc['parents'][0]), '甲'*400+'\n'+'乙'*400+'\n')

    def test_heading_and_cross_page_table_parents(self):
        table = '<table>\n\n<tr><td>(20)</td></tr>\n \t\n</table>\n'
        doc = self.check_document(run('前文。\n\n'+table+'接次頁\n'
            '<!-- Page: 2330_2025_P16 -->\n承前頁\n'+table+'後文。\n', 'parent_child').document)
        self.assertTrue(any(p['node_type']=='table_parent' for p in doc['parents']))
        self.assertTrue(any(p['node_type']=='heading_parent' for p in doc['parents']))
        self.assertIn('<tr><td>(20)</td></tr>', content_body(doc['chunks'][1]))

    def test_source_mapping_crlf_cr_unicode_space_and_no_final_newline(self):
        source = '\r\n甲 乙\r\n\t \r\n丙\r\u3000\r丁'
        doc = {'chunks': [{'content': source, 'source_spans': [
            {'start': 0, 'end': len(source), 'pages': [1]}]}], 'parents': []}
        remove_blank_lines(doc, source)
        chunk = doc['chunks'][0]
        self.assertEqual(chunk['content'], '甲 乙\r\n丙\r丁')
        self.assertEqual(''.join(source[s['start']:s['end']] for s in chunk['source_spans']), chunk['content'])
        removed = doc['removed_blank_line_spans']
        self.assertEqual(sum(s['end']-s['start'] for s in removed)+len(chunk['content']), len(source))


if __name__ == '__main__':
    unittest.main()
