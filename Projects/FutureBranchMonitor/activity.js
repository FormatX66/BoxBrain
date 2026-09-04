/* Render only observed fields. No HTML interpolation, network writes or command execution. */
const workloadStyle = document.createElement('style');
workloadStyle.textContent = `.workloadSummary{border-bottom:1px solid #29394b;padding-bottom:24px}.workloadSummary .big{font-size:25px}.meter{height:5px;background:#29394b;border-radius:5px;margin-top:14px;overflow:hidden}.meter span{display:block;background:#67ddc0;height:100%}.providerStates,.workloadFilters{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.providerStates>div{background:#0c1722;padding:8px 12px;border-radius:7px}.workloadFilters label{font-size:12px;color:#9fb1c5;display:flex;gap:7px;align-items:center}.workloadFilters input{background:#213344;color:#e6edf4;border:1px solid #405267;border-radius:6px;padding:9px;width:220px}#workloadTable{min-width:940px}#workloadTable td:first-child{max-width:240px;overflow-wrap:anywhere}#workloadTable td:nth-child(4){max-width:190px}#workloadTable td:nth-child(6){max-width:175px}#workloadGaps{border-top:1px solid #29394b;margin-top:15px;padding-top:12px}button:disabled{opacity:.4;cursor:default}.cpuCell{min-width:100px}.cpuCell .meter{width:85px;margin:5px 0}#workloadSources p{margin:10px 0}`;
document.head.append(workloadStyle);
let workloadData, workloadPage = 0, workloadOffline = false;
const wEl = id => document.getElementById(id);
const wText = (id, value) => wEl(id).textContent = value;
const wAdd = (parent, tag, value, cls) => {const node=document.createElement(tag);node.textContent=value;if(cls)node.className=cls;parent.append(node);return node;};
const wAge = seconds => seconds == null ? 'Unknown' : seconds < 60 ? Math.floor(seconds)+'s' : seconds < 3600 ? Math.floor(seconds/60)+'m' : seconds < 86400 ? Math.floor(seconds/3600)+'h' : Math.floor(seconds/86400)+'d';
const finished = row => ['ended','success','failure','cancelled','skipped','timed_out','neutral','action_required','stale'].includes(row.state);
function wLink(parent, label, url) {
  try {const parsed=new URL(url);if(parsed.protocol!=='https:' || !['github.com','chatgpt.com'].includes(parsed.hostname))return;
    const a=wAdd(parent,'a',label);a.href=parsed.href;a.target='_blank';a.rel='noopener noreferrer';}catch{}
}
function renderWorkloads(data){
  workloadData=data;workloadOffline=false;
  const feed=data.workloads;if(!feed){wText('workloadConnection','Feed not installed');return;}
  const decision=data.engine.continuous_exploration?.resource_decision||{}, host=decision.observed_host||{};
  const hostFresh=data.engine.reachable&&!data.engine.stale&&host.observed_at&&data.observed_at-host.observed_at<=15;
  wText('hostCpu',hostFresh&&host.cpu_percent!=null?host.cpu_percent+'%':'Unavailable');
  wEl('hostCpuBar').style.width=(hostFresh?Math.max(0,Math.min(100,host.cpu_percent||0)):0)+'%';
  wText('hostMemory',hostFresh&&host.available_memory_mb!=null?host.available_memory_mb.toLocaleString()+' MB RAM available · '+host.physical_load_percent+'% in use':'No fresh host sample');
  const local=feed.providers.local||{}, github=feed.providers.github||{};
  wText('workloadCounts',(['ok','empty'].includes(local.status)&&!local.stale?feed.summary.local_running:'—')+' local · '+(['ok','empty'].includes(github.status)&&!github.stale?feed.summary.github_active_observed:'—')+' GitHub');
  wText('workloadCountScope','Active observed processes and jobs; bounded provider inventory');
  wText('workloadDecision',hostFresh?(decision.selected==='reduced_local_budget'?'Reduced exploration':'Normal exploration'):'Awaiting decision');
  const used=decision.activity_evidence;
  wText('workloadInput',used?.available&&hostFresh?'Consumed activity '+used.snapshot_id.slice(0,10)+' · '+(decision.activity_contention?'local contention detected':'no contention trigger')+' · explorer only':hostFresh?'Host sampler connected; shared activity '+(used?.reason||'consumer not installed').replaceAll('_',' '):'No current consumer claim');
  wText('workloadConnection','Feed '+feed.snapshot_id.slice(0,10));
  wEl('providerStates').replaceChildren();wEl('workloadSources').replaceChildren();
  for(const [name,p] of Object.entries(feed.providers)){
    const label=name==='local'?'This computer':'GitHub';
    const status=p.status==='ok'||p.status==='empty'?(p.stale?'Stale':p.status==='empty'?'Empty':'Connected'):p.status||'Unavailable';
    const item=wAdd(wEl('providerStates'),'div','');wAdd(item,'strong',label+' · '+status,p.stale||p.error?'warn':'ok');
    wAdd(item,'div','Observed '+wAge(p.age_seconds)+' ago'+(p.error?' · '+p.error.replaceAll('_',' '):''),'small');
    wAdd(wEl('workloadSources'),'p',label+': '+(p.scope||'No inventory received')+'. Poll delay '+(p.next_poll_seconds??'—')+'s · last collection '+(p.collector_wall_ms??'—')+' ms wall / '+(p.collector_cpu_ms??'—')+' ms monitor CPU. '+(p.overhead_scope||'')+(p.http_status?' · HTTP '+p.http_status:''));
  }
  wEl('workloadGaps').replaceChildren();
  for(const gap of feed.capability_gaps||[]){const p=wAdd(wEl('workloadGaps'),'p',gap.provider+': '+gap.detail+' ');wLink(p,'Open environment',gap.url);}
  renderWorkloadRows();
}
function renderWorkloadRows(){
  if(!workloadData?.workloads)return;
  const query=wEl('workloadSearch').value.trim().toLowerCase(),location=wEl('workloadLocation').value,state=wEl('workloadState').value;
  let rows=workloadData.workloads.rows.filter(row=>(location==='all'||row.provider===location)&&(state==='all'||(state==='finished')===finished(row))&&[row.name,row.pid,row.owner,row.step,row.runner].some(value=>String(value??'').toLowerCase().includes(query)));
  const sort=wEl('workloadSort').value;
  rows.sort((a,b)=>sort==='name'?a.name.localeCompare(b.name):sort==='recent'?b.observed_at-a.observed_at:sort==='memory'?(b.memory_mb??-1)-(a.memory_mb??-1):(b.cpu_percent??-1)-(a.cpu_percent??-1));
  const size=25,pages=Math.max(1,Math.ceil(rows.length/size));workloadPage=Math.min(workloadPage,pages-1);
  wEl('workloadRows').replaceChildren();
  for(const r of rows.slice(workloadPage*size,(workloadPage+1)*size)){
    const row=wAdd(wEl('workloadRows'),'tr','');
    const name=wAdd(row,'td',r.name);wAdd(name,'small',r.owner+(r.pid?' · PID '+r.pid:''));
    const where=wAdd(row,'td',r.location);wAdd(where,'small',r.state.replaceAll('_',' '));
    if(r.runner)wAdd(where,'small',r.runner);
    const metric=wAdd(row,'td',r.cpu_percent==null?'CPU unavailable':r.cpu_percent.toFixed(1)+'% CPU','cpuCell');metric.title=r.cpu_denominator;
    if(r.cpu_percent!=null){const bar=wAdd(metric,'div','','meter');wAdd(bar,'span','').style.width=Math.max(0,Math.min(100,r.cpu_percent))+'%';}
    wAdd(metric,'small',r.memory_mb==null?'RAM unavailable':r.memory_mb.toLocaleString()+' MB RAM');
    const activity=wAdd(row,'td',r.step||'Step unavailable');
    wAdd(activity,'small',r.started_at?wAge(Math.max(0,(r.completed_at||workloadData.observed_at)-r.started_at))+' elapsed':'Start time unavailable');
    const freshness=workloadOffline?'disconnected':r.freshness;
    const observed=wAdd(row,'td',wAge(r.age_seconds)+' ago',freshness==='fresh'?'ok':'warn');wAdd(observed,'small',freshness);
    observed.title=new Date(r.observed_at*1000).toLocaleString();
    const controls=wAdd(row,'td','');if(r.url)wLink(controls,'View logs / details',r.url);
    for(const c of r.controls||[]){const item=wAdd(controls,'div','');wLink(item,c.label,c.url);}
    if(!r.url&&!r.controls?.length)wAdd(controls,'span','Observation only','small');controls.title=r.control_note;
  }
  if(!rows.length){const cell=wAdd(wAdd(wEl('workloadRows'),'tr',''),'td','No observed workloads match these filters. Check source status above.','empty');cell.colSpan=6;}
  wText('workloadPageInfo',rows.length+' matching · page '+(workloadPage+1)+' of '+pages+' · 25 rows per page');
  wEl('workloadPrevious').disabled=workloadPage===0;wEl('workloadNext').disabled=workloadPage>=pages-1;
}
function workloadsDisconnected(){workloadOffline=true;wText('workloadConnection','Disconnected · historical values');wText('workloadDecision','Current decision unknown');wText('hostCpu','Unavailable');wText('hostMemory','No fresh host observation');wEl('hostCpuBar').style.width='0%';wText('workloadCounts','Unconfirmed');wText('workloadInput','Last consumed activity is historical; current input is unknown');wEl('providerStates').replaceChildren();wAdd(wEl('providerStates'),'div','Monitor disconnected · provider state unconfirmed','warn');renderWorkloadRows();}
for(const id of ['workloadLocation','workloadState','workloadSort','workloadSearch'])wEl(id).addEventListener('input',()=>{workloadPage=0;renderWorkloadRows();});
wEl('workloadPrevious').addEventListener('click',()=>{workloadPage=Math.max(0,workloadPage-1);renderWorkloadRows();});
wEl('workloadNext').addEventListener('click',()=>{workloadPage++;renderWorkloadRows();});
