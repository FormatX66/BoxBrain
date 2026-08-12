#!/usr/bin/env python3
import argparse, asyncio, ipaddress, json, socket, time
DEFAULT_PORTS=(22,80,443,3000,3389,5985,5986,8000,8080)
def is_allowed_host(value):
    try: ip=ipaddress.ip_address(value)
    except ValueError:
        try: infos=socket.getaddrinfo(value,None,family=socket.AF_INET,type=socket.SOCK_STREAM)
        except socket.gaierror: return False
        return any(is_allowed_host(i[4][0]) for i in infos)
    return ip.is_private or ip.is_link_local or ip.is_loopback
async def probe(host,port,timeout):
    started=time.perf_counter()
    try:
        r,w=await asyncio.wait_for(asyncio.open_connection(host,port),timeout);w.close()
        try: await w.wait_closed()
        except Exception: pass
        return {'host':host,'port':port,'open':True,'latency_ms':round((time.perf_counter()-started)*1000,1)}
    except Exception:return {'host':host,'port':port,'open':False}
async def run(hosts,ports,timeout,concurrency):
    sem=asyncio.Semaphore(concurrency)
    async def one(h,p):
        async with sem:return await probe(h,p,timeout)
    results=await asyncio.gather(*(one(h,p) for h in hosts for p in ports))
    opened=[r for r in results if r.get('open')];by={}
    for r in opened:by.setdefault(r['host'],[]).append(r['port'])
    return {'schema':'aurum.observation.connectivity.v0','kind':'connectivity-observation','hosts':hosts,'ports':list(ports),'open':opened,'services_by_host':{h:sorted(ps) for h,ps in sorted(by.items())},'verification':{'connect_only':True,'private_or_link_local_only':True,'reversible':True}}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('hosts',nargs='+');ap.add_argument('--ports',default=','.join(map(str,DEFAULT_PORTS)));ap.add_argument('--timeout',type=float,default=.7);ap.add_argument('--concurrency',type=int,default=128);a=ap.parse_args()
    hosts=[]
    for h in dict.fromkeys(a.hosts):
        if not is_allowed_host(h):raise SystemExit('refusing non-private target: '+h)
        hosts.append(h)
    ports=tuple(sorted({int(p) for p in a.ports.split(',') if p.strip()}));c=max(1,min(a.concurrency,256));print(json.dumps(asyncio.run(run(hosts,ports,max(.05,a.timeout),c)),separators=(',',':'),sort_keys=True))
if __name__=='__main__':main()
