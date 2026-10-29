"""OpenAI Responses：完整token預檢、嚴格JSON、拒答／截斷停止；不自動重試。"""
import json
import urllib.error
import urllib.request
from Code_2.config.qa import SYSTEM_PROMPT, RESPONSE_SCHEMA
from Code_2.functions.qa.services import NoRedirect


def json_schema(node):
    result={k:json_schema(v) if isinstance(v,dict) else [json_schema(x) if isinstance(x,dict) else x for x in v] if isinstance(v,list) else v for k,v in node.items()}
    if 'type' in result: result['type']=result['type'].lower()
    if result.get('type')=='object': result['additionalProperties']=False
    return result


class OpenAIAnswerer:
    def __init__(self,key,settings,opener=None):
        self.key,self.settings=key,settings
        self.opener=opener or urllib.request.build_opener(NoRedirect())

    def post(self,method,body):
        request=urllib.request.Request('https://api.openai.com/v1/'+method,
            data=json.dumps(body,ensure_ascii=False).encode('utf-8'), method='POST',
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key})
        try:
            with self.opener.open(request,timeout=self.settings.timeout) as response:
                raw=response.read(self.settings.max_response_bytes+1)
            if len(raw)>self.settings.max_response_bytes: raise ValueError('OpenAI回覆超過上限')
            return json.loads(raw)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'OpenAI HTTP {error.code}；未重試或切換模型') from None
        except Exception as error:
            raise RuntimeError(f'OpenAI請求失敗（{type(error).__name__}）；未重試') from None

    def answer(self,question,evidence):
        self.last_attempt={'provider':'openai','model':self.settings.answer_model}
        content=json.dumps({'original_question':question,'evidence':[{k:e[k] for k in ('id','doc_id','page','text')} for e in evidence]},ensure_ascii=False)
        body={'model':self.settings.answer_model,'instructions':SYSTEM_PROMPT,'input':content,
              'text':{'format':{'type':'json_schema','name':'financial_answer','strict':True,'schema':json_schema(RESPONSE_SCHEMA)}}}
        counted=self.post('responses/input_tokens',body)
        tokens=counted.get('input_tokens')
        if type(tokens) is not int or tokens<1: raise ValueError('OpenAI未回傳有效輸入token數，未生成')
        self.last_attempt['input_tokens']=tokens
        if tokens>self.settings.max_input_tokens: raise ValueError('回答輸入超過token預算，未截斷或生成')
        response=self.post('responses',{**body,'max_output_tokens':self.settings.max_output_tokens,'store':False,'truncation':'disabled'})
        self.last_attempt.update(model_version=response.get('model'),usage=response.get('usage',{}))
        if response.get('status')!='completed' or response.get('error'):
            raise ValueError('OpenAI未完整完成，可能拒答或輸出截斷；不交付部分答案')
        parts=[]
        for item in response.get('output',[]):
            if item.get('type')=='reasoning': continue
            if item.get('type')!='message' or item.get('role')!='assistant' or item.get('status')!='completed':
                raise ValueError('OpenAI回傳非預期輸出，已停止')
            for part in item.get('content',[]):
                if part.get('type')!='output_text': raise ValueError('OpenAI拒答或非文字輸出，已停止')
                parts.append(part.get('text',''))
        if len(parts)!=1: raise ValueError('OpenAI回答筆數不符')
        try: answer=json.loads(parts[0])
        except (ValueError,TypeError): raise ValueError('OpenAI回答不是有效JSON') from None
        return answer,dict(self.last_attempt)
