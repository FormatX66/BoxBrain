#!/usr/bin/env python3
import argparse
import asyncio
import ipaddress
import json
import socket
import time

DEFAULT_PORTS = (22, 80, 443, 3000, 3389, 5985, 5986, 8000, 8080)
MAX_CONCURRENCY = 256


def _is_allowed_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.version == 4 and (ip.is_private or ip.is_link_local or ip.is_loopback)


def resolve_allowed_host(value: str) -> tuple[str, ...]:
    """Resolve once and return only private/link-local/loopback IPv4 addresses."""
    if _is_allowed_ip(value):
        return (str(ipaddress.ip_address(value)),)
    try:
        infos = socket.getaddrinfo(
            value,
            None,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return ()
    addresses = {
        info[4][0]
        for info in infos
        if info[4] and _is_allowed_ip(info[4][0])
    }
    return tuple(sorted(addresses, key=ipaddress.ip_address))


def resolve_targets(values: list[str]) -> list[tuple[str, str]]:
    """Return de-duplicated (requested-host, validated-address) probe targets."""
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for host in dict.fromkeys(values):
        addresses = resolve_allowed_host(host)
        if not addresses:
            raise ValueError(f"refusing non-private or unresolved target: {host}")
        for address in addresses:
            item = (host, address)
            if item not in seen:
                seen.add(item)
                targets.append(item)
    return targets


async def probe(label: str, address: str, port: int, timeout: float):
    started = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port), timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return {
            "host": label,
            "address": address,
            "port": port,
            "open": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception:
        return {"host": label, "address": address, "port": port, "open": False}


async def run(targets, ports, timeout, concurrency):
    sem = asyncio.Semaphore(concurrency)

    async def one(label, address, port):
        async with sem:
            return await probe(label, address, port, timeout)

    results = await asyncio.gather(
        *(one(label, address, port) for label, address in targets for port in ports)
    )
    open_results = [result for result in results if result.get("open")]
    by_host: dict[str, set[int]] = {}
    for result in open_results:
        by_host.setdefault(result["host"], set()).add(result["port"])
    resolved: dict[str, list[str]] = {}
    for label, address in targets:
        resolved.setdefault(label, []).append(address)
    return {
        "schema": "aurum.observation.connectivity.v0",
        "kind": "connectivity-observation",
        "hosts": list(resolved),
        "resolved": resolved,
        "ports": list(ports),
        "open": open_results,
        "services_by_host": {
            host: sorted(ports) for host, ports in sorted(by_host.items())
        },
        "verification": {
            "connect_only": True,
            "private_or_link_local_only": True,
            "resolve_once_then_pin": True,
            "reversible": True,
        },
    }


def parse_ports(value: str) -> tuple[int, ...]:
    try:
        ports = tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
    except ValueError as exc:
        raise ValueError("invalid ports") from exc
    if not ports or any(port < 1 or port > 65535 for port in ports):
        raise ValueError("invalid ports")
    return ports


def main():
    parser = argparse.ArgumentParser(
        description="Aurum bounded private-network cluster probe"
    )
    parser.add_argument(
        "hosts", nargs="+", help="Private/link-local IPv4 addresses or local hostnames"
    )
    parser.add_argument("--ports", default=",".join(map(str, DEFAULT_PORTS)))
    parser.add_argument("--timeout", type=float, default=0.7)
    parser.add_argument("--concurrency", type=int, default=128)
    args = parser.parse_args()
    try:
        targets = resolve_targets(args.hosts)
        ports = parse_ports(args.ports)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    concurrency = max(1, min(args.concurrency, MAX_CONCURRENCY))
    result = asyncio.run(run(targets, ports, max(0.05, args.timeout), concurrency))
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
