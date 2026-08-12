#!/usr/bin/env python3
from __future__ import annotations
import json,time,urllib.request,urllib.error
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
    'BBPI4':{'status':'unconfirmed','carriers':['10.12.194.1','10.42.194.1','bbpi4.local','192.168.0.194','arkmatx-outbound']},
    'Aurum-Morris':{'status':'unconfirmed','carriers':['arkmatx-outbound','local-windows-lane']}
  },
  'next':'probe-controller-and-target-plan'
}

def load_state():
    if not STATE.exists(): return DEFAULT.copy()
    return json.loads(STATE.read_text())

def save_state(s):
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n')

def event(kind,payload):
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    with EVENTS.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'time':int(time.time()),'kind':kind,'payload':payload},sort_keys=True)+'\n')

def controller_status():
    req=urllib.request.Request(CONTROLLER,headers={'Cache-Control':'no-cache','User-Agent':'Aurum-Autobuild/1'})
    with urllib.request.urlopen(req,timeout=10) as r:
        data=json.load(r)
    return data

def choose_next(s):
    # Deterministic, bounded priorities. This engine does not execute arbitrary remote code.
    if s['targets']['BBPI4']['status']!='confirmed': return 'enroll-bbpi4-via-outbound-controller'
    if s['targets']['Aurum-Morris']['status']!='confirmed': return 'enroll-morris-via-outbound-controller'
    return 'slush-repo-ingest'

def main():
    s=load_state();s['cycle']=int(s.get('cycle',0))+1
    try:
        c=controller_status()
        s['last_controller_status']={'ok':True,'node':c.get('node'),'status':c.get('status'),'events':c.get('events'),'time':int(time.time())}
        event('controller-heartbeat',s['last_controller_status'])
    except Exception as e:
        s['last_controller_status']={'ok':False,'error':type(e).__name__,'time':int(time.time())}
        event('controller-heartbeat-failed',s['last_controller_status'])
    s['next']=choose_next(s)
    s['updated_at']=int(time.time())
    event('cycle-checkpoint',{'cycle':s['cycle'],'next':s['next']})
    save_state(s)
    print(json.dumps(s,indent=2,sort_keys=True))

if __name__=='__main__': main()
