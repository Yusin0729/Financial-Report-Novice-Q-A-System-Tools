// 畫面證據對應測試，只有合成結果，不呼叫服務。
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Node {constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.classList={add(){},remove(){}};}append(...rows){this.children.push(...rows);}replaceChildren(...rows){this.children=[...rows];}}
const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,new Node('div'));return elements.get(id);};
const document={createElement:tag=>new Node(tag)};
const state={tab:'summary',result:{status:'answered',mode:'answer',backend:'bge',original_question:'合成問題',evidence:[{id:'S1',doc_id:'文件A',page:[65,66],chunk_id:'parent-A',parent_relation:'table',matched_chunk_ids:['child-A'],retrieval_rank:3,retrieval_distance:.12,text:'完整表格 <script>不得執行</script>'}],answer:{claims:[{kind:'quoted',text:'合成事實',citations:[{id:'S1',quote:'逐字引文'}]}],reason:'尚缺另一年度資料'}}};
const labels={answered:'已回答，待核對'};
const app=fs.readFileSync(path.join(__dirname,'../functions/web/static/app.js'),'utf8');
const code=app.slice(app.indexOf('function el('),app.indexOf('function alertMessage('))+app.slice(app.indexOf('function markdown('),app.indexOf('function updateBusy('));
vm.runInNewContext(code+';renderResult();',{state,$,labels,document,URLSearchParams});
function text(node){return node.textContent+' '+node.children.map(text).join(' ');}
const rendered=text($('result-content'));
for(const expected of ['合成事實','文件A','PDF 頁序 65、66','逐字引文','完整表格父項','child-A','尚缺另一年度資料','<script>不得執行</script>'])assert.ok(rendered.includes(expected),expected);
assert.ok(text($('result-context')).includes('合成問題'));
state.tab='rerank';state.result.rerank_skipped=true;
vm.runInNewContext(code+';renderResult();',{state,$,labels,document,URLSearchParams});
assert.ok(text($('result-content')).includes('已略過重排序'));
assert.ok(!text($('result-content')).includes('相關性 undefined'));
console.log('PASS：答案、引用文件／頁序、父子來源、缺少資料及略過重排，文字不執行HTML。');
