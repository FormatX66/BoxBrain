/* AURUM_NATIVE_FRONTIER_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Reads the verified Aurum trunk checkpoint and makes the existing self-build card
 * report the actual native frontier instead of inferring progress from runner activity.
 */
(()=>{'use strict';if(window.__aurumNativeFrontierV1)return;window.__aurumNativeFrontierV1=true;
const API='https://api.github.com/repos/FormatX66/BoxBrain/contents/Projects/Codelation/autobuild/native_chain_state.json?ref=aurum%2Ftrunk-v0.01';
const REFRESH=5*60*1000;
const state={chain:null,ok:false,updated:0};
const words=v=>String(v??'unknown').replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim();
function decode(v){const raw=atob(String(v||'').replace(/\s+/g,''));try{return decodeURIComponent([...raw].map(c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join(''))}catch{return raw}}
function latestGap(c){const g=Array.isArray(c?.generations)?c.generations:[];return g.length?g[g.length-1]?.gap:null}
function frontier(c){
  const generation=Number(c?.completed_generations||0);
  const gap=latestGap(c)||c?.next_gap||'unknown-frontier';
  const blocked=String(c?.blocked_reason||'');
  const output=String(c?.blocked_output||'');
  const reason=String(c?.external_evidence?.reason||'');
  const extApplied=c?.external_evidence?.applied===true;
  const candidateVerified=/candidate-verified/i.test(output);
  let status='Verified';
  if(blocked) status='Waiting';
  if(c?.failed_attempt) status='Attention';
  const pieces=[`Native chain generation ${generation}`,words(gap)];
  if(candidateVerified) pieces.push('local candidate verified');
  if(blocked==='external-prerequisite-blocked') pieces.push(reason?`waiting on ${words(reason)}`:'waiting on external prerequisite');
  else if(blocked) pieces.push(`blocked: ${words(blocked)}`);
  else if(extApplied) pieces.push('external evidence applied');
  else pieces.push('checkpoint verified');
  if(status==='Waiting') pieces.push('Aurum/system evidence work, not your action');
  return{generation,gap,blocked,reason,status,evidence:pieces.join(' · ')};
}
function apply(){
  if(!state.ok||!state.chain)return;
  const card=document.querySelector('#systems [data-id="selfbuild"]');if(!card)return;
  const f=frontier(state.chain),pill=card.querySelector('.pill'),evidence=card.querySelector('.evidence');
  if(pill){
    const current=pill.textContent?.trim();
    const keepRunning=current==='Running'&&f.status==='Waiting';
    if(!keepRunning){pill.textContent=f.status;pill.className='pill '+(f.status==='Attention'?'failed':f.status==='Waiting'?'waiting':'success')}
  }
  if(evidence)evidence.textContent=f.evidence;
  card.dataset.nativeFrontier='verified';
  card.dataset.nativeGeneration=String(f.generation);
  card.title=f.evidence;
}
async function refresh(){
  try{
    const r=await fetch(API,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw new Error(String(r.status));
    const envelope=await r.json();const chain=JSON.parse(decode(envelope.content));
    if(chain?.schema!=='aurum-native-chain-resume-v1')throw new Error('schema');
    state.chain=chain;state.ok=true;state.updated=Date.now();apply();
  }catch(_){state.ok=false}
}
const systems=document.querySelector('#systems');if(systems)new MutationObserver(()=>requestAnimationFrame(apply)).observe(systems,{childList:true,subtree:true});
refresh();setInterval(refresh,REFRESH);setInterval(apply,3000);
})();
