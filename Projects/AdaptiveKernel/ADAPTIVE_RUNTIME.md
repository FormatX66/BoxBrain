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

## Preserved Pi3 integration and calibration

`pi3_artifact_adapter.py` implements the first integration layer. It accepts only
a bounded, already-downloaded overnight `samples.jsonl`, records the source file
hash and GitHub artifact identity, converts an evidence window, and seals a second
provenance receipt around the governor result. It has no live collector or
executor. Re-run the canonical final window from the repository root with:

```text
python -m Projects.AdaptiveKernel.pi3_artifact_adapter \
  --samples /path/to/samples.jsonl \
  --artifact-id 9599926710 \
  --artifact-digest sha256:9a79ed658cfa10305de4cd86471420046eba4f8f92658d49aa0ba70c961d0157 \
  --window-size 32 \
  --output Projects/AdaptiveKernel/results/pi3-adaptive-runtime-shadow-32926370691.json
```

The canonical final-window receipt contains 32 accepted samples, zero
quarantines, and a shadow-only recommendation for
`runtime-gen3-opportunistic-v1`. It explicitly records `change_applied=false`,
`live_pi_contacted=false`, and `mutation_authority_granted=false`.

The same preserved artifact has now been calibrated across eleven 32-sample
views in
`results/pi3-adaptive-runtime-calibration-32926370691.json`: ten non-overlapping
windows cover samples 0-319, plus the canonical final window covers 296-327.
The tail therefore overlaps the tenth window by 24 samples and is not counted as
an independent physical run. All eleven windows were quarantine-free and all
eleven independently ranked `runtime-gen3-opportunistic-v1` above the protected
baseline in shadow mode. Maximum window temperature stayed at or below 50.464 C,
minimum available-memory ratio stayed above 0.815, and maximum normalized load
stayed at or below 0.025 in these preserved windows. The calibration replay of
the canonical final window reproduced the existing artifact-shadow receipt hash
`c20da0e9f6ed0914a2b7e89efb8a5e2e615f4dfd1199f0984ab1fab61a31def7`
exactly before the broader window evidence was persisted.

This is **policy-stability evidence for one physical run**, not proof that the
Generation-3 policy should be activated. The next high-value evidence is an
independent physical observation set under meaningfully different load/thermal/
memory conditions so the governor can demonstrate both promotion and refusal/
conservation behavior without active execution. A later active adapter must
still target only a previously proven reversible runtime-tunable API, arm a real
rollback path first, and remain separate from recovery-controller, kernel
replacement, and adaptive-driver mutation authority.

## GitHub-hosted policy processing

`pi3_cloud_policy.py` moves replay and scenario analysis away from the Pi. The
manual `Aurum Pi3 Cloud Policy Processing` workflow verifies the exact GitHub
artifact ID, workflow-run ID, artifact digest, checked-in semantic-result seal,
individual evidence-file hashes, pinned Pi3 identity, rollback hashes, and final
physical invariants. It then evaluates every bounded contiguous window and a
deterministic bootstrap scenario set on a GitHub-hosted runner. The output is a
sealed, zero-authority proposal; the workflow has no SSH, live collector, Pi
address, hardware executor, or mutation path.

QPU routing is evidence based. The current catalog contains four policies, so
exhaustive classical ranking is exact and materially cheaper than a hardware QPU
submission. The receipt therefore records that QPU use was considered and
skipped. A future catalog must reach at least 64 candidates before this lane can
mark QPU exploration eligible, and eligibility still grants no hardware access
or physical-apply authority.

## Hardware and known-driver correlation

`pi3_reference_correlation.py` adds a separate reference-aware lane without
replacing raw empirical testing. The `Aurum Pi3 Reference Correlation` workflow
downloads ten hash-pinned inputs: the official reduced Pi3B Rev 1.2 schematic,
the LAN9514 controller datasheet, Raspberry Pi Linux sources at an immutable
`rpi-6.18.y` commit, and upstream Linux sources at the immutable v6.18 commit.
It compares the Raspberry Pi and upstream `smsc95xx`, `usbnet`, and related
sources, then reconciles their explicit capabilities with the preserved sealed
physical artifact and the compile-only Aurum candidate.

The reduced schematic proves the board class and BCM2837 but does not itself
name LAN9514. The analyzer therefore treats the datasheet as a controller-family
reference until a read-only USB identity receipt proves the controller on this
exact Pi. It likewise refuses to equate a later `rpi-6.18.y` source snapshot with
the running `6.18.34+rpt-rpi-v8` binary without exact package/source provenance.

The earlier Future Branch three-qubit model is retained as a sealed comparison
input. It ranks machine-experiment paths; it is not a Pi3 electrical, kernel, or
driver digital twin. It may guide experiment ordering, but official references
and physical telemetry remain authoritative for hardware claims. This comparison
is small enough for exact classical evaluation, so it performs no QPU submission.
The workflow is GitHub-hosted, has no Pi address or SSH path, and grants no
kernel, driver-binding, boot, firmware, network, or other physical mutation
authority.
