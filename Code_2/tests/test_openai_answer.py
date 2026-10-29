"""GPT適配與可略過重排：所有API回覆均為模擬。"""
import json
import unittest
import urllib.error
from dataclasses import replace
from unittest.mock import Mock,patch
from Code_2.config.qa import QASettings
from Code_2.config.embedding import Settings
from Code_2.functions.qa.openai_answer import OpenAIAnswerer,json_schema
from Code_2.functions.qa.pipeline import ask
from Code_2.functions.qa.answers import render_qa_report
from Code_2.tests.test_qa import source,response,INDEX,raw_row


class OpenAIAnswerTests(unittest.TestCase):
    def answerer(self,**changes):
        a=OpenAIAnswerer('FAKE-KEY',replace(QASettings(),answer_provider='openai',answer_model='gpt-test-only'))
        result={'status':'completed','model':'gpt-test-only','usage':{'input_tokens':100,'output_tokens':20,'total_tokens':120},
                'output':[{'type':'message','role':'assistant','status':'completed',
                           'content':[{'type':'output_text','text':json.dumps(response())}]}]}
        result.update(changes)
        a.post=Mock(side_effect=[{'input_tokens':100},result])
        return a

    def test_count_full_payload_strict_schema_and_no_storage(self):
        a=self.answerer();answer,usage=a.answer('原題',[source()])
        self.assertEqual(answer,response());self.assertEqual(usage['usage']['output_tokens'],20)
        count=a.post.call_args_list[0].args;generate=a.post.call_args_list[1].args
        self.assertEqual(count[0],'responses/input_tokens');self.assertEqual(generate[0],'responses')
        self.assertIn(source()['text'],count[1]['input'])
        for key in ('model','instructions','input','text'): self.assertEqual(count[1][key],generate[1][key])
        self.assertTrue(count[1]['text']['format']['strict'])
        self.assertFalse(count[1]['text']['format']['schema']['additionalProperties'])
        self.assertFalse(generate[1]['store']);self.assertEqual(generate[1]['truncation'],'disabled')
        self.assertNotIn('FAKE-KEY',json.dumps(generate[1]))

    def test_over_budget_does_not_generate(self):
        a=self.answerer();a.post=Mock(return_value={'input_tokens':32001})
        with self.assertRaises(ValueError): a.answer('原題',[source()])
        self.assertEqual(a.post.call_count,1)

    def test_refusal_incomplete_bad_json_or_multiple_text_rejected(self):
        outputs=[{'status':'incomplete'}, {'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'refusal','refusal':'fake'}]}]},
                 {'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'bad-json'}]}]}]
        for change in outputs:
            with self.assertRaises(ValueError): self.answerer(**change).answer('原題',[source()])

    def test_http_error_no_retry_no_key_or_body(self):
        opener=Mock();opener.open.side_effect=urllib.error.HTTPError('url',429,'PRIVATE BODY',{},None)
        a=OpenAIAnswerer('FAKE-SECRET',QASettings(),opener)
        with self.assertRaises(RuntimeError) as error: a.post('responses',{})
        self.assertIn('429',str(error.exception));self.assertNotIn('PRIVATE',str(error.exception));self.assertNotIn('FAKE-SECRET',str(error.exception))
        self.assertEqual(opener.open.call_count,1)

    def test_skip_rerank_reads_only_answer_key_and_validates_answer(self):
        provider=Mock(profile=INDEX['signature']['model']);provider.embed.return_value=[[1.,0.]]
        store=Mock(collection_name=INDEX['collection']);store.search.return_value=[raw_row()]
        answerer=Mock();answerer.answer.return_value=(response(),{'usage':{'total_tokens':10}})
        with patch('Code_2.functions.qa.pipeline.service_key',return_value='FAKE') as key,patch('voyageai.Client') as voyage,patch('Code_2.functions.qa.openai_answer.OpenAIAnswerer',return_value=answerer):
            result=ask('原題',Settings(),index=INDEX,qa=replace(QASettings(),answer_provider='openai',answer_model='gpt-test-only',rerank_enabled=False),provider_factory=lambda *a:provider,store_factory=lambda *a,**k:store)
        self.assertEqual(result['status'],'answered');self.assertEqual(result['completed_stages'],['query_embedding','retrieval','answer'])
        self.assertTrue(result['rerank_skipped']);self.assertNotIn('rerank',result)
        self.assertEqual([call.args[1] for call in key.call_args_list],['OPENAI_API_KEY']);voyage.assert_not_called()
        report=render_qa_report({**result,'created_at':'2026-10-25T12:00:00+08:00'})
        self.assertIn('略過',report);self.assertIn('GPT',report);self.assertNotIn('Gemini',report)


if __name__=='__main__': unittest.main()
