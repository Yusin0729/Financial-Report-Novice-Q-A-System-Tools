// 合成DOM：預覽與提交只含來源及重排設定，不重送Excel或要求embedding。
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node{constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.checked=false;this.disabled=false;this.value='';this.hidden=false;}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=[...v];}}
const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
const collect=n=>[n,...n.children.flatMap(collect)];
const document={querySelectorAll:selector=>collect($('saved-rerank-questions')).filter(n=>n.dataset.savedRerankId&&(!selector.includes(':checked')||n.checked))};
let submitted=null,alert=null,called=0;
const state={busy:false,workspaceBusy:false};
const source={source_run:'qa_test',source_sha256:'a'.repeat(64),retrieve_k:50,batch:true,valid_count:1,rows:[{ID:'1',Question:'問題',candidate_count:40},{ID:'2',Question:'失敗',error:'無候選'}]};
const window={addEventListener(){}};
const context={window,$,state,document,URLSearchParams,location:{hash:'#history'},el:(tag,text)=>{const n=new Node(tag);n.textContent=text;return n;},api:async()=>{called++;return source;},profileOptions:n=>{n.value='profile';},apiReadyProfiles:()=>[],rerankProfiles:()=>[],start:async data=>{submitted=data;state.busy=true;},alertMessage:s=>{alert=s;}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../functions/web/static/saved-rerank.js'),'utf8'),context);
(async()=>{
 await window.savedRerankUI.select('qa_test');assert.equal(called,1);
 const checks=document.querySelectorAll('[data-saved-rerank-id]');assert.equal(checks.length,2);assert.equal(checks[1].disabled,true);
 assert.equal($('saved-rerank-start').disabled,false);assert.equal($('saved-rerank-charts').checked,false);
 $('saved-rerank-count').value='10';$('saved-rerank-charts').checked=true;
 await $('saved-rerank-start').onclick();assert.equal(submitted.action,'rerank-report');assert.deepEqual([...submitted.ids],['1']);
 assert.equal(submitted.generate_charts,true);assert.equal(submitted.source_sha256,source.source_sha256);
 for(const k of ['backend','collection','question','workbook_base64','embedding_profile'])assert.equal(submitted[k],undefined);
 window.savedRerankUI.syncBusy();assert.equal($('saved-rerank-start').disabled,true);
 submitted=null;state.busy=false;$('saved-rerank-count').value='51';await $('saved-rerank-start').onclick();assert.equal(submitted,null);assert.ok(alert.includes('來源召回數'));
 console.log('PASS：舊報告預覽、可用題勾選、重排專用提交、圖表選項與忙碌狀態。');
})().catch(e=>{console.error(e);process.exitCode=1;});
