import unittest
from unittest.mock import Mock,patch
from dataclasses import replace
from Code_2.config.qa import QASettings
from Code_2.functions.qa.services import GeminiAnswerer
from Code_2.functions.qa.answers import validate_answer,render_answer
from Code_2.functions.qa.openai_answer import OpenAIAnswerer
from Code_2.tests.test_qa import source

class DirectTextTests(unittest.TestCase):
    def test_gemini_calculates_in_text_without_json_or_program_calculation(self):
        answerer=GeminiAnswerer('unused',QASettings())
        text='平均 = (100 + 200) / 2 = 150 百萬元。[S1]'
        answerer.post=Mock(side_effect=[{'totalTokens':50},{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}]}])
        answer,_=answerer.answer('平均？',[source()])
        with patch('Code_2.functions.qa.answers.calculate',side_effect=AssertionError('must not compute')):
            self.assertEqual(validate_answer(answer,[source()])['text'],text)
        self.assertEqual(render_answer({'status':'answered','answer':answer,'evidence':[source()]}),text)
        body=answerer.post.call_args_list[-1].args[1]
        self.assertNotIn('responseSchema',body['generationConfig'])
        self.assertNotIn('responseMimeType',body['generationConfig'])

    def test_openai_accepts_plain_text_that_is_not_json(self):
        a=OpenAIAnswerer('unused',replace(QASettings(),answer_model='gpt-test-only'))
        a.post=Mock(side_effect=[{'input_tokens':10},{'status':'completed','output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'結果為 3.44%。'}]}]}])
        answer,_=a.answer('結果？',[source()])
        self.assertEqual(answer['text'],'結果為 3.44%。')
        self.assertNotIn('text',a.post.call_args_list[-1].args[1])

    def test_empty_direct_answer_is_still_rejected(self):
        with self.assertRaises(ValueError):validate_answer({'format':'markdown','text':' '},[])

if __name__=='__main__':unittest.main()
