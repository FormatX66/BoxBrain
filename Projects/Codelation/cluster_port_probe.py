#!/usr/bin/env python3
"""Aurum cluster-safe TCP capability probe.

Scans only explicitly supplied private/link-local targets. Intended for authorized
BoxBrain/Aurum nodes. Produces compact JSON suitable for UAF/Slush merging.
"""
from __future__ import annotations
import argparse, asyncio, ipaddress, json, socket, time
from dataclasses import dataclass, asdict

DEFAULT_PORTS=(22,80,443,3000,3389,5985,5986,8000,8080)

@dataclass
class Hit:
    host:str
    port:int
    open:bool
    latency_ms:float|None
    service:str|None=None

SERVICE={22:'ssh',80:'http',443:'https',3000:'ui',3389:'rdp',5985:'winrm',5986:'winrm-tls',8000:'brainconnect',8080:'ui-alt'}

def allowed_target(value:str)->str:
    try:
        ip=ipaddress.ip_address(value)
        if ip.is_private or ip.is_link_local:
            return value
        raise argparse.ArgumentTypeError('target must be private/link-local')
    except ValueError:
        # Hostnames are allowed only when they resolve exclusively to local addresses.
        try:
            infos=socket.getaddrinfo(value,None,type=socket.SOCK_STREAM)
            addrs={ipaddress.ip_address(i[4][0]) for i in infos}
            if addrs and all(a.is_private or a.is_link_local for a in addrs):
                return value
        except Exception:
            pass
        raise argparse.ArgumentTypeError('hostname did not resolve to private/link-local addresses')

async def probe(host:str,port:int,timeout:float,sem:asyncio.Semaphore)->Hit:
    async with sem:
        t=time.perf_counter()
        try:
            r,w=await asyncio.wait_for(asyncio.open_connection(host,port),timeout)
            ms=(time.perf_counter()-t)*1000
            w.close()
            try: await w.wait_closed()
            except Exception: pass
            return Hit(host,port,True,round(ms,2),SERVICE.get(port))
        except Exception:
            return Hit(host,port,False,None,SERVICE.get(port))

async def run(hosts:list[str],ports:list[int],timeout:float,concurrency:int):
    sem=asyncio.Semaphore(concurrency)
    hits=await asyncio.gather(*(probe(h,p,timeout,sem) for h in hosts for p in ports))
    open_hits=[asdict(h) for h in hits if h.open]
    return {
      'schema':'aurum.capability.probe.v0',
      'capability':'cluster-port-probe',
      'targets':hosts,
      'ports':ports,
      'open':open_hits,
      'summary':{'targets':len(hosts),'ports':len(ports),'open_count':len(open_hits)},
      'verification':{'non_destructive':True,'connect_only':True}
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('targets',nargs='+',type=allowed_target)
    ap.add_argument('--ports',default=','.join(map(str,DEFAULT_PORTS)))
    ap.add_argument('--timeout',type=float,default=.45)
    ap.add_argument('--concurrency',type=int,default=256)
    a=ap.parse_args()
    ports=sorted({int(x) for x in a.ports.split(',') if x.strip() and 0<int(x)<65536})
    print(json.dumps(asyncio.run(run(a.targets,ports,a.timeout,max(1,min(a.concurrency,1024)))),separators=(',',':')))

if __name__=='__main__': main()
