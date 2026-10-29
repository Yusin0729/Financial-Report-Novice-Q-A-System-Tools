// Local reranker remains selectable without any API credentials.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('Code_2/functions/web/static/app.js','utf8');
const implementation=source.match(/function rerankProfiles\(\)\{[^\n]+\}/)[0];
const local={id:'local_bge_reranker_v2_m3',provider:'bge',configured:true};
const state={metadata:{local_rerank_profiles:[local]}};
let cloud=[];const sandbox={state,apiReadyProfiles:()=>cloud};vm.createContext(sandbox);
vm.runInContext(implementation,sandbox);
assert.equal(sandbox.rerankProfiles().length,1);
assert.equal(sandbox.rerankProfiles()[0].id,local.id);
cloud=[{id:'voyage',provider:'voyage',configured:true}];
assert.equal(sandbox.rerankProfiles().length,2);
assert.match(fs.readFileSync('Code_2/functions/web/static/saved-rerank.js','utf8'),/rerankProfiles\(\)/);
console.log('BGE local rerank UI choices passed');
