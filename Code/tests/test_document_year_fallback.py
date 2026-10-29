"""所有chunk包含檔名年度，保留表頭年度及正文／embedding內容；不呼叫模型。"""
import unittest
from test_hierarchical_modes import run
from functions.content_context import content_body
from functions.chunking.table_metadata import with_document_year
from Code.functions.embedding.prepare import prepare_document
from Code.functions.embedding.load_prepared import validate_prepared

class DocumentYearFallbackTests(unittest.TestCase):
    def test_missing_years_gain_document_source_but_existing_years_are_preserved(self):
        years,sources=with_document_year([],[],'2024')
        self.assertEqual(years,[2024])
        self.assertEqual(sources,[{'raw':'2024','source':'document_year_fallback','years':[2024]}])
        found=[2022,2023];provenance=[{'raw':'112年度','source':'table_header_row_1','years':[2023]}]
        years,sources=with_document_year(found,provenance,'2024')
        self.assertEqual(years,[2022,2023,2024])
        self.assertEqual(sources[:-1],provenance)
        self.assertEqual(sources[-1],{'raw':'2024','source':'document_year_included','years':[2024]})
        self.assertEqual(with_document_year(years,sources,'2024'),(years,sources))
        self.assertEqual(found,[2022,2023])

    def test_all_modes_trace_text_and_table_fallback_without_embedding_year_prefix(self):
        body='甲'*1000+'。\n<table><tr><th>金額</th></tr><tr><td>123</td></tr></table>\n乙文。\n'
        for mode,limit in [('original',700),('parent_child',700),('parent_child',250)]:
            with self.subTest(mode=mode,limit=limit):
                doc=run(body,mode,recursive_threshold=limit).document
                self.assertEqual({c["content_type"] for c in doc["chunks"]},{"text","table"})
                validate_prepared(prepare_document(doc,input_sha256='a'*64))
                for node in doc['chunks']+doc['parents']:
                    self.assertEqual(node['years'],[2025])
                    self.assertTrue(any(s['source']=='document_year_fallback' and s['years']==[2025] for s in node['year_sources']))
                    self.assertNotIn('年度：',node['content_prefix'])
                    self.assertNotIn('2025',content_body(node))

    def test_explicit_table_year_is_preserved_and_file_year_is_added(self):
        table='<table><tr><th>112年度</th></tr><tr><td>123</td></tr></table>\n'
        for mode in ['original','parent_child']:
            doc=run(table,mode).document
            for node in doc['chunks']+doc['parents']:
                self.assertEqual(node['years'],[2023,2025])
                self.assertTrue(any(s['source']=='document_year_included' and s['years']==[2025] for s in node['year_sources']))
                self.assertTrue(any(s['source'].startswith('table_') and s['years']==[2023] for s in node['year_sources']))
                self.assertNotIn('年度：',node['content_prefix'])
                self.assertNotIn('2025',content_body(node))
