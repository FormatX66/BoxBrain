#!/usr/bin/env python3
from __future__ import annotations
import json,time,urllib.request,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE_DIR=ROOT/'autobuild'
STATE=STATE_DIR/'state.json'
EVENTS=STATE_DIR/'events.jsonl'
CONTROLLER='https://arkmatx.com/aurum/index.php'

DEFAULT={
  'schema':1,
  'cycle':0,
  'last_controller_status':None,
  'targets':{
    'BBPI4':{
      'status':'unconfirmed',
      'outbound_enrollment_ready':False,
      'carriers':['10.12.194.1','10.42.194.1','bbpi4.local','192.168.0.194','remote-desktop','arkmatx-outbound'],
      'preferred_bootstrap':['10.12.194.1','10.42.194.1','bbpi4.local','remote-desktop']
    },
    'Aurum-Morris':{
      'status':'unconfirmed',
      'outbound_enrollment_ready':False,
      'carriers':['winrm','arkmatx-outbound','local-windows-lane'],
      'preferred_bootstrap':['winrm']
    }
  },
  'next':'probe-controller-and-target-plan'
}

def load_state():
    if not STATE.exists(): return json.loads(json.dumps(DEFAULT))
    current=json.loads(STATE.read_text())
    # Merge newly learned carrier knowledge into older durable state.
    for name,defaults in DEFAULT['targets'].items():
        target=current.setdefault('targets',{}).setdefault(name,{})
        target.setdefault('status','unconfirmed')
        target.setdefault('outbound_enrollment_ready',False)
        existing=list(target.get('carriers',[]))
        target['carriers']=list(dict.fromkeys(defaults['carriers']+existing))
        target['preferred_bootstrap']=defaults.get('preferred_bootstrap',[])
    return current

def save_state(s):
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n')

def event(kind,payload):
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    with EVENTS.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'time':int(time.time()),'kind':kind,'payload':payload},sort_keys=True)+'\n')

def controller_status():
    req=urllib.request.Request(CONTROLLER,headers={'Cache-Control':'no-cache','User-Agent':'Aurum-Autobuild/1'})
    with urllib.request.urlopen(req,timeout=10) as r: return json.load(r)

def controller_emit(cycle,next_intent,targets):
    frame={
      'schema':'aurum.uaf.v0','frame_id':uuid.uuid4().hex,
      'origin':'Aurum-GitHub-Autobuild','target':'Aurum-Arkmatx',
      'intent':'build_checkpoint',
      'state_delta':{'cycle':cycle,'next':next_intent,'builder':'github-python','targets':targets},
      'provenance':{'node':'Aurum-GitHub-Autobuild','created':int(time.time())},
      'verification':{'content_addressed':True,'reversible':True}
    }
    body=json.dumps(frame,separators=(',',':')).encode()
    req=urllib.request.Request(CONTROLLER,data=body,method='POST',headers={'Content-Type':'application/json','User-Agent':'Aurum-Autobuild/1'})
    with urllib.request.urlopen(req,timeout=10) as r: return json.load(r)

def choose_next(s):
    morris=s['targets']['Aurum-Morris']; bb=s['targets']['BBPI4']
    if not morris.get('outbound_enrollment_ready') or not bb.get('outbound_enrollment_ready'):
        return 'deploy-and-verify-outbound-node-heartbeat'
    # Prefer concrete, already-authorized local bootstrap carriers before generic outbound enrollment.
    if morris['status']!='confirmed': return 'bootstrap-morris-via-winrm-then-enroll-arkmatx'
    if bb['status']!='confirmed': return 'bootstrap-bbpi4-via-usb-ap-mdns-or-rdp-then-enroll-arkmatx'
    return 'slush-repo-ingest'

def main():
    s=load_state();s['cycle']=int(s.get('cycle',0))+1
    try:
        c=controller_status()
        capabilities=list(c.get('capabilities') or [])
        s['last_controller_status']={'ok':True,'node':c.get('node'),'status':c.get('status'),'events':c.get('events'),'capabilities':capabilities,'time':int(time.time())}
        if 'node_enroll' in capabilities and 'node_heartbeat' in capabilities:
            s['targets']['BBPI4']['outbound_enrollment_ready']=True
            s['targets']['Aurum-Morris']['outbound_enrollment_ready']=True
        event('controller-heartbeat',s['last_controller_status'])
    except Exception as e:
        s['last_controller_status']={'ok':False,'error':type(e).__name__,'time':int(time.time())}
        event('controller-heartbeat-failed',s['last_controller_status'])
    s['next']=choose_next(s)
    try:
        ack=controller_emit(s['cycle'],s['next'],s['targets'])
        s['last_controller_ack']={'ok':ack.get('status')=='merged','time':int(time.time())}
        event('controller-build-ack',s['last_controller_ack'])
    except Exception as e:
        s['last_controller_ack']={'ok':False,'error':type(e).__name__,'time':int(time.time())}
        event('controller-build-ack-failed',s['last_controller_ack'])
    s['updated_at']=int(time.time())
    event('cycle-checkpoint',{'cycle':s['cycle'],'next':s['next'],'targets':s['targets']})
    save_state(s)
    print(json.dumps(s,indent=2,sort_keys=True))

if __name__=='__main__': main()
