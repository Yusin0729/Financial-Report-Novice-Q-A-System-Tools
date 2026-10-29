import unittest
from copy import deepcopy
from functions.content_context import context_prefix,legacy_context_prefix,content_body,heading_text,add_context
from Code.functions.embedding.context_modes import embedding_text

class PathPrefixTests(unittest.TestCase):
    def chunk(self,kind='table'):
        return {'doc_id':'2024Q4_2330_Financial_Report','years':[2024],
                'main_section':'合併財務報告附註','sub_section':'二一、營業收入',
                'note_title':['(一)客戶合約收入之細分'],'title':[],
                'content_type':kind,'directions':[{'text':'113年度技術平台別'}],
                'table_context':'113年度技術平台別','content':'原文113年度100。'}

    def test_exact_path_for_both_types_and_modes(self):
        for kind in ('text','table'):
            c=self.chunk(kind);before=deepcopy(c)
            self.assertEqual(context_prefix(c),'營業收入 > 客戶合約收入之細分 > 技術平台別\n')
            self.assertEqual(context_prefix(c,mode='description'),'技術平台別\n')
            self.assertEqual(context_prefix(c,mode='body'),'')
            self.assertEqual(c,before)
            add_context(c,'full');self.assertEqual(content_body(c),before['content'])
            self.assertEqual(c['sub_section'],before['sub_section']);self.assertEqual(c['years'],[2024])

    def test_heading_number_cleanup_retains_semantic_digits(self):
        for source,target in [('二一 、 營業收入','營業收入'),('（ 一 ）客戶合約收入','客戶合約收入'),
                              ('2. 客戶資訊','客戶資訊'),('A. 地區','地區'),
                              ('IFRS 16 租賃','IFRS 16 租賃'),('3奈米製程','3奈米製程'),('2024年度營收','2024年度營收')]:
            self.assertEqual(heading_text(source),target)

    def test_empty_and_duplicate_items(self):
        c=self.chunk();c.update(sub_section='',note_title=[],table_context='')
        self.assertEqual(context_prefix(c),'')
        c.update(sub_section='二一、營業收入',note_title=['(一)營業收入'],table_context='營業收入')
        self.assertEqual(context_prefix(c),'營業收入\n')

    def test_legacy_prefix_keeps_old_embedding_and_is_validated(self):
        c=self.chunk();c['embedding_context_mode']='full';c['content_prefix']=legacy_context_prefix(c)
        c['content']=c['content_prefix']+c['content']
        self.assertEqual(content_body(c),'原文113年度100。')
        c['content']='wrong'+c['content']
        with self.assertRaises(ValueError):content_body(c)

    def test_unknown_format_rejected(self):
        c=self.chunk();add_context(c,'full');c['content_prefix_format']='bad'
        with self.assertRaises(ValueError):content_body(c)

if __name__=='__main__':unittest.main()
