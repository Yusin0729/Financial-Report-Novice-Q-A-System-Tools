"""建庫脈絡獨立於切法；合成來源，無模型API。"""
import unittest
from copy import deepcopy
from itertools import product
from test_hierarchical_modes import run
from Code.functions.embedding.prepare import prepare_document
from Code.functions.embedding.load_prepared import validate_prepared
from Code.functions.embedding.context_modes import MODES
from functions.content_context import content_body


class EmbeddingContextTests(unittest.TestCase):
    def test_all_modes_keep_source_and_metadata_for_both_chunkers(self):
        source = ('## (一)測試小標題\n## 文字說明如下：\n內文金額123。\n'
                  '## 114年度表格說明如下：\n'
                  '<table><tr><th>114年度</th></tr><tr><td>(100)</td></tr></table>\n')
        for strategy in ('original','parent_child'):
            doc = run(source,strategy).document
            legacy = prepare_document(doc,input_sha256='a'*64)
            for text,table in product(MODES,repeat=2):
                modes={'text':text,'table':table}
                doc=run(source,strategy,text_embedding_mode=text,table_embedding_mode=table).document
                before=deepcopy(doc)
                prepared=prepare_document(doc,input_sha256='a'*64)
                validate_prepared(prepared)
                self.assertEqual(doc,before)
                self.assertEqual(prepared['embedding_context_modes'],modes)
                from Code.functions.chunking.filenames import validate_chunk_filename, chunk_record_prefix
                suffix='_700' if strategy=='parent_child' else ''
                filename=f'2025_2330_chunk{suffix}_text-{text}_table-{table}.json'
                match=validate_chunk_filename(filename,doc,'2330')
                self.assertIn(f'text-{text}_table-{table}',chunk_record_prefix(match))
                self.assertEqual([content_body(c) for c in prepared['parents']],
                                 [content_body(c) for c in legacy['parents']])
                for item, old in zip(prepared['chunks'],legacy['chunks']):
                    self.assertEqual(item['metadata'],old['metadata'])
                    self.assertEqual(content_body(item['original_chunk']),content_body(old['original_chunk']))
                    self.assertEqual(item['original_chunk']['source_spans'],old['original_chunk']['source_spans'])
                    mode=modes[item['original_chunk']['content_type']]
                    value=item['embedding_text']
                    self.assertNotIn('Main_Section：',value)
                    self.assertNotIn('股票代號：',value)
                    if mode=='body':
                        self.assertNotIn('說明：',value)
                        self.assertNotIn('Sub_Section：',value)
                    elif mode=='description':
                        self.assertIn('說明如下：',value)
                        self.assertNotIn('Note_Title：',value)
                    else:
                        self.assertNotIn('Sub_Section：',value)
                        self.assertIn(' > ',value)
                        self.assertNotIn('Note_Title：',value)
                        self.assertIn('測試小標',value)
                    if item['original_chunk']['content_type']=='table':
                        self.assertIn('114年度',value)
                        self.assertIn('(100)',value)

    def test_invalid_modes_and_modified_text_are_rejected(self):
        doc=run('內文。\n',text_embedding_mode='body',table_embedding_mode='body').document
        for modes in ({'text':'body'}, {'text':'bad','table':'full'}):
            with self.assertRaises(ValueError):
                prepare_document(doc,input_sha256='a'*64,embedding_context_modes=modes)
        prepared=prepare_document(doc,input_sha256='a'*64,embedding_context_modes={'text':'body','table':'body'})
        prepared['chunks'][0]['embedding_text']='額外加入錯誤標籤'
        with self.assertRaises(ValueError):validate_prepared(prepared)
