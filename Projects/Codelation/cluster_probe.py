#!/usr/bin/env python3
import argparse, asyncio, ipaddress, json, socket, time

DEFAULT_PORTS = (22, 80, 443, 3000, 3389, 5985, 5986, 8000, 8080)


def is_allowed_host(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        try:
            infos = socket.getaddrinfo(value, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        return any(is_allowed_host(info[4][0]) for info in infos)
    return ip.is_private or ip.is_link_local or ip.is_loopback


async def probe(host: str, port: int, timeout: float):
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return {"host": host, "port": port, "open": True, "latency_ms": round((time.perf_counter()-started)*1000, 1)}
    except Exception:
        return {"host": host, "port": port, "open": False}


async def run(hosts, ports, timeout, concurrency):
    sem = asyncio.Semaphore(concurrency)
    async def one(h, p):
        async with sem:
            return await probe(h, p, timeout)
    results = await asyncio.gather(*(one(h, p) for h in hosts for p in ports))
    open_results = [r for r in results if r.get("open")]
    by_host = {}
    for r in open_results:
        by_host.setdefault(r["host"], []).append(r["port"])
    return {
        "schema": "aurum.observation.connectivity.v0",
        "kind": "connectivity-observation",
        "hosts": hosts,
        "ports": list(ports),
        "open": open_results,
        "services_by_host": {h: sorted(ps) for h, ps in sorted(by_host.items())},
        "verification": {"connect_only": True, "private_or_link_local_only": True, "reversible": True},
    }


def main():
    ap = argparse.ArgumentParser(description="Aurum bounded private-network cluster probe")
    ap.add_argument("hosts", nargs="+", help="Private/link-local IPv4 addresses or local hostnames")
    ap.add_argument("--ports", default=','.join(map(str, DEFAULT_PORTS)))
    ap.add_argument("--timeout", type=float, default=0.7)
    ap.add_argument("--concurrency", type=int, default=128)
    args = ap.parse_args()
    hosts = []
    for host in dict.fromkeys(args.hosts):
        if not is_allowed_host(host):
            raise SystemExit(f"refusing non-private target: {host}")
        hosts.append(host)
    ports = tuple(sorted({int(p) for p in args.ports.split(',') if p.strip()}))
    if not ports or any(p < 1 or p > 65535 for p in ports):
        raise SystemExit("invalid ports")
    concurrency = max(1, min(args.concurrency, 256))
    result = asyncio.run(run(hosts, ports, max(0.05, args.timeout), concurrency))
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))

if __name__ == "__main__":
    main()
