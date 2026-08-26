"""Lower the sealed USBNet lifecycle graph into a portable zero-authority C candidate."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_usbnet_lifecycle_model import ACTIONS, SCHEMA as LIFECYCLE_SCHEMA

CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-candidate.v1"
DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-differential.v1"
DEFAULT_SEQUENCE_SEED = 0x95146E7
DEFAULT_SEQUENCE_STEPS = 65_536

_REQUIRED_FALSE = (
    "mutation_allowed",
    "device_io_allowed",
    "usb_transfer_allowed",
    "register_write_allowed",
    "interrupt_ack_write_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _validated_graph(lifecycle: Mapping[str, Any]) -> tuple[list[str], dict[tuple[str, str], tuple[str, bool]]]:
    if lifecycle.get("schema") != LIFECYCLE_SCHEMA or not _verify_sealed(lifecycle):
        raise ValueError("lifecycle model must be a valid sealed receipt")
    if lifecycle.get("state") != "verified-offline-usbnet-lifecycle-fault-model":
        raise ValueError("lifecycle model gate has not passed")
    authority = lifecycle.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("lifecycle model authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"lifecycle model must keep {key}=false")
    invariants = lifecycle.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError("lifecycle model invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted", "driver_binding_changed"):
        if invariants.get(key) is not False:
            raise ValueError(f"lifecycle model must keep {key}=false")
    qpu = lifecycle.get("qpu")
    if not isinstance(qpu, Mapping) or qpu.get("used") is not False or qpu.get("hardware_submission_performed") is not False:
        raise ValueError("lifecycle model contains unexpected QPU execution")

    graph = lifecycle.get("graph")
    if not isinstance(graph, Mapping):
        raise ValueError("lifecycle graph is malformed")
    states_raw = graph.get("states")
    transitions_raw = graph.get("transitions")
    if not isinstance(states_raw, list):
        raise ValueError("lifecycle graph states are malformed")
    # Durable receipts omit the transition list intentionally only if they could
    # not be re-executed. This candidate requires the complete graph.
    if transitions_raw is None:
        transitions_raw = lifecycle.get("transition_matrix")
    if not isinstance(transitions_raw, list):
        raise ValueError("lifecycle graph transition matrix is missing")
    state_ids = []
    for item in states_raw:
        if not isinstance(item, Mapping):
            raise ValueError("lifecycle state entry is malformed")
        state_id = item.get("id")
        if not isinstance(state_id, str) or len(state_id) != 8 or set(state_id) - {"0", "1"}:
            raise ValueError("lifecycle state id is malformed")
        state_ids.append(state_id)
    if len(state_ids) != len(set(state_ids)) or graph.get("state_count") != len(state_ids):
        raise ValueError("lifecycle state accounting is inconsistent")
    state_ids.sort()
    known = set(state_ids)
    matrix: dict[tuple[str, str], tuple[str, bool]] = {}
    for item in transitions_raw:
        if not isinstance(item, Mapping):
            raise ValueError("lifecycle transition entry is malformed")
        before, action, after, accepted = item.get("from"), item.get("action"), item.get("to"), item.get("accepted")
        if before not in known or after not in known or action not in ACTIONS or not isinstance(accepted, bool):
            raise ValueError("lifecycle transition entry is outside the sealed graph")
        key = (str(before), str(action))
        if key in matrix:
            raise ValueError("lifecycle transition matrix contains a duplicate")
        matrix[key] = (str(after), accepted)
    expected = len(state_ids) * len(ACTIONS)
    if len(matrix) != expected or graph.get("transition_count") != expected:
        raise ValueError("lifecycle transition matrix is incomplete")
    return state_ids, matrix


def synthesize_lifecycle_candidate(lifecycle: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    state_ids, matrix = _validated_graph(lifecycle)
    indexes = {state_id: index for index, state_id in enumerate(state_ids)}
    next_rows = []
    accepted_rows = []
    for state_id in state_ids:
        next_rows.append(
            "    {" + ", ".join(str(indexes[matrix[(state_id, action)][0]]) for action in ACTIONS) + "}"
        )
        accepted_rows.append(
            "    {" + ", ".join("1" if matrix[(state_id, action)][1] else "0" for action in ACTIONS) + "}"
        )
    next_table = ",\n".join(next_rows)
    accepted_table = ",\n".join(accepted_rows)
    source = f'''/* Aurum generated host-only USBNet lifecycle candidate.
 * ZERO AUTHORITY: table lookup over synthetic state/action indexes only.
 */
#include <stdint.h>

#define AURUM_STATE_COUNT {len(state_ids)}u
#define AURUM_ACTION_COUNT {len(ACTIONS)}u

typedef struct {{
    uint32_t next_state;
    uint32_t accepted;
}} aurum_usbnet_transition_result;

static const uint8_t AURUM_NEXT_STATE[{len(state_ids)}][{len(ACTIONS)}] = {{
{next_table}
}};

static const uint8_t AURUM_ACCEPTED[{len(state_ids)}][{len(ACTIONS)}] = {{
{accepted_table}
}};

int aurum_usbnet_transition(uint32_t state,
                            uint32_t action,
                            aurum_usbnet_transition_result *out) {{
    if (!out || state >= AURUM_STATE_COUNT || action >= AURUM_ACTION_COUNT)
        return -1;
    out->next_state = AURUM_NEXT_STATE[state][action];
    out->accepted = AURUM_ACCEPTED[state][action];
    return 0;
}}
'''
    receipt: dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "state": "synthesized-zero-authority-usbnet-lifecycle-candidate",
        "input_lifecycle_receipt_sha256": lifecycle.get("receipt_sha256"),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "state_ids": state_ids,
        "actions": list(ACTIONS),
        "state_count": len(state_ids),
        "action_count": len(ACTIONS),
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "driver_probe_performed": False,
            "driver_binding_path_present": False,
            "kernel_module_entrypoint_present": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "compiled-complete-transition-and-sequence-differential",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return source, receipt


class CandidateTransition(ctypes.Structure):
    _fields_ = [("next_state", ctypes.c_uint32), ("accepted", ctypes.c_uint32)]


def _compile(source: str, root: Path, cc: str | None = None) -> Path:
    compiler = cc or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("no C compiler available for lifecycle differential verification")
    source_path = root / "lifecycle-candidate.c"
    library_path = root / "lifecycle-candidate.so"
    source_path.write_text(source, encoding="utf-8")
    build = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", str(source_path), "-o", str(library_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError("lifecycle candidate compilation failed:\n" + build.stdout + build.stderr)
    return library_path


def run_lifecycle_differential(
    lifecycle: Mapping[str, Any],
    *,
    cc: str | None = None,
    sequence_seed: int = DEFAULT_SEQUENCE_SEED,
    sequence_steps: int = DEFAULT_SEQUENCE_STEPS,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(sequence_steps, int) or not 0 <= sequence_steps <= 1_000_000:
        raise ValueError("sequence_steps must be between 0 and 1000000")
    state_ids, matrix = _validated_graph(lifecycle)
    source, candidate = synthesize_lifecycle_candidate(lifecycle)
    indexes = {state_id: index for index, state_id in enumerate(state_ids)}
    scenario_hash = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="aurum-usbnet-lifecycle-diff-") as temp_dir:
        library = ctypes.CDLL(str(_compile(source, Path(temp_dir), cc)))
        fn = library.aurum_usbnet_transition
        fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(CandidateTransition)]
        fn.restype = ctypes.c_int

        for state_id in state_ids:
            for action_index, action in enumerate(ACTIONS):
                out = CandidateTransition()
                rc = fn(indexes[state_id], action_index, ctypes.byref(out))
                next_id, accepted = matrix[(state_id, action)]
                observed = (rc, int(out.next_state), bool(out.accepted))
                wanted = (0, indexes[next_id], accepted)
                if observed != wanted:
                    raise ValueError(f"lifecycle transition mismatch: {(state_id, action, observed, wanted)}")
                scenario_hash.update(json.dumps([state_id, action, next_id, accepted], separators=(",", ":")).encode())

        rng = random.Random(sequence_seed)
        state_id = str(lifecycle["graph"]["initial_state"])
        for _ in range(sequence_steps):
            action_index = rng.randrange(len(ACTIONS))
            action = ACTIONS[action_index]
            out = CandidateTransition()
            rc = fn(indexes[state_id], action_index, ctypes.byref(out))
            next_id, accepted = matrix[(state_id, action)]
            observed = (rc, int(out.next_state), bool(out.accepted))
            wanted = (0, indexes[next_id], accepted)
            if observed != wanted:
                raise ValueError(f"lifecycle sequence mismatch: {(state_id, action, observed, wanted)}")
            scenario_hash.update(json.dumps(["sequence", state_id, action, next_id, accepted], separators=(",", ":")).encode())
            state_id = next_id

    transition_scenarios = len(state_ids) * len(ACTIONS)
    result: dict[str, Any] = {
        "schema": DIFFERENTIAL_SCHEMA,
        "state": "controlled-usbnet-lifecycle-candidate-differential-passed",
        "input_lifecycle_receipt_sha256": lifecycle.get("receipt_sha256"),
        "candidate_receipt_sha256": candidate.get("receipt_sha256"),
        "candidate_source_sha256": candidate.get("source_sha256"),
        "complete_transition_scenarios": transition_scenarios,
        "deterministic_sequence_steps": sequence_steps,
        "scenario_count": transition_scenarios + sequence_steps,
        "scenario_matrix_sha256": scenario_hash.hexdigest(),
        "mismatch_count": 0,
        "sequence_seed": sequence_seed,
        "verification": {
            "host_compilation": True,
            "shared_library_execution": True,
            "all_reachable_state_action_pairs": True,
            "accepted_and_refused_transitions": True,
            "deterministic_multi_step_sequences": True,
        },
        "qpu": {
            "preserved_router_available": True,
            "used": False,
            "hardware_submission_performed": False,
            "reason": "The complete finite transition table and deterministic sequences are exactly evaluated classically.",
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "driver_probe_performed": False,
            "driver_binding_changed": False,
            "kernel_module_built": False,
            "kernel_module_loaded": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "nonbinding-userspace-usbnet-event-emulator",
        "strongest_claim": (
            "A portable table-driven C lifecycle candidate matches every sealed reachable USBNet state/action pair and "
            "a deterministic multi-step sequence matrix. It remains a host-only state transform with no USB, kernel, "
            "probe, binding, mutation, or promotion capability."
        ),
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return source, candidate, result


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lifecycle", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cc")
    parser.add_argument("--sequence-seed", type=lambda value: int(value, 0), default=DEFAULT_SEQUENCE_SEED)
    parser.add_argument("--sequence-steps", type=int, default=DEFAULT_SEQUENCE_STEPS)
    args = parser.parse_args()
    source, candidate, differential = run_lifecycle_differential(
        _load(args.lifecycle), cc=args.cc, sequence_seed=args.sequence_seed, sequence_steps=args.sequence_steps
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "usbnet-lifecycle-candidate.c").write_text(source, encoding="utf-8")
    (args.output_dir / "usbnet-lifecycle-candidate.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "usbnet-lifecycle-differential.json").write_text(
        json.dumps(differential, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "AURUM_PI3_SMSC95XX_USBNET_LIFECYCLE_CANDIDATE "
        f"state={differential['state']} scenarios={differential['scenario_count']} "
        "mismatches=0 live_pi_contacted=false mutation_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
