'use strict';
// 金鑰只經同來源POST傳送，不放入網址、localStorage或回應。
let apiSettingsData={profiles:[],credentials:[],model_suggestions:{}};
const apiElement=id=>document.getElementById(id);
const apiPurposes=['embedding','rerank','answer'];
const apiId=(purpose,field)=>'api-'+purpose+'-'+field;
function apiNode(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function profileOptions(select,profiles,label){const old=select.value;select.replaceChildren();const blank=apiNode('option','請選擇設定');blank.value='';select.append(blank);for(const p of profiles){const option=apiNode('option',label?label(p):p.name+' · '+p.model);option.value=p.id;select.append(option);}if(profiles.some(p=>p.id===old))select.value=old;else if(!old&&profiles.length===1)select.value=profiles[0].id;}
function apiReadyProfiles(purpose){return apiSettingsData.profiles.filter(p=>p.purpose===purpose&&p.configured);}
function apiSlot(purpose){return apiSettingsData.slots?.[purpose]||apiReadyProfiles(purpose)[0]||null;}
async function apiSettingsRequest(body){const token=document.querySelector('meta[name="app-token"]')?.content;const headers={'Content-Type':'application/json',...(token?{'X-App-Token':token}:{'X-UI-Token':window.financialUiToken})};const response=await fetch('/api/api-settings',{method:'POST',headers,body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.error||'API設定操作未完成');return data;}
function publishApiSettings(data){apiSettingsData=data;window.dispatchEvent(new CustomEvent('api-settings-changed',{detail:data}));}
async function refreshApiSettings(){const data=await apiSettingsRequest({action:'list'});publishApiSettings(data);return data;}
function clearApiKeys(){for(const purpose of apiPurposes)if(apiElement(apiId(purpose,'key')))apiElement(apiId(purpose,'key')).value='';}
function updateAnswerModel(){const provider=apiElement('api-answer-provider').value,profile=apiSlot('answer');apiElement('api-answer-model').value=profile?.provider===provider?profile.model:apiSettingsData.model_suggestions.answer?.[provider]?.[0]||'';apiElement('api-answer-key').value='';}
function renderApiSettings(){
 for(const purpose of apiPurposes){apiElement(apiId(purpose,'save')).disabled=false;const profile=apiSlot(purpose),credential=apiSettingsData.credentials.find(c=>c.id===profile?.credential_id);apiElement(apiId(purpose,'status')).textContent=profile?'已設定（金鑰不顯示；連線未驗證）':'尚未設定';const button=apiElement(apiId(purpose,'delete'));button.disabled=!profile||credential?.deletable===false;button.title=credential?.deletable===false?'金鑰由外部環境提供，請在啟動環境移除':'';}
 apiElement('api-rerank-model-label').textContent='模型：'+(apiSlot('rerank')?.model||'rerank-3-lite');
 apiElement('api-answer-provider').value=apiSlot('answer')?.provider||'gemini';updateAnswerModel();
}
async function saveApiSlot(purpose,event){
 event.preventDefault();const provider=purpose==='answer'?apiElement('api-answer-provider').value:'voyage';
 const model=purpose==='embedding'?'voyage-finance-2':purpose==='rerank'?(apiSlot('rerank')?.model||'rerank-3-lite'):apiElement('api-answer-model').value.trim();
 const button=apiElement(apiId(purpose,'save')),request={action:'save-slot',purpose,provider,model,api_key:apiElement(apiId(purpose,'key')).value};button.disabled=true;
 try{publishApiSettings(await apiSettingsRequest(request));clearApiKeys();renderApiSettings();apiElement('api-settings-message').textContent='已儲存；建庫與問答選單已更新。';}
 catch(error){apiElement('api-settings-message').textContent=error.message;}
 finally{request.api_key='';apiElement(apiId(purpose,'key')).value='';button.disabled=false;}
}
async function deleteApiSlot(purpose){
 if(!confirm('刪除此用途的本機金鑰設定？'))return;
 const button=apiElement(apiId(purpose,'delete'));button.disabled=true;
 try{publishApiSettings(await apiSettingsRequest({action:'delete-slot',purpose}));clearApiKeys();renderApiSettings();apiElement('api-settings-message').textContent='已清除此用途；其他用途仍使用的共用金鑰會保留。';}
 catch(error){apiElement('api-settings-message').textContent=error.message;renderApiSettings();}
}
async function loadApiSettings(host=null){try{
 if(!apiElement('api-settings-dialog')){
  const response=await fetch('/api-settings.html');if(!response.ok)throw Error('無法載入API設定介面');
  const template=document.createElement('template');template.innerHTML=await response.text();
  if(host&&host.nodeType===1){const dialog=template.content.querySelector('dialog'),section=document.createElement('section');section.id=dialog.id;section.className='api-settings-inline';section.append(...dialog.childNodes);dialog.replaceWith(section);host.append(template.content);}else document.body.append(template.content);
  apiElement('api-settings-close').onclick=()=>{clearApiKeys();apiElement('api-settings-dialog').close?.();};
  apiElement('api-settings-dialog').addEventListener('close',clearApiKeys);apiElement('api-answer-provider').onchange=updateAnswerModel;
  for(const purpose of apiPurposes){apiElement(apiId(purpose,'form')).onsubmit=event=>saveApiSlot(purpose,event);apiElement(apiId(purpose,'delete')).onclick=()=>deleteApiSlot(purpose);}
 }
 apiElement('api-settings-close').hidden=apiElement('api-settings-dialog').tagName!=='DIALOG';await refreshApiSettings();clearApiKeys();renderApiSettings();apiElement('api-settings-message').textContent='';
 const dialog=apiElement('api-settings-dialog');apiElement('api-settings-close').hidden=dialog.tagName!=='DIALOG';dialog.showModal?.();
 }catch(error){const message=apiElement('api-settings-message');if(message){message.textContent=error.message;for(const purpose of apiPurposes){apiElement(apiId(purpose,'save')).disabled=true;apiElement(apiId(purpose,'delete')).disabled=true;}}else alert(error.message);}
}
let apiSettingsOpening=null;
async function openApiSettings(host=null){if(apiSettingsOpening)return apiSettingsOpening;apiSettingsOpening=loadApiSettings(host);try{return await apiSettingsOpening;}finally{apiSettingsOpening=null;}}
window.openApiSettings=openApiSettings;
