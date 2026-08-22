from datetime import datetime, timedelta, timezone

from Projects.Codelation.computeweave_physical import (
    PHYSICAL_NODE_SCHEMA,
    PHYSICAL_RESULT_SCHEMA,
    assess_node,
    shard_request,
    validate_result,
)


NOW = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)


def node(**overrides):
    payload = {
        "schema": PHYSICAL_NODE_SCHEMA,
        "node": "BBPI4",
        "architecture": "arm64",
        "authorized": True,
        "safe": True,
        "capabilities": ["computeweave-shard-v1", "python"],
        "heartbeat_at": (NOW - timedelta(seconds=20)).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_fresh_authorized_node_is_eligible():
    result = assess_node(node(), architecture="arm64", now=NOW)
    assert result.eligible
    assert result.reasons == ()


def test_stale_node_is_not_eligible():
    result = assess_node(
        node(heartbeat_at=(NOW - timedelta(minutes=10)).isoformat()),
        architecture="arm64",
        now=NOW,
    )
    assert not result.eligible
    assert "stale-heartbeat" in result.reasons


def test_request_contains_no_arbitrary_command_surface():
    request = shard_request(
        request_id="proof-1",
        source_sha="a" * 40,
        seed="computeweave",
        units=32,
        rounds=1000,
        shard_index=1,
        shard_count=4,
        target_node="BBPI4",
        architecture="arm64",
    )
    assert request["operation"] == "computeweave-shard-v1"
    assert "command" not in request
    assert "shell" not in request
    assert request["physical_state_mutation_allowed"] is False


def test_matching_physical_result_validates():
    request = shard_request(
        request_id="proof-2",
        source_sha="b" * 40,
        seed="computeweave",
        units=8,
        rounds=10,
        shard_index=0,
        shard_count=2,
        target_node="BBPI4",
        architecture="arm64",
    )
    result = {
        "schema": PHYSICAL_RESULT_SCHEMA,
        "request_id": "proof-2",
        "source_sha": "b" * 40,
        "node": "BBPI4",
        "physical_state_mutated": False,
        "shard": {
            "schema": "aurum.computeweave-shard.v1",
            "seed": "computeweave",
            "units": 8,
            "rounds": 10,
            "node": "BBPI4",
            "shard_index": 0,
            "shard_count": 2,
            "item_count": 4,
            "items": [],
            "execution_ms": 1.0,
            "verified": True,
        },
    }
    valid, reasons = validate_result(request, result)
    assert valid
    assert reasons == ()


def test_result_from_wrong_node_is_rejected():
    request = shard_request(
        request_id="proof-3",
        source_sha="c" * 40,
        seed="computeweave",
        units=8,
        rounds=10,
        shard_index=0,
        shard_count=2,
        target_node="BBPI4",
        architecture="arm64",
    )
    result = {
        "schema": PHYSICAL_RESULT_SCHEMA,
        "request_id": "proof-3",
        "source_sha": "c" * 40,
        "node": "Hopper",
        "physical_state_mutated": False,
        "shard": {"schema": "aurum.computeweave-shard.v1", "verified": False},
    }
    valid, reasons = validate_result(request, result)
    assert not valid
    assert "node-mismatch" in reasons
