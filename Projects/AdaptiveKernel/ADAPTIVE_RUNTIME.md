# Shadow-first adaptive runtime governor

`adaptive_runtime.py` is the offline Generation-2/3 governor for bounded
whole-machine speculation. It consumes observation mappings supplied by another
component and emits a deterministic recommendation receipt. It does not collect
from a live machine and contains no kernel, driver, boot, network, firmware, or
recovery-controller operations.

## Evidence window

Each sample names its source with `sample_id` and contains:

- temperature in Celsius and the **current** throttle flag;
- available and total memory;
- one-minute load and CPU count;
- Ethernet carrier, operational state, cumulative RX/TX error and dropped-packet
  counters, and the expected Linux reference-driver name.

Malformed evidence, active throttle, unsafe thermal/load/memory state, lost
Ethernet, any network error or dropped-packet evidence, or a reference-driver
mismatch quarantines the sample and the entire decision window. All four error
and drop counters are required nonnegative integers. Quarantine always recommends
no change. A clean window still needs three distinct samples by default.

## Bounded candidates

The protected baseline always competes with three static candidates:

| Candidate | Generation | Maximum speculative CPU | Maximum speculative memory |
| --- | ---: | ---: | ---: |
| `runtime-gen2-conserve-v1` | 2 | 10% | 10% |
| `runtime-gen2-balanced-v1` | 2 | 25% | 20% |
| `runtime-gen3-opportunistic-v1` | 3 | 40% | 30% |

The catalog is capped at eight policies, 50% speculative CPU, and 35%
speculative memory. Ranking is deterministic. Insufficient evidence or a
baseline win produces `no-change`; another winner produces only
`shadow-change`. Every receipt contains normalized evidence, quarantines,
aggregate metrics, all scores, the protected baseline branch, invariants, and a
canonical SHA-256 seal.

## Execution boundary

Active execution defaults to disabled. This module supplies no system executor.
Even an injected executor is not called unless all of the following are true:

1. the sealed shadow receipt recommends a change;
2. the caller explicitly sets `active=True`;
3. authority is granted for exactly `adaptive-runtime-policy`;
4. that authority is reversible and bound to the exact shadow-receipt hash;
5. rollback target and rollback-receipt SHA-256 metadata are present;
6. the executor reports that rollback was armed before the application result is
   accepted.

This gate does not itself grant authority or prove a real rollback mechanism.

## Integration state and next gate

`pi3_artifact_adapter.py` now implements the first half of that integration. It
accepts only a bounded, already-downloaded overnight `samples.jsonl`, records the
source file hash and GitHub artifact identity, converts the final evidence window,
and seals a second provenance receipt around the governor result. It has no live
collector or executor. Re-run it from the repository root with:

```text
python -m Projects.AdaptiveKernel.pi3_artifact_adapter \
  --samples /path/to/samples.jsonl \
  --artifact-id 9599926710 \
  --artifact-digest sha256:9a79ed658cfa10305de4cd86471420046eba4f8f92658d49aa0ba70c961d0157 \
  --window-size 32 \
  --output Projects/AdaptiveKernel/results/pi3-adaptive-runtime-shadow-32926370691.json
```

The preserved run-32926370691 receipt contains 32 accepted samples, zero
quarantines, and a shadow-only recommendation for
`runtime-gen3-opportunistic-v1`. It explicitly records `change_applied=false`,
`live_pi_contacted=false`, and `mutation_authority_granted=false`.

The next safe step is to publish sealed shadow receipts across multiple preserved
windows for calibration. An active adapter remains a separate later change and
must target only a previously proven reversible runtime-tunable API; it must not
reuse the recovery-controller, kernel replacement, or adaptive-driver candidate
paths.
