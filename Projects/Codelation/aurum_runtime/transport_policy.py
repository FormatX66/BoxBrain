#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Transport:
    name: str
    endpoint: str
    kind: str
    available: bool
    authenticated: bool
    cost: int
    risk: int
    latency_rank: int


def choose_transport(transports: Iterable[Transport]) -> Transport | None:
    viable = [t for t in transports if t.available and t.authenticated]
    if not viable:
        return None
    return sorted(viable, key=lambda t: (t.risk, t.cost, t.latency_rank, t.name))[0]


def bbpi4_candidates() -> tuple[Transport, ...]:
    return (
        Transport('usb-c-ssh','kali@10.12.194.1:22','ssh',False,True,1,0,0),
        Transport('usb-ap-ssh','kali@10.42.194.1:22','ssh',False,True,1,0,1),
        Transport('lan-ssh','kali@192.168.0.194:22','ssh',False,True,1,0,2),
        Transport('mdns-http','http://bbpi4.local/','http',False,False,1,0,3),
        Transport('boxbrain-local','http://boxbrain.local/','http',False,False,1,0,4),
        Transport('controller-pull','boxbrain-controller','pull',False,True,2,0,5),
        Transport('hive-relay','slush-delta','hive',False,True,2,0,6),
    )
