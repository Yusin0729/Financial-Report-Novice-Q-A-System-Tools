// 以真實選單函式驗證模型／模式隔離；無HTTP或模型呼叫。
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
  constructor(){this.children=[];this._value='';this._selected=0;}
  append(n){this.children.push(n);}
  replaceChildren(...nodes){this.children=nodes;this._selected=0;this._value='';}
  get firstChild(){return this.children[0];}
  get options(){return this.children;}
  get value(){return this.children.length?this.children[this._selected]?.value||'':this._value;}
  set value(value){if(this.children.length){const i=this.children.findIndex(x=>x.value===value);this._selected=i<0?0:i;}else this._value=value;}
  set selectedIndex(index){this._selected=index;}
}
const nodes=Object.fromEntries(['query-backend','query-chunk-mode','query-index','query-multiple','open-api-settings'].map(id=>[id,new Element()]));
const context=vm.createContext({window:{addEventListener(){}},openApiSettings(){},document:{getElementById:id=>nodes[id],createElement:()=>new Element()}});
let source=fs.readFileSync(path.join(__dirname,'../functions/web/static/app.js'),'utf8');
source=source.slice(0,source.indexOf('async function refresh()'));
vm.runInContext(source+'\nfunction updateMode(){}',context);
vm.runInContext(`state.metadata={indexes:[
  {backend:'bge',collection:'A',display_name:'自訂索引A',signature:{chunking:{mode:'original'}},doc_ids:['d'],chunk_count:1},
  {backend:'bge',collection:'B',signature:{chunking:{mode:'parent_child'}},doc_ids:['d'],chunk_count:1},
  {backend:'voyage',collection:'C',signature:{chunking:{mode:'original'}},doc_ids:['d'],chunk_count:1},
  {backend:'bge',collection:'D',signature:{},doc_ids:['d'],chunk_count:1}
]};`,context);
for(const [backend,mode,wanted] of [['bge','original','0'],['bge','parent_child','1'],['voyage','original','2'],['bge','legacy','3']]){
  nodes['query-backend'].value=backend;nodes['query-chunk-mode'].value=mode;
  vm.runInContext('queryIndexes()',context);
  assert.equal(nodes['query-index'].options.length,2);
  assert.equal(nodes['query-index'].value,wanted);
  if(wanted==='0')assert.ok(nodes['query-index'].options[1].textContent.includes('自訂索引A'));
}
nodes['query-backend'].value='voyage';nodes['query-chunk-mode'].value='parent_child';
vm.runInContext('queryIndexes()',context);
assert.equal(nodes['query-index'].value,'');
assert.equal(nodes['query-index'].options.length,1);
console.log('PASS：問答三模式共用索引選擇，模型／切法／舊版互相隔離；沒有匹配時不選其他索引。');
