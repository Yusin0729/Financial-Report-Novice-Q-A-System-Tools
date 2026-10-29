// 網頁狀態契約：用暫存DOM與模擬HTTP驗證，不執行財報轉換。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let html = fs.readFileSync(path.join(__dirname, '../functions/web_ui/index.html'), 'utf8');
for (const [name, value] of Object.entries({TOKEN:'test',POLL:1500,OCR_SCALE:3,TABLE_MODE:'accurate',
  CHUNK_MODE:'original',PARENT_LIMIT:1500,RECURSIVE_THRESHOLD:700,CHILD_TARGET:300,
  PARENT_SLIDER_MAX:3000,THRESHOLD_SLIDER_MAX:1500,CHILD_SLIDER_MAX:1000,OCR_CHECKED:'checked'})) {
  html = html.replaceAll(`__${name}__`, String(value));
}
class Element {
  constructor() {this.value='';this.hidden=false;this.disabled=false;this.open=false;this.style={};
    this.listeners={};this.children=[];this.dataset={};this.classList={toggle(){}};}
  get options(){return this.children;}
  addEventListener(name, fn){this.listeners[name]=fn;}
  append(...items){this.children.push(...items);}
  replaceChildren(){this.children=[];}
  setAttribute(name,value){this[name]=value;}
}
const elements = new Map();
for (const match of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
  const e = new Element();const tag = match[0];
  e.value = tag.match(/\bvalue="([^"]*)"/)?.[1] ?? '';
  e.max = tag.match(/\bmax="([^"]*)"/)?.[1];
  e.hidden = /\bhidden\b/.test(tag);e.checked = /\bchecked\b/.test(tag);
  elements.set(match[1],e);
}
elements.get('selectionFilter').value='all';
elements.get('indexAction').value='new';elements.get('indexName').value='介面測試索引';elements.get('pdfParser').value='docling';
elements.get('embeddingMode').value='original';elements.get('embeddingBackend').value='bge';
const document = {querySelector:()=>null,getElementById:id=>elements.get(id),querySelectorAll:()=>[],
  createElement:()=>new Element(),createTextNode:value=>value};
let state = {state:'idle',busy:false,results:[]};
let submitted,stopRequest;
const data = Object.fromEntries(['raw','processed','tagged','chunk','embed'].map(stage=>[stage,
  [{id:'first/file1',name:'file1'},{id:'second/nested/file2',name:'file2'}]]));
data.embed=[{id:'Financial_chunk_20261025_12-00-00/original/2025_2330_chunk.json'},{id:'Financial_chunk_20261025_12-00-00/parent_child/2025_2330_chunk.json'}];
const handlers={};const window={addEventListener:(name,fn)=>{handlers[name]=fn;},dispatchEvent:event=>handlers[event.type]?.(event)};
const context=vm.createContext({window,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},document,console,setInterval(){},SelectionTree:require('../functions/web_ui/selection.js'),
  fetch:async(url,options)=>({ok:true,json:async()=>{
    if(url.endsWith('/catalog'))return data;
    if(url.endsWith('/api-settings'))return {profiles:[],credentials:[],model_suggestions:{}};
    if(url.endsWith('/database'))return {indexes:[]};
    if(url.endsWith('/state'))return state;
    if(url.endsWith('/cancel')){stopRequest=JSON.parse(options.body);state.stop_requested=true;return {};}
    if(url.endsWith('/run')){submitted=JSON.parse(options.body);
      state={state:'running',stage:submitted.stage,busy:true,total:2,completed:0,results:[]};return {};}
    return {};
  }})});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../functions/web_ui/api-settings.js'),'utf8'),context);
