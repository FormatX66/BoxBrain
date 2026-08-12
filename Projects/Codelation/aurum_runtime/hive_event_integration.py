#!/usr/bin/env python3
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class HiveDelta:
    event_id: str
    origin: str
    capability: str
    payload: dict[str,Any]
    provenance: dict[str,Any]
    reversible: bool

def compatible(delta: HiveDelta, known_capabilities:set[str]) -> tuple[bool,str]:
    if not delta.provenance.get("node"):
        return False,"missing-provenance"
    if not delta.reversible:
        return False,"non-reversible"
    if delta.capability not in known_capabilities:
        return False,"unknown-capability"
    return True,"compatible"

def merge_state(state:dict[str,Any], delta:HiveDelta) -> dict[str,Any]:
    ok,reason=compatible(delta,set(state.get("known_capabilities",[])))
    if not ok:
        return {**state,"last_hive_event":{"id":delta.event_id,"status":"rejected","reason":reason}}
    merged=dict(state)
    changes=list(merged.get("hive_changes",[]))
    changes.append({"event_id":delta.event_id,"origin":delta.origin,"capability":delta.capability,"payload":delta.payload})
    merged["hive_changes"]=changes
    merged["last_hive_event"]={"id":delta.event_id,"status":"merged","reason":reason}
    merged["wake_requested"]=True
    return merged
