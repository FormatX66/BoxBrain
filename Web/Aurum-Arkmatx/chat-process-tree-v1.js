/* AURUM_CHAT_PROCESS_TREE_V1_CANONICAL
 * Canonical website owner: FormatX66/ClusterSites.
 * Read-only visualization of Aurum's durable conversation/process tree and shared-state routing contract.
 * Tree navigation, shared state, cross-chat live sync, App presentation, consolidation, metadata cache, workflow state, and Future Branch preparation never grant arbitrary execution authority or resolve physical boundaries.
 * Farmer v3.2 adds one bounded MCP actuator: structured objectives may be submitted only through the fixed Chat-to-Git/Farmer route; callers cannot choose repository, event type, URL, token, workflow name, or arbitrary command, and the actuator grants no destructive, physical, trust-broadening, or LKG authority.
 */
(()=>{'use strict';
if(window.__aurumChatProcessTreeV1)return;
window.__aurumChatProcessTreeV1=true;

const REPO='FormatX66/BoxBrain';
const RAW=`https://raw.githubusercontent.com/${REPO}/main`;
const API=`https://api.github.com/repos/${REPO}`;
const TREE_URL=`${RAW}/Projects/Aurum/chat-process-tree.json`;
const SHARED_URL=`${RAW}/Projects/Aurum/shared-state/CURRENT_STATE.json`;
const FARMER_RUNTIME_URL=`${RAW}/Projects/AurumFarmer/Deploy/latest-windows-runtime-proof.json`;
const WORKFLOWS={shared:'Aurum Chat Tree Shared State',mcp:'Aurum Chat Tree MCP',plugin:'Aurum Chat Tree Plugin'};
const REFRESH=2*60*1000;
const FARMER_ACTUATOR={
  mergeCommit:'d7da7375d811aa85151c16e4670aca601f4ad6e2',
  pullRequest:119,
  ciRun:32980349897,
  ciConclusion:'success',
  tool:'dispatch_farmer_objective',
  fixedRepository:'FormatX66/Chat-to-Git-Pipeline',
  fixedEventType:'aurum_farmer_event',
  arbitraryRepository:false,
  arbitraryEventType:false,
  arbitraryUrl:false,
  rawToken:false,
  arbitraryWorkflow:false,
  arbitraryCommand:false,
  destructiveAuthority:false,
  physicalAuthority:false,
  trustBroadeningAuthority:false,
  lkgMutation:false,
  endToEndDispatchProven:false
};
const IMPL={
 topicRouter:[`${RAW}/Projects/Aurum/Experiments/chat_topic_router.py`,'child_split'],
 sharedState:[`${RAW}/Projects/Aurum/Experiments/shared_state_bus.py`,'running_verified'],
 gptBridge:[`${RAW}/Projects/Aurum/Experiments/chat_tree_bridge.py`,'post_receipt'],
 consolidation:[`${RAW}/Projects/Aurum/Experiments/chat_tree_bridge.py`,'plan_consolidation'],
 operationalFuture:[`${RAW}/Projects/Aurum/Experiments/operational_branch.py`,'unchanged_retry_allowed'],
 mcpAdapter:[`${RAW}/Projects/Aurum/ChatTreeMCP/main.py`,'get_tree'],
 farmerActuator:[`${RAW}/Projects/Aurum/ChatTreeMCP/main.py`,'dispatch_farmer_objective'],
 pluginPanel:[`${RAW}/Projects/Aurum/ChatTreePlugin/server.js`,'chat-tree-widget'],
 contextCache:[`${RAW}/Admin/sync_cross_chat_cache.py`,'boxbrain-cross-chat-cache-receipt-v1']
};
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const age=v=>{const n=Date.parse(v||'');return Number.isFinite(n)?Math.max(0,Date.now()-n):null};
const ageText=ms=>{if(ms===null)return'unknown';const m=Math.floor(ms/60000);if(m<60)return`${m} min`;const h=Math.floor(m/60),r=m%60;return r?`${h}h ${r}m`:`${h}h`};
let state={tree:null,shared:null,sharedPresent:false,farmerRuntime:null,farmerRuntimePresent:false,runs:{},impl:{},error:''};

const css=document.createElement('style');
css.textContent=`.chat-tree-card .ct-hint{margin-top:9px;font-size:9px;color:#737e92;font-weight:750}.chat-tree-card .ct-detail{display:none;margin-top:11px;padding-top:11px;border-top:1px solid #283041;font-size:10.5px;line-height:1.48;color:#909bad}.chat-tree-card[aria-expanded=true] .ct-detail{display:block}.chat-tree-card[aria-expanded=true] .ct-hint{color:#7ee7ff}.chat-tree-card .ct-list{list-style:none;margin:8px 0 0;padding:0}.chat-tree-card .ct-node{margin:5px 0;padding-left:14px;border-left:2px solid #364156}.chat-tree-card .ct-node b{color:#d7dbea}.chat-tree-card .ct-state{margin-left:6px;color:#7ee7ff;font-size:9px;text-transform:uppercase}.chat-tree-card .ct-meta{display:block;color:#747f92;font-size:9px}.chat-tree-card .ct-grid{display:grid;grid-template-columns:145px minmax(0,1fr);gap:5px 9px;margin:10px 0}.chat-tree-card .ct-grid b{color:#cfd3df;font-size:10px}.chat-tree-card .ct-grid span{min-width:0;overflow-wrap:anywhere}@media(max-width:680px){.chat-tree-card .ct-grid{grid-template-columns:1fr}}`;
document.head.appendChild(css);

function valid(){
  const t=state.tree;
  return t?.schema==='aurum-chat-process-tree-v1'&&Array.isArray(t?.nodes)&&t?.invariants?.human_focus_collapses_machine_lanes===false&&t?.invariants?.completed_or_archived_nodes_are_deleted===false&&t?.invariants?.merge_preserves_source_provenance===true&&t?.invariants?.tree_grants_execution_authority===false&&t?.invariants?.tree_resolves_physical_boundaries===false;
}
function children(id){return state.tree.nodes.filter(n=>n?.parent_id===id).sort((a,b)=>Number(a.sequence||0)-Number(b.sequence||0)||String(a.title||'').localeCompare(String(b.title||'')))}
function branch(node){const kids=children(node.node_id),concepts=Array.isArray(node.concepts)?node.concepts:[];return `<li class="ct-node"><b>${esc(node.title||node.node_id)}</b><span class="ct-state">${esc(node.state||'unknown')}</span><span class="ct-meta">${esc(node.lane_id||'lane unknown')}${node.boundary?` · boundary: ${esc(node.boundary)}`:''}</span>${concepts.length?`<span class="ct-meta">concepts: ${esc(concepts.join(' · '))}</span>`:''}${kids.length?`<ul class="ct-list">${kids.map(branch).join('')}</ul>`:''}</li>`}
function ensure(){
  const systems=$('#systems');if(!systems)return null;
  let card=$('[data-id="chat-process-tree"]',systems);if(card)return card;
  card=document.createElement('article');card.className='system-card chat-tree-card';card.dataset.id='chat-process-tree';card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-expanded','false');
  card.innerHTML='<div class="card-head"><div class="card-icon">⑂</div><span class="pill experiment">Experiment</span></div><h3>Chat Process Tree</h3><p>One human focus path while sibling machine work, concepts, evidence, and boundaries stay durable.</p><div class="evidence">Loading durable branch state…</div><div class="ct-hint">Tap to expand topic routing, cross-chat live sync, bounded Farmer dispatch, MCP/App bridge, consolidation, shared state, context cache, concurrent lanes, and action boundaries →</div><div class="ct-detail"></div>';
  const toggle=e=>{if(e?.type==='keydown'&&!['Enter',' '].includes(e.key))return;if(e?.type==='keydown')e.preventDefault();card.setAttribute('aria-expanded',String(card.getAttribute('aria-expanded')!=='true'));e?.stopPropagation?.()};
  card.addEventListener('click',toggle);card.addEventListener('keydown',toggle);systems.appendChild(card);return card;
}
function latestRun(runs,name){return (Array.isArray(runs)?runs:[]).filter(r=>r?.name===name&&r?.head_branch==='main').sort((a,b)=>Date.parse(b.updated_at||b.created_at||0)-Date.parse(a.updated_at||a.created_at||0))[0]||null}
function runText(key){const r=state.runs[key];if(!r)return'no dedicated workflow evidence';return`${r.conclusion||r.status||'unknown'} · ${ageText(age(r.updated_at||r.created_at))} old`}
function runOk(key){const r=state.runs[key];return r?.status==='completed'&&r?.conclusion==='success'}
function liveSyncProof(tree){const node=(tree?.nodes||[]).find(n=>n?.node_id==='cross-chat-live-sync'),refs=Array.isArray(node?.evidence_refs)?node.evidence_refs.map(String):[];return node?.state==='completed'&&refs.some(r=>r.startsWith('mcp-endpoint:https://aurum.arkmatx.com/chat-tree/mcp'))&&refs.some(r=>r.startsWith('shared-state-event:evt-cross-chat-live-sync-'))}
function sharedInvariant(key){return state.shared?.invariants?.[key]===true}
function farmerRuntimeOk(){
  const p=state.farmerRuntime;
  return state.farmerRuntimePresent&&p?.schema==='aurum.farmer.windows-runtime-proof.v1'&&p?.task_state==='Running'&&p?.initial_health_verified===true&&p?.post_restart_health_verified===true&&p?.event_chain_valid===true&&p?.restart_resume_job_state==='SUCCEEDED'&&p?.destructive_action_allowed===false&&p?.lkg_mutation_inferred===false&&p?.physical_proof_inferred===false;
}
function render(){
  const card=ensure();if(!card)return;
  const pill=$('.pill',card),evidence=$('.evidence',card),detail=$('.ct-detail',card);
  if(!valid()){
    pill.className='pill unknown';pill.textContent='Unknown';
    evidence.textContent=state.error?`Chat Tree evidence incomplete: ${state.error}`:'Chat Tree contract is not verified.';
    if(detail)detail.innerHTML='<b>Frontiers Advancing:</b> none inferred from missing evidence.<br><b>Needs Work → Aurum/System:</b> restore a valid durable tree projection and repository evidence before claiming runtime state.<br><b>Your Actions:</b> none. Missing dashboard evidence cannot manufacture a human task.';
    return;
  }
  const tree=state.tree;
  const active=(tree.active_frontier||[]).length;
  const concepts=Object.keys(tree.concept_index||{}).length;
  const root=tree.nodes.find(n=>n.node_id===tree.root_id);
  const mcpGreen=runOk('mcp');
  const pluginGreen=runOk('plugin');
  const mcpReady=state.impl.mcpAdapter===true&&mcpGreen;
  const pluginReady=state.impl.pluginPanel===true&&pluginGreen;
  const liveSync=liveSyncProof(tree);
  const consolidationReady=state.impl.consolidation===true;
  const actuatorReady=state.impl.farmerActuator===true&&FARMER_ACTUATOR.ciConclusion==='success';
  const farmerHealthy=farmerRuntimeOk();
  const appendOnlyTruth=state.sharedPresent&&sharedInvariant('append_only_events')&&state.shared?.invariants?.chat_memory_is_source_of_truth===false&&state.shared?.invariants?.state_bus_grants_execution_authority===false;
  const failed=Object.values(state.runs).some(r=>r&&['failure','timed_out','startup_failure','action_required'].includes(r.conclusion));
  pill.className=failed?'pill failed':'pill experiment';
  pill.textContent=failed?'Needs Work':actuatorReady&&farmerHealthy?'Bounded Actuator':liveSync&&mcpReady&&pluginReady?'Live Sync':'Advancing';
  evidence.textContent=`${active} live nodes · ${concepts} retained concepts · cross-chat live sync ${liveSync?'E2E proven':'not proven'} · MCP ${mcpReady?'CI green':'bounded'} · Farmer actuator ${actuatorReady?'CI proven':'not proven'} · Farmer runtime ${farmerHealthy?'healthy':'separate proof pending'} · App panel ${pluginReady?'CI green':'bounded'} · consolidation ${consolidationReady?'present':'not proven'}.`;

  const eventCount=Number.isFinite(Number(state.shared?.event_count))?Number(state.shared.event_count):null;
  const sharedText=state.sharedPresent?`runtime shared-state projection present${eventCount!==null?` · ${eventCount} append-only events`:''}${appendOnlyTruth?' · append-only authority contract verified':''}`:'runtime CURRENT_STATE projection not yet persisted';
  const implText=`topic router:${state.impl.topicRouter?'present':'not proven'} · shared-state bus:${state.impl.sharedState?'present':'not proven'} · GPT bridge:${state.impl.gptBridge?'present':'not proven'} · consolidation:${consolidationReady?'present':'not proven'} · Future Branch:${state.impl.operationalFuture?'present':'not proven'} · MCP adapter:${state.impl.mcpAdapter?'present':'not proven'} · bounded Farmer actuator:${actuatorReady?'CI proven':'not proven'} · MCP App panel:${state.impl.pluginPanel?'present':'not proven'} · cross-chat metadata cache:${state.impl.contextCache?'present':'not proven'}`;
  const workflowText=`shared:${runText('shared')} · MCP:${runText('mcp')} · App:${runText('plugin')}`;
  const liveSyncText=liveSync?'public HTTPS MCP publish/read completed end-to-end; append-only shared-state event is retained as source-of-truth evidence and grants no execution authority':'end-to-end public MCP publish/read proof not currently present in the canonical tree';
  const consolidationText=consolidationReady?'exact-parent-and-lane terminal branches can be planned for revision-bound consolidation; source nodes are archived with concepts/evidence/boundaries/provenance preserved; underlying ChatGPT History remains outside plugin authority':'branch consolidation implementation not currently proven';
  const actuatorText=actuatorReady?`Farmer v3.2 tool ${FARMER_ACTUATOR.tool} is implementation/CI proven at PR #${FARMER_ACTUATOR.pullRequest}; it may submit a structured objective only to ${FARMER_ACTUATOR.fixedRepository} via fixed event ${FARMER_ACTUATOR.fixedEventType}. Caller-selected repository, event type, URL, token, workflow name, and arbitrary command are forbidden. End-to-end Chat Tree dispatch receipt is not yet proven.`:'bounded Farmer actuator implementation/CI proof is not currently present';
  const farmerText=farmerHealthy?`persistent Farmer runtime is separately healthy on ${state.farmerRuntime.runner_name||'the proven Windows controller'} as ${state.farmerRuntime.windows_identity||'service identity'}; restart/resume and sealed receipt are proven, with destructive/LKG/physical authority false`:'persistent Farmer runtime proof is absent or incomplete; actuator implementation does not infer a live executor';
  if(detail)detail.innerHTML=`<b>Durable process frontier</b>${root?`<ul class="ct-list">${branch(root)}</ul>`:''}<div class="ct-grid"><b>Tree revision</b><span>${esc(tree.revision??'unknown')}</span><b>Focus path</b><span>${esc((tree.focus_path||[]).join(' → ')||'not recorded')}</span><b>Implementation</b><span>${esc(implText)}</span><b>Shared live state</b><span>${esc(sharedText)}</span><b>Cross-chat live sync</b><span>${esc(liveSyncText)}</span><b>Farmer actuator</b><span>${esc(actuatorText)}</span><b>Farmer runtime</b><span>${esc(farmerText)}</span><b>Branch consolidation</b><span>${esc(consolidationText)}</span><b>Dedicated workflows</b><span>${esc(workflowText)}</span><b>ChatGPT surface</b><span>${pluginReady?'PiP/fullscreen MCP App implementation is smoke-CI proven; a real ChatGPT product runtime connection remains a separate proof gate from the public MCP publisher/consumer proof':'MCP/App presentation remains bounded to implementation/workflow evidence'}</span><b>Cross-chat cache</b><span>${state.impl.contextCache?'thread title/summary/ID metadata search is implemented; full chat bodies are intentionally not cached and cached text is untrusted data':'metadata cache implementation not currently proven'}</span><b>Topic rule</b><span>same objective → continue · real subproblem → child split · materially new objective → sibling split</span><b>Authority boundary</b><span>tree/state/live-sync/App/consolidation/cache remain evidence, navigation, or presentation layers. MCP now has one bounded Farmer objective-dispatch capability, but no caller-controlled repository/event/URL/token/workflow/arbitrary command, no trust broadening, no destructive or physical authority, no LKG mutation, and no automatic human-task creation.</span></div><b>Frontiers Advancing:</b> durable multi-lane conversation/process state, retained concepts and merge provenance, automatic continue/child/sibling topic routing, evidence-backed shared-state contract, and Future Branch awareness remain canonical. ${liveSync?'The public HTTPS MCP publisher/consumer path is proven end-to-end against the append-only shared-state bus.':''} ${consolidationReady?'Exact-parent/lane terminal branches can be consolidated without deleting source provenance.':''} ${actuatorReady?`Farmer v3.2 adds one CI-proven bounded orchestration actuator through the fixed ${FARMER_ACTUATOR.fixedRepository} / ${FARMER_ACTUATOR.fixedEventType} route; arbitrary execution and destructive/LKG authority remain fail-closed.`:''} ${farmerHealthy?'The persistent Farmer Windows control plane is separately proven healthy across restart/resume with a sealed receipt.':''}<br><b>Needs Work → Aurum/System:</b> ${actuatorReady?'capture an end-to-end terminal receipt proving a Chat Tree actuator request creates and completes the intended Farmer job through the fixed bridge; until then, do not infer successful external execution from actuator availability. ':''}${liveSync?'Extend the proven public MCP publisher/consumer path to a real ChatGPT product runtime and concurrent-client use while preserving one append-only state authority.':'Obtain end-to-end public MCP publish/read proof before claiming cross-chat live-state flow.'} Calibrate topic splitting, context retrieval, bounded objective dispatch, and terminal-branch consolidation in normal use for fewer correction turns and duplicate lanes without provenance loss or speculative churn.<br><b>Your Actions:</b> none. Chat focus, topic classification, MCP/App availability, bounded Farmer dispatch capability, consolidation candidates, cached metadata, workflow state, predicted intent, or shared-state events cannot create a human task. Exact directions belong elsewhere only after fresh evidence proves a genuinely human-only physical, destructive, credential, identity-authentication, or subjective-preference boundary.`;

  window.__aurumChatProcessTreeState={
    schema:'aurum-command-center-chat-process-tree-v1.0',
    componentRevision:'1.3',
    modelSchema:tree.schema,
    treeRevision:Number.isFinite(Number(tree.revision))?Number(tree.revision):null,
    activeNodes:active,
    retainedConcepts:concepts,
    topicRouterVisible:state.impl.topicRouter===true,
    sharedStateBusVisible:state.impl.sharedState===true,
    gptBridgeVisible:state.impl.gptBridge===true,
    operationalFutureBranchVisible:state.impl.operationalFuture===true,
    mcpAdapterVisible:state.impl.mcpAdapter===true,
    mcpWorkflowState:state.runs.mcp?.conclusion||state.runs.mcp?.status||'unknown',
    chatGptAppPanelVisible:state.impl.pluginPanel===true,
    chatGptAppWorkflowState:state.runs.plugin?.conclusion||state.runs.plugin?.status||'unknown',
    crossChatMetadataCacheVisible:state.impl.contextCache===true,
    crossChatLiveSyncVisible:liveSync,
    crossChatLiveSyncEndToEndProven:liveSync,
    appendOnlySharedStateSourceOfTruth:appendOnlyTruth,
    branchConsolidationVisible:consolidationReady,
    branchConsolidationRequiresPlanToken:consolidationReady,
    underlyingChatHistoryConsolidated:false,
    fullChatBodiesCached:false,
    cachedTextGrantsAuthority:false,
    chatGptRuntimeConnectionInferred:false,
    sharedRuntimeProjectionPresent:state.sharedPresent,
    dedicatedWorkflowState:state.runs.shared?.conclusion||state.runs.shared?.status||'unknown',
    humanFocusCollapsesMachineLanes:false,
    completedNodesDeleted:false,
    mergePreservesSourceProvenance:true,
    treeGrantsExecutionAuthority:false,
    sharedStateGrantsExecutionAuthority:false,
    crossChatLiveSyncGrantsExecutionAuthority:false,
    consolidationGrantsExecutionAuthority:false,
    mcpGrantsGeneralExecutionAuthority:false,
    farmerActuatorVisible:actuatorReady,
    farmerActuatorImplemented:state.impl.farmerActuator===true,
    farmerActuatorCiVerified:FARMER_ACTUATOR.ciConclusion==='success',
    farmerActuatorBoundedDispatch:actuatorReady,
    farmerActuatorFixedRepository:FARMER_ACTUATOR.fixedRepository,
    farmerActuatorFixedEventType:FARMER_ACTUATOR.fixedEventType,
    farmerActuatorArbitraryRepository:false,
    farmerActuatorArbitraryEventType:false,
    farmerActuatorArbitraryUrl:false,
    farmerActuatorRawToken:false,
    farmerActuatorArbitraryWorkflow:false,
    farmerActuatorArbitraryCommand:false,
    farmerActuatorGrantsArbitraryExecutionAuthority:false,
    farmerActuatorGrantsDestructiveAuthority:false,
    farmerActuatorGrantsPhysicalAuthority:false,
    farmerActuatorGrantsTrustBroadeningAuthority:false,
    farmerActuatorGrantsLkgMutation:false,
    farmerActuatorEndToEndDispatchProven:false,
    farmerRuntimeProofPresent:state.farmerRuntimePresent,
    farmerRuntimeHealthy:farmerHealthy,
    farmerRuntimeRestartResumeProven:farmerHealthy,
    appPanelGrantsExecutionAuthority:false,
    treeResolvesPhysicalBoundaries:false,
    needsWorkOwner:'aurum-system',
    consolidationCreatesHumanAction:false,
    farmerActuatorCreatesHumanAction:false,
    humanActionInference:false
  };
  window.dispatchEvent(new CustomEvent('aurum-chat-process-tree-state',{detail:window.__aurumChatProcessTreeState}));
}
async function getText(u){const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw Error(`HTTP ${r.status}`);return r.text()}
async function getJson(u){const r=await fetch(u,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json()}
async function presence(){const pairs=await Promise.all(Object.entries(IMPL).map(async([k,[u,marker]])=>{try{return[k,(await getText(u)).includes(marker)]}catch{return[k,false]}}));return Object.fromEntries(pairs)}
async function optionalJson(url){try{return{present:true,value:await getJson(url)}}catch{return{present:false,value:null}}}
async function refresh(){
  try{
    const [tree,runs,impl,shared,farmerRuntime]=await Promise.all([getJson(TREE_URL),getJson(`${API}/actions/runs?branch=main&per_page=100`),presence(),optionalJson(SHARED_URL),optionalJson(FARMER_RUNTIME_URL)]);
    const list=runs?.workflow_runs||[];
    state={tree,shared:shared.value,sharedPresent:shared.present,farmerRuntime:farmerRuntime.value,farmerRuntimePresent:farmerRuntime.present,runs:{shared:latestRun(list,WORKFLOWS.shared),mcp:latestRun(list,WORKFLOWS.mcp),plugin:latestRun(list,WORKFLOWS.plugin)},impl,error:''};
  }catch(e){state={...state,error:e?.message||'request failed'}}
  render();
}
function boot(){const systems=$('#systems');if(!systems){setTimeout(boot,250);return}new MutationObserver(()=>{if(!systems.querySelector('[data-id="chat-process-tree"]'))render()}).observe(systems,{childList:true});refresh();setInterval(refresh,REFRESH)}
boot();
})();
