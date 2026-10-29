"""表格候選標記的0／1欄位、父子範圍及下游保真。"""
import unittest
from copy import deepcopy
from test_chunks import convert, tagged, page
from test_table_parents import table
from test_full_table_blocks import FULL
from functions.chunking.chunks import validate_chunk_document
from Code_2.functions.embedding.prepare import validate_document, prepare_document
from Code_2.functions.embedding.metadata import build_metadata


class TableCompletenessTests(unittest.TestCase):
    def test_normal_table_is_one_and_text_has_no_table_field(self):
        result = convert(tagged(page(15) + '## 一、公司沿革\n正文。\n' + table()))
        for item in result.document['chunks'] + result.document['parents']:
            if item['content_type'] == 'table':
                self.assertEqual(item['table_completeness'], 1)
            else:
                self.assertNotIn('table_completeness', item)
        self.assertIn('<!-- table_completeness: 1 -->', result.markdown)
        prepared = prepare_document(result.document, input_sha256='b' * 64)
        item = next(c for c in prepared['chunks'] if c['metadata']['content_type'] == 'table')
        self.assertEqual(item['metadata']['table_completeness'], 1)
        self.assertEqual(item['original_chunk']['table_completeness'], 1)

    def test_candidate_table_is_zero_in_parent_child_and_markdown(self):
        result = convert(tagged(page(15) + '## 一、公司沿革\n' + FULL))
        for item in result.document['chunks'] + result.document['parents']:
            self.assertEqual(item['table_completeness'], 0)
            meta = build_metadata(item, stock_code='2330', report_year=2025)
            self.assertEqual(meta['table_completeness'], 0)
        self.assertIn('<!-- table_completeness: 0 -->', result.markdown)
        validate_document(result.document)

    def test_mixed_parent_and_page_children_use_their_own_content(self):
        raw = page(15) + '## 一、公司沿革\n' + table() + '接次頁\n' + page(16) + FULL
        doc = convert(tagged(raw)).document
        self.assertEqual(len(doc['parents']), 1)
        self.assertEqual(doc['parents'][0]['table_completeness'], 0)
        self.assertEqual([c['table_completeness'] for c in doc['chunks']], [1, 0])
        validate_document(doc)

    def test_invalid_values_and_wrong_marker_claim_are_rejected(self):
        doc = convert(tagged(page(15) + '## 一、公司沿革\n' + FULL)).document
        for value in (1, True, '0', None, -1):
            altered = deepcopy(doc)
            altered['chunks'][0]['table_completeness'] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'table_completeness'):
                    validate_chunk_document(altered)
                with self.assertRaisesRegex(ValueError, 'table_completeness'):
                    validate_document(altered)

    def test_old_chunks_without_field_still_accepted_by_code2(self):
        doc = convert(tagged(page(15) + '## 一、公司沿革\n' + table())).document
        for item in doc['chunks'] + doc['parents']:
            item.pop('table_completeness')
        validate_document(doc)


if __name__ == '__main__':
    unittest.main()
