#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED={"TR8:WEB","TR8:FILES","TR8:MEDIA","TR8:WRITE","TR8:INTENT","TR8:CONNECT","TR8:RECOVER"}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--manifest", default=str(Path(__file__).with_name("traits.json"))); p.add_argument("--trait"); a=p.parse_args()
    data=json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    if data.get("schema")!="aurum-human-traits-v1": raise SystemExit("unexpected trait schema")
    by_id={x.get("id"):x for x in data.get("traits",[]) if isinstance(x,dict)}
    missing=REQUIRED-set(by_id)
    if missing: raise SystemExit("missing mandatory seed traits: "+", ".join(sorted(missing)))
    targets=[a.trait] if a.trait else sorted(REQUIRED)
    for tid in targets:
        t=by_id.get(tid)
        if not t or not t.get("goal") or not t.get("human_aliases") or not t.get("compatibility_providers"):
            raise SystemExit(f"{tid}: incomplete staged implementation contract")
    print("AURUM_TRAITS_OK complete_seed_contract=true traits="+",".join(targets))
    return 0
if __name__=="__main__": raise SystemExit(main())
