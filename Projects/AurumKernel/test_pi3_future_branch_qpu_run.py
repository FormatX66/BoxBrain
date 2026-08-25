from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Projects" / "AurumKernel" / "pi3_future_branch_qpu_run.py"
SPEC = importlib.util.spec_from_file_location("pi3_future_branch_qpu_run", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CANDIDATE = ROOT / "artifacts" / "aurum-pi3-qpu-run-v0.02.2" / "future-branch-qpu.json"
STATUS = ROOT / "artifacts" / "aurum-pi3-qpu-run-v0.02.2" / "qpu-status.json"
BRANCH_STATE = ROOT / "artifacts" / "aurum-pi3-future-branch-state-v0.02.2.json"
EXPERIMENTS = ROOT / "Projects" / "Aurum" / "Experiments"


def physical_receipt() -> dict:
    return {
        "schema": "aurum-pi3-physical-receipt-v1",
        "captured_at": "2026-08-25T17:00:00+00:00",
        "hostname": "aurum-pi3-kernel",
        "model": "Raspberry Pi 3 Model B Rev 1.2",
        "arch": "aarch64",
        "kernel": MODULE.EXPECTED_KERNEL,
        "cores": 4,
        "ram_mb": 910,
        "boot_id": "11111111-2222-3333-4444-555555555555",
        "interfaces": ["eth0", "lo", "wlan0"],
    }


def test_real_qpu_evidence_passes_complete_physical_collapse() -> None:
    result = MODULE.complete_run(
        candidate_path=CANDIDATE,
        status_path=STATUS,
        branch_state_path=BRANCH_STATE,
        lib_dir=EXPERIMENTS,
        physical_receipt=physical_receipt(),
    )
    assert result["state"] == "success"
    assert result["qpu"]["provider"] == "ibm_quantum"
    assert result["qpu"]["shots"] == 256
    assert result["qpu"]["spearman_rank_correlation"] == 1.0
    assert result["collapse"]["matches_qpu_winner"] is True
    assert set(result["canonical_layers"]) == {
        "reality_gap",
        "gap_stack",
        "surprise_budget",
        "human_availability",
        "unattended_precompute",
        "execution_routes",
    }


def test_tampered_qpu_status_is_rejected(tmp_path: Path) -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    status["counts"]["000"] += 1
    tampered = tmp_path / "qpu-status.json"
    tampered.write_text(json.dumps(status), encoding="utf-8")
    with pytest.raises(ValueError, match="256-shot"):
        MODULE.validate_qpu_evidence(CANDIDATE, tampered, BRANCH_STATE)


def test_wrong_physical_kernel_is_rejected() -> None:
    receipt = physical_receipt()
    receipt["kernel"] = "stock-kernel"
    with pytest.raises(ValueError, match="unexpected kernel"):
        MODULE.complete_run(
            candidate_path=CANDIDATE,
            status_path=STATUS,
            branch_state_path=BRANCH_STATE,
            lib_dir=EXPERIMENTS,
            physical_receipt=receipt,
        )