vm.runInContext([...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n'),context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../functions/web_ui/database.js'),'utf8'),context);
const get=id=>elements.get(id);
const execute=code=>vm.runInContext(code,context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('ocr').checked,true);
  assert.equal(get('statusPanel').hidden,true);
  assert.equal(get('cancel').hidden,true);
  execute("changeStage('processed')");
  assert.equal(get('pdfOptions').hidden,true);
  assert.equal(get('chunkOptions').hidden,true);
  execute("changeStage('tagged')");
  assert.equal(get('ocrOption').hidden,true);
  execute("changeStage('chunk')");
  assert.equal(get('chunkOptions').hidden,false);
  assert.equal(get('chunkAdvanced').open,false);
  execute("selectChunkMode('parent_child')");
  assert.equal(get('parentLimitParameter').hidden,true);
  assert.equal(get('childTargetParameter').hidden,true);
  assert(get('chunkModeHelp').textContent.includes('###'));
  execute("selectChunkMode('original')");
  assert.equal(get('parentLimitParameter').hidden,true);
  assert.equal(get('childTargetParameter').hidden,true);
  get('parentLimit').value='4000';get('parentLimit').listeners.input();
  get('recursiveThreshold').value='2000';get('recursiveThreshold').listeners.input();
  get('childTarget').value='1200';get('childTarget').listeners.input();
  assert.equal(get('parentLimit').value,'4000');
  assert.equal(get('parentRange').value,'3000');
  assert.equal(get('parentOver').hidden,false);
  get('childRange').value='600';get('childRange').listeners.input();
  assert.equal(get('childTarget').value,'600');
  get('childTarget').value='1200';get('childTarget').listeners.input();
  get('search').value='first';get('search').oninput();get('selectAll').onclick();
  await get('run').onclick();
  assert.equal(submitted.ids.length,2); // 全選包含篩選外及子資料夾。
  assert.equal(submitted.parent_limit,4000);
  assert.equal(submitted.recursive_threshold,2000);
  assert.equal(submitted.child_target,1200);
  assert.equal(get('cancel').hidden,false);
  assert.equal(get('parentRange').disabled,true);
  state={...state,state:'completed',busy:false,completed:2,output:'test-output',results:[]};
  await execute('poll()');
  assert.equal(get('cancel').hidden,true);
  assert.equal(get('openOutput').hidden,false);
  assert.equal(get('progress').hidden,true);
  execute("changeStage('processed')");
  assert.equal(get('openOutput').hidden,true);
  state={state:'running',stage:'embed',busy:true,completed:0,total:2,results:[],vector_job_id:'a'.repeat(32),embedding_files:['batch/2024_2330_chunk_700.json','batch/2025_2330_chunk_700.json']};
  await execute('poll()');
  assert.equal(get('embeddingStop').hidden,false);
  assert.equal(get('embeddingStopButton').disabled,false);
  get('embeddingStopAfter').value=state.embedding_files[0];
  await get('embeddingStopButton').onclick();
  assert.equal(stopRequest.after_file,'batch/2024_2330_chunk_700.json');
  assert.equal(get('embeddingStopButton').disabled,true);
  state={state:'stopped',stage:'embed',busy:false,completed:1,total:2,results:[],skipped:['batch/2025_2330_chunk_700.json']};await execute('poll()');
  assert(get('current').textContent.includes('2025_2330_chunk_700.json'));
 // 不把另一階段的結果按鈕留在本階段。
  execute("changeStage('raw')");get('ocr').checked=false;get('ocr').onchange();
  assert.equal(get('ocrScaleOption').hidden,true);
  state={state:'idle',busy:false,results:[]};await execute('poll()');
  assert.equal(get('statusPanel').hidden,true);
  execute("changeStage('embed')");
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('embeddingOptions').hidden,false);
  assert.equal(get('databasePanel').hidden,false);
  get('embeddingBackend').value='bge';get('selectAll').onclick();
  await get('run').onclick();
  assert.equal(submitted.stage,'embed');assert.equal(submitted.backend,'bge');
  assert.equal(submitted.ids.length,1);assert(submitted.ids[0].includes('/original/'));
  assert.equal(get('cancel').hidden,true);
  state={state:'completed',stage:'embed',busy:false,completed:1,results:[]};await execute('poll()');
  assert.equal(get('openOutput').hidden,true);
  get('embeddingMode').value='parent_child';get('embeddingMode').onchange();get('selectAll').onclick();
  assert.equal(execute('[...selections.embed][0]').includes('/parent_child/'),true);
  execute("publishApiSettings({profiles:[{id:'voyage-test',purpose:'embedding',name:'Voyage測試',model:'voyage-finance-2',configured:true}],credentials:[],model_suggestions:{}})");
  assert(get('embeddingBackend').options.some(o=>o.value==='voyage-test'));
  get('embeddingBackend').value='voyage-test';get('embeddingBackend').onchange();get('embeddingVoyage').checked=true;
  await get('run').onclick();assert.equal(submitted.backend,'voyage');assert.equal(submitted.embedding_profile,'voyage-test');
  state={state:'completed',stage:'embed',busy:false,completed:1,results:[]};await execute('poll()');
  execute("publishApiSettings({profiles:[],credentials:[],model_suggestions:{}})");
  assert.equal(get('embeddingBackend').value,''); // 刪除選中設定後不偷偷切換BGE。
  for(const stage of ['processed','tagged','chunk','embed']) {
    state={state:'completed',stage,busy:false,total:1,completed:1,results:[{name:'test',status:'failed',message:'測試',elapsed_seconds:0.12}]};
    await execute('poll()');
    assert(get('results').children[0].children.some(e=>e.textContent==='執行時間：0.12 秒'));
  }
  assert.equal(execute("runtimeConfigText({runtime_config:{cpu_threads:4,batch_size:2,batch_unit:'chunk'}})"), 'CPU 執行緒設定：4；批次上限：2 chunk／批');
  assert.equal(execute("runtimeConfigText({runtime_config:{cpu_threads:null,batch_size:null}})"), 'CPU 執行緒設定：不適用；批次：不適用');
  assert.equal(execute('durationText(3661)'), '1 小時 1 分 1 秒');
  assert.equal(execute('durationText(undefined)'), '未取得');
  execute("changeStage('embed')");
  get('indexAction').value='batch';get('indexAction').onchange();
  assert.equal(get('embeddingMode').value,'all');
  assert.equal(get('indexNameLabel').hidden,false);
  assert.equal(get('existingIndexLabel').hidden,true);
  get('indexName').value='九組比較';get('embeddingBackend').value='bge';
  get('search').value='';get('selectAll').onclick();
  await get('run').onclick();
  assert.equal(submitted.index_mode,'batch');
  assert.equal(submitted.index_name,'九組比較');
  assert.equal(submitted.ids.length,2); // 可跨original與parent_child一次提交。
  state={state:'completed',stage:'embed',busy:false,total:2,completed:2,results:[],index_groups:[
    {group_number:1,group_total:2,index_group_name:'組一',status:'completed',succeeded:1,total:1},
    {group_number:2,group_total:2,index_group_name:'組二',status:'completed_with_errors',succeeded:0,total:1}]};
  await execute('poll()');
  assert(get('results').children[0].textContent.includes('組一'));
  assert(get('results').children[1].textContent.includes('部分失敗'));
  await get('shutdown').onclick();
  assert.equal(get('statusPanel').hidden,false);
  assert(get('status').textContent.includes('服務已關閉'));
  console.log('PASS：分階段顯示、初始OCR、滑桿同步／超限輸入、實際請求值、全選及工作狀態。');
})().catch(error=>{console.error(error);process.exitCode=1;});
