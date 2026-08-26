"""Verify the bounded Debian source recipe behind the Pi3 protected paths.

The verifier consumes only sealed receipts and downloaded bytes.  It parses the
official clear-signed .dsc, validates its archive hashes, inventories the quilt
series, and proves whether any patch names a protected USBNet/URB path.  It does
not compile source, trust an unprovided signer key, contact hardware, or grant
kernel, mutation, binding, or promotion authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.pi3.source-package-recipe-provenance.v1"
STATE = "official-source-recipe-protected-paths-proven"
QUARANTINE_STATE = "source-package-recipe-provenance-quarantined"
MANIFEST_SCHEMA = "aurum.pi3.source-package-recipe-manifest.v1"
UPSTREAM_SCHEMA = "aurum.pi3.source-package-provenance.v1"
UPSTREAM_STATE = "running-package-protected-source-bound-to-rpi-git"
SOURCE_VERSION = "1:6.18.34-1+rpt1"
RPI_COMMIT = "16f1da3c4e94437449d6aa151589ca0ad4b388bb"
PROTECTED_PATHS = ("drivers/net/usb/usbnet.c", "drivers/usb/core/urb.c")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed",
    "register_write_allowed", "interrupt_ack_write_allowed",
    "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed",
    "promotion_allowed", "write_authority",
)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_seal(value: Mapping[str, Any], label: str) -> None:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        raise ValueError(f"{label} is not sealed")
    body = dict(value)
    body.pop("receipt_sha256", None)
    if claimed != canonical_sha256(body):
        raise ValueError(f"{label} seal mismatch")


def require_false(value: object, label: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} authority is malformed")
    for key in AUTHORITY_FALSE:
        if value.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def validate_upstream(value: Mapping[str, Any]) -> None:
    if value.get("schema") != UPSTREAM_SCHEMA or value.get("state") != UPSTREAM_STATE:
        raise ValueError("protected-path provenance has the wrong schema/state")
    verify_seal(value, "protected-path provenance")
    require_false(value.get("authority"), "protected-path provenance")
    if value.get("mismatch_count") != 0 or value.get("protected_source_path_binding_proven") is not True:
        raise ValueError("protected-path provenance is not a clean passed receipt")
    if value.get("full_source_package_git_commit_binding_proven") is not False:
        raise ValueError("upstream receipt unexpectedly claims full-tree Git binding")
    target = value.get("target")
    rpi = value.get("raspberry_pi_reference")
    if not isinstance(target, Mapping) or target.get("source_version") != SOURCE_VERSION:
        raise ValueError("protected-path provenance source version moved")
    if not isinstance(rpi, Mapping) or rpi.get("commit") != RPI_COMMIT:
        raise ValueError("protected-path provenance Raspberry Pi commit moved")


def validate_manifest(value: Mapping[str, Any]) -> None:
    if value.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("source-recipe manifest schema mismatch")
    target = value.get("target")
    dsc = value.get("dsc")
    archives = value.get("archives")
    quilt = value.get("quilt")
    protected = value.get("protected_sources")
    if not all(isinstance(item, Mapping) for item in (target, dsc, archives, quilt, protected)):
        raise ValueError("source-recipe manifest is malformed")
    if target != {"source_package": "linux", "source_version": SOURCE_VERSION}:
        raise ValueError("source-recipe manifest target moved")
    if tuple(quilt.get("protected_paths", ())) != PROTECTED_PATHS:
        raise ValueError("source-recipe protected path set moved")
    if set(protected) != set(PROTECTED_PATHS):
        raise ValueError("source-recipe protected hashes are incomplete")
    for digest in list(protected.values()) + [dsc.get("sha256"), quilt.get("series_sha256"), quilt.get("inventory_sha256")]:
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ValueError("source-recipe manifest contains an invalid SHA-256")
    if not isinstance(archives, Mapping) or set(archives) != {"orig", "debian"}:
        raise ValueError("source-recipe archive set must be orig plus debian")
    for item in archives.values():
        if not isinstance(item, Mapping) or not HEX64.fullmatch(str(item.get("sha256", ""))):
            raise ValueError("source-recipe archive digest is invalid")
        if not isinstance(item.get("size"), int) or item["size"] <= 0:
            raise ValueError("source-recipe archive size is invalid")


def _clearsigned_parts(data: bytes) -> tuple[bytes, bytes]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(".dsc is not UTF-8 clear-signed text") from exc
    begin = "-----BEGIN PGP SIGNED MESSAGE-----"
    sig_begin = "-----BEGIN PGP SIGNATURE-----"
    sig_end = "-----END PGP SIGNATURE-----"
    if not text.startswith(begin) or sig_begin not in text or sig_end not in text:
        raise ValueError(".dsc clear-signature envelope is missing")
    signed_head, signature_tail = text.split(sig_begin, 1)
    header_end = signed_head.find("\n\n")
    if header_end < 0:
        raise ValueError(".dsc clear-signature header is malformed")
    payload = signed_head[header_end + 2:].rstrip("\r\n") + "\n"
    payload = "\n".join(line[2:] if line.startswith("- ") else line for line in payload.splitlines()) + "\n"
    signature = sig_begin + signature_tail.split(sig_end, 1)[0] + sig_end + "\n"
    return payload.encode("utf-8"), signature.encode("ascii")


def _packet_body(data: bytes) -> tuple[int, bytes]:
    if not data or not data[0] & 0x80:
        raise ValueError("OpenPGP signature packet is malformed")
    head = data[0]
    index = 1
    if head & 0x40:
        tag = head & 0x3F
        first = data[index]
        index += 1
        if first < 192:
            length = first
        elif first < 224:
            length = ((first - 192) << 8) + data[index] + 192
            index += 1
        elif first == 255:
            length = int.from_bytes(data[index:index + 4], "big")
            index += 4
        else:
            raise ValueError("partial OpenPGP packet lengths are not accepted")
    else:
        tag = (head >> 2) & 0x0F
        length_type = head & 0x03
        width = (1, 2, 4)[length_type] if length_type < 3 else None
        if width is None:
            raise ValueError("indeterminate OpenPGP packet lengths are not accepted")
        length = int.from_bytes(data[index:index + width], "big")
        index += width
    body = data[index:index + length]
    if tag != 2 or len(body) != length:
        raise ValueError("expected one complete OpenPGP signature packet")
    return tag, body


def _subpackets(data: bytes) -> list[tuple[int, bytes]]:
    result: list[tuple[int, bytes]] = []
    index = 0
    while index < len(data):
        first = data[index]
        index += 1
        if first < 192:
            length = first
        elif first < 255:
            length = ((first - 192) << 8) + data[index] + 192
            index += 1
        else:
            length = int.from_bytes(data[index:index + 4], "big")
            index += 4
        packet = data[index:index + length]
        index += length
        if not packet or index > len(data):
            raise ValueError("OpenPGP signature subpacket is malformed")
        result.append((packet[0] & 0x7F, packet[1:]))
    return result


def signature_metadata(armor: bytes) -> dict[str, Any]:
    lines = armor.decode("ascii").splitlines()
    encoded = "".join(
        line.strip() for line in lines
        if line and not line.startswith("-----") and not line.startswith(("Version:", "Comment:", "="))
    )
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("OpenPGP signature armor is invalid") from exc
    _, body = _packet_body(raw)
    if len(body) < 8 or body[0] != 4:
        raise ValueError("only OpenPGP v4 signatures are accepted")
    public_key_algorithm = body[2]
    hash_algorithm = body[3]
    hashed_length = int.from_bytes(body[4:6], "big")
    hashed = body[6:6 + hashed_length]
    cursor = 6 + hashed_length
    unhashed_length = int.from_bytes(body[cursor:cursor + 2], "big")
    unhashed = body[cursor + 2:cursor + 2 + unhashed_length]
    fingerprints = []
    for packet_type, packet in _subpackets(hashed) + _subpackets(unhashed):
        if packet_type == 33 and len(packet) == 21 and packet[0] == 4:
            fingerprints.append(packet[1:].hex().upper())
    if len(set(fingerprints)) != 1:
        raise ValueError("OpenPGP signature issuer fingerprint is missing or ambiguous")
    return {
        "issuer_fingerprint": fingerprints[0],
        "public_key_algorithm": public_key_algorithm,
        "hash_algorithm": hash_algorithm,
        "signature_packet_sha256": sha256(raw),
    }


def _control_fields(payload: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for raw in payload.decode("utf-8").splitlines():
        if raw.startswith((" ", "\t")) and current:
            fields[current] += "\n" + raw.strip()
        elif ":" in raw:
            current, content = raw.split(":", 1)
            fields[current] = content.strip()
        elif raw:
            raise ValueError(".dsc control field is malformed")
    return fields


def _checksum_entries(text: str) -> dict[str, tuple[str, int]]:
    entries: dict[str, tuple[str, int]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 3 or not HEX64.fullmatch(parts[0]):
            raise ValueError(".dsc Checksums-Sha256 entry is malformed")
        entries[parts[2]] = (parts[0], int(parts[1]))
    return entries


def _read_members(archive: bytes, names: set[str], *, suffix: bool = False) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r|xz") as bundle:
            for member in bundle:
                normalized = member.name.removeprefix("./")
                matched = next((name for name in names if normalized == name or (suffix and normalized.endswith("/" + name))), None)
                if matched is None:
                    continue
                if not member.isfile():
                    raise ValueError(f"archive member {member.name} is not a regular file")
                handle = bundle.extractfile(member)
                if handle is None:
                    raise ValueError(f"archive member {member.name} cannot be read")
                found[matched] = handle.read()
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise ValueError("source archive is not a valid xz-compressed tar") from exc
    if set(found) != names:
        raise ValueError(f"source archive members are incomplete: {sorted(names - set(found))}")
    return found


def _patch_paths(data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("quilt patch is not UTF-8 text") from exc
    paths: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"diff --git a/(.+) b/(.+)$", line)
        if match:
            paths.update(match.groups())
            continue
        if line.startswith(("--- ", "+++ ")):
            path = line[4:].split("\t", 1)[0].split(" ", 1)[0]
            if path == "/dev/null":
                continue
            if path.startswith(("a/", "b/")):
                path = path[2:]
            paths.add(path)
    return sorted(paths)


def _hits(paths: list[str]) -> list[str]:
    return sorted({
        protected for protected in PROTECTED_PATHS
        if any(path == protected or path.endswith("/" + protected) for path in paths)
    })


def _inventory(debian_archive: bytes, series_path: str) -> tuple[bytes, list[dict[str, Any]]]:
    series = _read_members(debian_archive, {series_path})[series_path]
    try:
        entries = [
            line.strip().split()[0] for line in series.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except UnicodeDecodeError as exc:
        raise ValueError("quilt series is not UTF-8 text") from exc
    if len(entries) != len(set(entries)) or any(path.startswith("/") or ".." in Path(path).parts for path in entries):
        raise ValueError("quilt series contains duplicate or unsafe patch paths")
    member_names = {"debian/patches/" + path for path in entries}
    patches = _read_members(debian_archive, member_names)
    inventory = []
    for path in entries:
        data = patches["debian/patches/" + path]
        touched = _patch_paths(data)
        inventory.append({
            "path": path,
            "sha256": sha256(data),
            "size": len(data),
            "touched_path_count": len(touched),
            "touched_paths_sha256": canonical_sha256(touched),
            "protected_hits": _hits(touched),
        })
    return series, inventory


def run_recipe_provenance(
    *, upstream: Mapping[str, Any], manifest: Mapping[str, Any], dsc_bytes: bytes,
    orig_archive: bytes, debian_archive: bytes,
) -> dict[str, Any]:
    validate_upstream(upstream)
    validate_manifest(manifest)
    dsc_manifest = manifest["dsc"]
    archives = manifest["archives"]
    quilt = manifest["quilt"]
    mismatches: list[str] = []
    for label, data, expected in (
        ("dsc", dsc_bytes, dsc_manifest),
        ("orig", orig_archive, archives["orig"]),
        ("debian", debian_archive, archives["debian"]),
    ):
        if len(data) != expected["size"] or sha256(data) != expected["sha256"]:
            raise ValueError(f"{label} source input differs from its immutable size/hash")

    payload, signature = _clearsigned_parts(dsc_bytes)
    fields = _control_fields(payload)
    sig = signature_metadata(signature)
    if fields.get("Format") != dsc_manifest["format"] or fields.get("Source") != "linux":
        raise ValueError(".dsc source format/name moved")
    if fields.get("Version") != SOURCE_VERSION:
        raise ValueError(".dsc source version moved")
    if fields.get("Vcs-Git") != dsc_manifest["vcs_git"]:
        raise ValueError(".dsc Vcs-Git moved")
    if sig["issuer_fingerprint"] != dsc_manifest["signature_issuer_fingerprint"]:
        raise ValueError(".dsc signature issuer fingerprint moved")
    expected_checksums = {
        item["filename"]: (item["sha256"], item["size"])
        for item in archives.values()
    }
    if _checksum_entries(fields.get("Checksums-Sha256", "")) != expected_checksums:
        raise ValueError(".dsc archive checksum set moved")

    protected = _read_members(orig_archive, set(PROTECTED_PATHS), suffix=True)
    for path in PROTECTED_PATHS:
        if sha256(protected[path]) != manifest["protected_sources"][path]:
            mismatches.append(f"orig:{path}:hash-mismatch")
    series, inventory = _inventory(debian_archive, quilt["series_path"])
    if len(series) != quilt["series_size"] or sha256(series) != quilt["series_sha256"]:
        raise ValueError("quilt series bytes moved")
    if len(inventory) != quilt["entry_count"] or canonical_sha256(inventory) != quilt["inventory_sha256"]:
        raise ValueError("quilt patch inventory moved")
    protected_hits = [
        {"patch": item["path"], "paths": item["protected_hits"]}
        for item in inventory if item["protected_hits"]
    ]
    if protected_hits:
        mismatches.extend(f"quilt:{item['patch']}:touches-protected-path" for item in protected_hits)

    passed = not mismatches
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if passed else QUARANTINE_STATE,
        "target": dict(manifest["target"]),
        "upstream_provenance_receipt_sha256": upstream["receipt_sha256"],
        "dsc": {
            "url": dsc_manifest["url"], "sha256": sha256(dsc_bytes), "size": len(dsc_bytes),
            "format": fields["Format"], "vcs_git": fields["Vcs-Git"],
            "clear_signature_present": True, **sig,
            "signature_cryptographically_verified": False,
            "signer_key_trust_anchored": False,
        },
        "archives": {
            name: {"filename": item["filename"], "sha256": sha256(data), "size": len(data), "dsc_checksum_matches": True}
            for name, item, data in (
                ("orig", archives["orig"], orig_archive),
                ("debian", archives["debian"], debian_archive),
            )
        },
        "quilt": {
            "series_path": quilt["series_path"], "series_sha256": sha256(series),
            "entry_count": len(inventory), "inventory_sha256": canonical_sha256(inventory),
            "protected_patch_hits": protected_hits,
            "protected_paths_unmodified_by_series": not protected_hits,
        },
        "orig_protected_sources": {
            path: {"sha256": sha256(protected[path]), "matches_pinned_raspberry_pi_source": sha256(protected[path]) == manifest["protected_sources"][path]}
            for path in PROTECTED_PATHS
        },
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "protected_path_source_recipe_binding_proven": passed,
        "dsc_signer_key_trust_binding_proven": False,
        "full_source_package_git_commit_binding_proven": False,
        "whole_tree_build_recipe_equivalence_proven": False,
        "held_claims": [
            "dsc-signer-key-trust-not-anchored",
            "full-source-package-to-git-commit-equivalence-not-proven",
            "whole-tree-build-reproducibility-not-proven",
        ],
        "invariants": {
            "live_pi_contacted": False, "qpu_contacted": False,
            "source_compiled_or_executed": False, "usb_device_opened": False,
            "usb_transfer_submitted": False, "register_access_performed": False,
            "kernel_code_executed": False, "driver_binding_changed": False,
        },
        "authority": {key: False for key in AUTHORITY_FALSE},
        "strongest_claim": (
            "The exact clear-signed .dsc bytes served by the official Raspberry Pi archive pin an orig tar and "
            "Debian quilt tar whose immutable hashes and sizes match. The orig archive contains the two protected "
            "USBNet/URB files at the pinned Raspberry Pi hashes, and no patch in the exact quilt inventory names "
            "either protected path. Signer-key trust, whole-tree Git equivalence, and build reproducibility remain held."
            if passed else
            "The bounded source recipe does not preserve every protected path; the evidence is quarantined and grants no authority."
        ),
        "next_safe_gate": "trusted-dsc-signer-key-or-whole-tree-reproducible-build-provenance",
    }
    body["receipt_sha256"] = canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dsc", type=Path, required=True)
    parser.add_argument("--orig-archive", type=Path, required=True)
    parser.add_argument("--debian-archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_recipe_provenance(
        upstream=json.loads(args.upstream.read_text(encoding="utf-8-sig")),
        manifest=json.loads(args.manifest.read_text(encoding="utf-8-sig")),
        dsc_bytes=args.dsc.read_bytes(), orig_archive=args.orig_archive.read_bytes(),
        debian_archive=args.debian_archive.read_bytes(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"AURUM_PI3_SOURCE_RECIPE state={result['state']} mismatches={result['mismatch_count']} receipt_sha256={result['receipt_sha256']} signer_trust=false whole_tree=false write_authority=false")
    return 0 if result["state"] == STATE else 2


if __name__ == "__main__":
    raise SystemExit(main())
