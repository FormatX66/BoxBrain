#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,time,uuid
from dataclasses import dataclass
from typing import Iterable

SCHEMA='aurum.work.v0'


def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def object_id(value):
    return hashlib.sha256(_canon(value)).hexdigest()

@dataclass(frozen=True)
class NodeCapability:
    node_id:str
    capabilities:frozenset[str]

class SlushWorkQueue:
    '''Machine-native work state. Storage adapters persist the returned objects; queue semantics do not depend on files, Git, or transport.'''
    def __init__(self, now=None):
        self._now=now or (lambda:int(time.time()))
        self.work={}

    def submit(self, capability:str, state_delta:dict, *, priority:int=100, reversible:bool=True, provenance:str='Aurum'):
        if not capability or not isinstance(state_delta,dict): raise ValueError('invalid work')
        if reversible is not True: raise ValueError('work must be reversible')
        created=self._now()
        item={
          'schema':SCHEMA,'work_id':uuid.uuid4().hex,'capability':capability,
          'state_delta':state_delta,'priority':int(priority),'status':'ready',
          'lease':None,'created':created,'updated':created,'provenance':provenance,
          'verification':{'reversible':True,'content_addressed':True}
        }
        item['content_id']=object_id({k:v for k,v in item.items() if k not in ('work_id','content_id','lease','status','updated')})
        self.work[item['work_id']]=item
        return dict(item)

    def lease(self,node:NodeCapability, *, ttl:int=60):
        now=self._now(); ttl=max(5,min(int(ttl),3600))
        for item in self.work.values():
            lease=item.get('lease')
            if item['status']=='leased' and lease and lease.get('expires',0)<=now:
                item['status']='ready'; item['lease']=None
        candidates=[w for w in self.work.values() if w['status']=='ready' and w['capability'] in node.capabilities]
        if not candidates: return None
        item=sorted(candidates,key=lambda w:(w['priority'],w['created'],w['work_id']))[0]
        token=uuid.uuid4().hex
        item['status']='leased'; item['lease']={'node_id':node.node_id,'token':token,'expires':now+ttl}; item['updated']=now
        return dict(item)

    def complete(self,work_id:str,node_id:str,token:str,result_delta:dict, *, verified:bool):
        item=self.work[work_id]; lease=item.get('lease') or {}
        if item['status']!='leased' or lease.get('node_id')!=node_id or lease.get('token')!=token: raise PermissionError('invalid lease')
        if lease.get('expires',0)<self._now(): raise TimeoutError('lease expired')
        if verified is not True: raise ValueError('unverified completion')
        result={'work_id':work_id,'node_id':node_id,'result_delta':result_delta,'verified':True,'completed':self._now()}
        result['content_id']=object_id(result)
        item['status']='complete'; item['lease']=None; item['result']=result; item['updated']=self._now()
        return dict(item)

    def state(self):
        return [dict(v) for v in sorted(self.work.values(),key=lambda w:(w['created'],w['work_id']))]
