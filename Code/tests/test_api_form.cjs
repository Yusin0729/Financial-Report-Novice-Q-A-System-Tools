// 模擬DOM與同來源HTTP，操作真實共用表單；不接觸真實金鑰／服務。
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const assets=path.join(__dirname,'../functions/web_ui'),nodes=new Map(),events=[],requests=[];
class Element{
  constructor(tag='div'){this.tag=tag;this.children=[];this._value='';this.listeners={};}
  get options(){return this.children;}
  get value(){return this._value;}
  set value(v){this._value=v;}
  append(...items){this.children.push(...items);if(this.tag==='select'&&!this._value&&this.children.length)this._value=this.children[0].value;}
  replaceChildren(...items){this.children=[];this._value='';this.append(...items);}
  addEventListener(name,fn){this.listeners[name]=fn;}
  showModal(){this.open=true;}
  close(){this.open=false;this.listeners.close?.();}
  set innerHTML(html){this.content=html;}
}
function mount(html){for(const match of html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"[^>]*>/g)){nodes.set(match[2],new Element(match[1]));}for(const match of html.matchAll(/<select[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){const select=nodes.get(match[1]);for(const option of match[2].matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g)){const node=new Element('option');node.value=option[1];node.textContent=option[2];select.append(node);}}}
let data={profiles:[],credentials:[],model_suggestions:{embedding:{voyage:['voyage-finance-2']},rerank:{voyage:['rerank-3-lite']},answer:{gemini:['gemini-3.1-flash-lite'],openai:[]}}};
const clone=()=>JSON.parse(JSON.stringify(data));
const document={getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag),querySelector:()=>({content:'fake-token'}),body:{append:mount}};
const window={dispatchEvent:event=>events.push(event.detail)};
const context=vm.createContext({document,window,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},confirm:()=>true,alert:message=>{throw Error(message);},fetch:async(url,options)=>{
  if(url==='/api-settings.html')return {ok:true,text:async()=>fs.readFileSync(path.join(assets,'api-settings.html'),'utf8')};
  assert.equal(url,'/api/api-settings');assert.equal(options.method,'POST');assert.equal(options.headers['X-App-Token'],'fake-token');
  const body=JSON.parse(options.body);requests.push(body);
  if(body.action==='add'){data.credentials=[{id:'key1',name:body.name,provider:body.provider,configured:true,deletable:true}];data.profiles=[{id:'profile1',name:body.name,purpose:body.purpose,provider:body.provider,model:body.model,credential_id:'key1',configured:true}];}
  if(body.action==='delete-key'){data.profiles=[];data.credentials=[];}
  return {ok:true,json:async()=>clone()};
}});
vm.runInContext(fs.readFileSync(path.join(assets,'api-settings.js'),'utf8'),context);
const get=id=>nodes.get(id);
(async()=>{
  await vm.runInContext('openApiSettings()',context);
  assert(get('api-settings-dialog').open);
  get('api-setting-purpose').value='answer';get('api-setting-purpose').onchange();
  get('api-setting-provider').value='openai';get('api-setting-provider').onchange();
  get('api-setting-name').value='GPT測試';get('api-setting-model').value='gpt-test-only';get('api-setting-key').value='FAKE-KEY-DO-NOT-ECHO';
  await get('api-settings-form').onsubmit({preventDefault(){}});
  const sent=requests.find(r=>r.action==='add');assert.equal(sent.provider,'openai');assert.equal(sent.model,'gpt-test-only');assert.equal(sent.api_key,'FAKE-KEY-DO-NOT-ECHO');
  assert.equal(get('api-setting-key').value,'');assert.equal(get('api-settings-save').disabled,false);
  assert(!JSON.stringify(events).includes('FAKE-KEY-DO-NOT-ECHO'));
  get('api-setting-credential').value='key1';get('api-setting-credential').onchange();assert.equal(get('api-setting-key').required,false);assert.equal(get('api-new-key-row').hidden,true);
  const deleteButton=get('api-credential-list').children[0].children[1];await deleteButton.onclick();
  assert.equal(events.at(-1).profiles.length,0);assert.equal(events.at(-1).credentials.length,0);
  get('api-setting-key').value='FAKE-UNSAVED';get('api-settings-close').onclick();assert.equal(get('api-setting-key').value,'');assert.equal(get('api-settings-dialog').open,false);
  console.log('PASS：共用API表單可選GPT、保存／共用金鑰、刪除並發佈選單更新；秘密不回傳且關閉清空輸入。');
})().catch(error=>{console.error(error);process.exitCode=1;});
