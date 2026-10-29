/* 原有工作面板的顯示接頭，核心與選取／刪除行為沿用Code。 */
'use strict';
let workspacePage='prepare',previousBusy=false;
function workspaceView(page){workspacePage=page==='database'?'database':'prepare';document.body.dataset.workspacePage=workspacePage;if(workspacePage==='database'&&stage!=='embed')changeStage('embed');else if(workspacePage==='prepare'&&stage==='embed')changeStage('raw');if(workspacePage==='database')$('heading').textContent='建立向量索引';}
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==parent)return;if(event.data?.type==='workspace-page')workspaceView(event.data.page);if(event.data?.type==='api-settings-refresh')refreshApiSettings().catch(fail);});
workspaceView(location.hash.slice(1));
refreshApiSettings().catch(fail);
setInterval(()=>{parent.postMessage({type:'workspace-state',busy:busy||dbWorking},location.origin);if(previousBusy&&!busy&&!dbWorking)parent.postMessage({type:'workspace-finished'},location.origin);previousBusy=busy||dbWorking;},500);

new ResizeObserver(()=>parent.postMessage({type:'workspace-height',height:document.querySelector('main').getBoundingClientRect().height},location.origin)).observe(document.querySelector('main'));
