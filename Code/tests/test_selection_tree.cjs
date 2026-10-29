/* 真正執行頁面render及事件：資料夾遞迴全選、半勾、搜尋及跨階段保留。 */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const SelectionTree=require('../functions/web_ui/selection.js');
class Element {
  constructor(){this.children=[];this.style={};this.attrs={};this.value='';this.classList={toggle(){}};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this.attrs[k]=v;}
}
const ids=new Map();
const document={getElementById(id){if(!ids.has(id))ids.set(id,new Element());return ids.get(id);},
  createElement(){return new Element();},createTextNode(text){return {textContent:text};},querySelectorAll(){return [];}};
const context=vm.createContext({document,SelectionTree,console});
const html=fs.readFileSync(path.join(__dirname,'../functions/web_ui/index.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace("changeStage('raw');refresh();poll();setInterval(poll,__POLL__);",'');
vm.runInContext(script,context);
vm.runInContext(`data={raw:[{id:'資料夾/a.pdf'},{id:'資料夾/子目錄/b.pdf'},{id:'其他/c.pdf'}],processed:[],tagged:[],chunk:[]};changeStage('raw');`,context);
function all(node){return [node,...(node.children||[]).flatMap(all)];}
function folder(name){return all(ids.get('rows')).find(n=>n.attrs?.['aria-label']==='選取資料夾全部內容 '+name);}
function selected(){return vm.runInContext('JSON.stringify([...selections.raw].sort())',context);}
let box=folder('資料夾');assert.equal(box.checked,false);box.checked=true;box.onchange();
assert.equal(selected(),JSON.stringify(['資料夾/a.pdf','資料夾/子目錄/b.pdf']));
vm.runInContext("selections.raw.delete('資料夾/a.pdf');render();",context);assert.equal(folder('資料夾').indeterminate,true);
ids.get('search').value='a.pdf';ids.get('search').oninput();
box=folder('資料夾');assert.equal(box.indeterminate,true);box.checked=true;box.onchange();
assert.equal(selected(),JSON.stringify(['資料夾/a.pdf','資料夾/子目錄/b.pdf']));
vm.runInContext("changeStage('chunk');changeStage('raw');",context);assert.equal(folder('資料夾').checked,true);
ids.get('clearAll').onclick();assert.equal(selected(),'[]');
ids.get('search').value='a.pdf';ids.get('selectVisible').onclick();assert.equal(selected(),JSON.stringify(['資料夾/a.pdf']));
ids.get('search').value='';ids.get('expandAll').onclick();assert.equal(all(ids.get('rows')).filter(n=>n.type==='checkbox').length,6);
ids.get('collapseAll').onclick();assert.equal(all(ids.get('rows')).filter(n=>n.type==='checkbox').length,2);
assert.equal(SelectionTree.descendants([{id:'A/a.pdf'},{id:'AB/b.pdf'}],'A').length,1);
console.log('PASS: folder render, recursive selection, mixed state, search, collapse and stage persistence');
// 執行真正的頁面按鈕handler，fetch只回傳合成狀態；不啟動模型或HTTP。
(async()=>{
  const calls=[];let cancelled=false;
  context.fetch=async(url,options)=>{
    calls.push({url,body:options.body?JSON.parse(options.body):null});
    if(url==='/api/cancel')cancelled=true;
    return {ok:true,json:async()=>url==='/api/state'?{state:cancelled?'cancelled':'running',busy:!cancelled,
      stage:'raw',results:[],total:1,completed:0}: {ok:true}};
  };
  ids.get('ocrScale').value='2.5';ids.get('tableMode').value='fast';ids.get('ocr').checked=true;
  await vm.runInContext("$('run').onclick()",context);
  const run=calls.find(c=>c.url==='/api/run');assert.equal(run.body.ocr_scale,2.5);assert.equal(run.body.table_mode,'fast');
  assert.equal(ids.get('cancel').disabled,false);
  await vm.runInContext("$('cancel').onclick()",context);
  assert.equal(calls.filter(c=>c.url==='/api/cancel').length,1);assert.equal(ids.get('cancel').disabled,true);
  assert.match(ids.get('status').textContent,/已取消/);
  const text=vm.runInContext("stageTimingText({stage_timings:{stages:{model_load:{seconds:1.25,status:'measured'},ocr:{seconds:null,status:'disabled'}}}})",context);
  assert.match(text,/模型載入：1.25 秒/);assert.match(text,/OCR：未啟用/);assert.match(text,/版面分析：未取得/);
  assert.match(text,/不可直接加總/);
  console.log('PASS: OCR scale, FAST mode, cancel button and timing states');
})().catch(error=>{console.error(error);process.exitCode=1;});
