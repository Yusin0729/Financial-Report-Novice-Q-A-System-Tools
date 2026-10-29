/* EXPERIMENT_ONLY：舊報告候選重排；移除此入口、後端action及preview路由即可停用。 */
'use strict';
window.savedRerankUI=(()=>{
 let source=null,version=0;
 const panel=$('saved-rerank-panel');
 function syncBusy(){$('saved-rerank-start').disabled=!source?.valid_count||state.busy||state.workspaceBusy;}
 function profiles(){profileOptions($('saved-rerank-profile'),rerankProfiles());}
 async function select(run){
  const current=++version;source=null;panel.hidden=false;
  $('saved-rerank-source').textContent=run;
  $('saved-rerank-status').textContent='讀取候選全文與來源中…';
  $('saved-rerank-start').disabled=true;$('saved-rerank-questions').replaceChildren();
  try{
   const data=await api('/api/rerank-source?'+new URLSearchParams({run,candidate_unit:'child'}));
   if(current!==version)return;source=data;profiles();
   $('saved-rerank-charts-field').hidden=!data.batch;
   $('saved-rerank-charts').checked=false;$('saved-rerank-all').checked=true;
   $('saved-rerank-source').textContent=`${run} · ${data.index_name||'來源索引'} · 可用 ${data.valid_count}/${data.rows.length} 題`;
   for(const row of data.rows){const label=el('label',undefined,'checkbox'),check=el('input');check.type='checkbox';check.dataset.savedRerankId=row.ID;check.disabled=!!row.error;check.checked=!row.error;label.append(check,el('span',`ID ${row.ID} · ${row.Question} · ${row.error||row.candidate_count+'個子項候選'}`));$('saved-rerank-questions').append(label);}
   $('saved-rerank-status').textContent=data.valid_count?'候選已讀取；請選重排序設定與保留數量。':'此報告沒有可重排序的完整候選。';
   $('saved-rerank-start').disabled=!data.valid_count||state.busy||state.workspaceBusy;
  }catch(e){if(current===version){$('saved-rerank-status').textContent=e.message;$('saved-rerank-start').disabled=true;}}
 }
 $('saved-rerank-all').onchange=e=>document.querySelectorAll('[data-saved-rerank-id]').forEach(n=>{if(!n.disabled)n.checked=e.target.checked;});
 $('saved-rerank-start').onclick=async()=>{
  if(!source)return alertMessage('請先選擇可重排序的舊報告。');
  const ids=[...document.querySelectorAll('[data-saved-rerank-id]:checked')].map(n=>n.dataset.savedRerankId);
  const profile=$('saved-rerank-profile').value,k=Number($('saved-rerank-count').value);
  if(!ids.length)return alertMessage('請至少勾選一題。');
  if(!profile)return alertMessage('請選擇BGE或Voyage重排序設定。');
  if(!Number.isInteger(k)||k<1||k>source.retrieve_k)return alertMessage('保留數量須介於1與來源召回數之間。');
  await start({action:'rerank-report',candidate_unit:'child',source_run:source.source_run,source_sha256:source.source_sha256,ids,rerank_profile:profile,evidence_k:k,generate_charts:source.batch&&$('saved-rerank-charts').checked});
  if(state.busy)location.hash='query';
 };
 window.addEventListener('api-settings-changed',profiles);
 return {select,syncBusy};
})();
