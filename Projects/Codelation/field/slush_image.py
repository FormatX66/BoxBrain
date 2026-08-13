from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import BinaryIO

from slush_media import MediaRegion, SlushMediaError, SlushMediaPlan

SECTOR_BYTES = 512
MBR_SIGNATURE = b"\x55\xaa"
PARTITION_TABLE_OFFSET = 446
PARTITION_ENTRY_BYTES = 16
FAT32_LBA_TYPE = 0x0C
AURUM_SLUSH_RAW_TYPE = 0xDA
ANCHOR_BYTES = 4096
ANCHOR_MAGIC = b"AURSLH0\x00"
ANCHOR_VERSION = 0


@dataclass(frozen=True)
class SlushImageEvidence:
    path: str
    logical_bytes: int
    boot_offset: int
    boot_bytes: int
    slush_offset: int
    slush_bytes: int
    plan_identity: str
    primary_anchor_digest: str
    mirror_anchor_digest: str


def _region(plan: SlushMediaPlan, owner: str) -> MediaRegion:
    matches = [region for region in plan.regions if region.semantic_owner == owner]
    if len(matches) != 1:
        raise SlushMediaError(f"expected exactly one {owner} region")
    return matches[0]


def _lba(value: int) -> int:
    if value % SECTOR_BYTES:
        raise SlushMediaError("media region is not sector aligned")
    return value // SECTOR_BYTES


def _partition_entry(*, start: int, size: int, type_code: int) -> bytes:
    first_lba = _lba(start)
    sectors = _lba(size)
    if first_lba <= 0 or sectors <= 0:
        raise SlushMediaError("partition start and size must be positive")
    if first_lba > 0xFFFFFFFF or sectors > 0xFFFFFFFF:
        raise SlushMediaError("v0 MBR image exceeds 32-bit LBA range")
    # CHS fields are compatibility placeholders. LBA fields are authoritative.
    return (
        b"\x00"
        + b"\xfe\xff\xff"
        + bytes([type_code])
        + b"\xfe\xff\xff"
        + struct.pack("<II", first_lba, sectors)
    )


def build_mbr(plan: SlushMediaPlan) -> bytes:
    boot = _region(plan, "compatibility-shim")
    slush = _region(plan, "aurum-slush")
    sector = bytearray(SECTOR_BYTES)
    sector[PARTITION_TABLE_OFFSET : PARTITION_TABLE_OFFSET + PARTITION_ENTRY_BYTES] = _partition_entry(
        start=boot.offset,
        size=boot.size,
        type_code=FAT32_LBA_TYPE,
    )
    second = PARTITION_TABLE_OFFSET + PARTITION_ENTRY_BYTES
    sector[second : second + PARTITION_ENTRY_BYTES] = _partition_entry(
        start=slush.offset,
        size=slush.size - (slush.size % SECTOR_BYTES),
        type_code=AURUM_SLUSH_RAW_TYPE,
    )
    sector[-2:] = MBR_SIGNATURE
    return bytes(sector)


def build_slush_anchor(plan: SlushMediaPlan, *, mirror: bool) -> bytes:
    slush = _region(plan, "aurum-slush")
    try:
        identity = bytes.fromhex(plan.identity)
    except ValueError as exc:
        raise SlushMediaError("plan identity is not hexadecimal") from exc
    if len(identity) != 32:
        raise SlushMediaError("plan identity must be 32 bytes")

    role = 1 if mirror else 0
    payload = struct.pack(
        "<8sII32sQQII",
        ANCHOR_MAGIC,
        ANCHOR_VERSION,
        role,
        identity,
        slush.offset,
        slush.size,
        SECTOR_BYTES,
        ANCHOR_BYTES,
    )
    digest = hashlib.blake2s(b"AURUM-SLUSH-ANCHOR-0\x00" + payload, digest_size=32).digest()
    anchor = payload + digest
    if len(anchor) > ANCHOR_BYTES:
        raise SlushMediaError("anchor payload exceeds fixed anchor size")
    return anchor.ljust(ANCHOR_BYTES, b"\x00")


def parse_slush_anchor(anchor: bytes) -> dict[str, object]:
    if len(anchor) != ANCHOR_BYTES:
        raise SlushMediaError("anchor has wrong size")
    payload_size = struct.calcsize("<8sII32sQQII")
    payload = anchor[:payload_size]
    digest = anchor[payload_size : payload_size + 32]
    expected = hashlib.blake2s(b"AURUM-SLUSH-ANCHOR-0\x00" + payload, digest_size=32).digest()
    if digest != expected:
        raise SlushMediaError("anchor digest mismatch")
    magic, version, role, identity, offset, size, sector_bytes, anchor_bytes = struct.unpack(
        "<8sII32sQQII", payload
    )
    if magic != ANCHOR_MAGIC or version != ANCHOR_VERSION:
        raise SlushMediaError("unsupported Slush anchor")
    return {
        "mirror": bool(role),
        "plan_identity": identity.hex(),
        "slush_offset": offset,
        "slush_size": size,
        "sector_bytes": sector_bytes,
        "anchor_bytes": anchor_bytes,
    }


def _copy_bounded(source: BinaryIO, target: BinaryIO, maximum: int) -> int:
    copied = 0
    while True:
        chunk = source.read(min(1024 * 1024, maximum - copied))
        if not chunk:
            break
        if copied + len(chunk) > maximum:
            raise SlushMediaError("boot shim image exceeds planned boot region")
        target.write(chunk)
        copied += len(chunk)
        if copied == maximum:
            if source.read(1):
                raise SlushMediaError("boot shim image exceeds planned boot region")
            break
    return copied


def assemble_sparse_image(
    output_path: str | Path,
    plan: SlushMediaPlan,
    *,
    boot_partition_image: str | Path | None = None,
) -> SlushImageEvidence:
    """Create a sparse image file only; this function never opens a block device.

    A separately prepared FAT boot-partition image may be inserted into the
    compatibility region.  If absent, that region remains zero-filled and the
    output is intentionally not bootable yet.
    """
    output = Path(output_path)
    if output.exists():
        raise SlushMediaError("output image already exists")
    boot = _region(plan, "compatibility-shim")
    slush = _region(plan, "aurum-slush")
    if slush.size < ANCHOR_BYTES * 2:
        raise SlushMediaError("Slush region is too small for mirrored anchors")

    primary = build_slush_anchor(plan, mirror=False)
    mirror = build_slush_anchor(plan, mirror=True)

    with output.open("xb") as handle:
        handle.truncate(plan.capacity)
        handle.seek(0)
        handle.write(build_mbr(plan))
        if boot_partition_image is not None:
            handle.seek(boot.offset)
            with Path(boot_partition_image).open("rb") as source:
                _copy_bounded(source, handle, boot.size)
        handle.seek(slush.offset)
        handle.write(primary)
        handle.seek(slush.offset + slush.size - ANCHOR_BYTES)
        handle.write(mirror)
        handle.flush()

    return SlushImageEvidence(
        path=str(output),
        logical_bytes=plan.capacity,
        boot_offset=boot.offset,
        boot_bytes=boot.size,
        slush_offset=slush.offset,
        slush_bytes=slush.size,
        plan_identity=plan.identity,
        primary_anchor_digest=hashlib.blake2s(primary, digest_size=32).hexdigest(),
        mirror_anchor_digest=hashlib.blake2s(mirror, digest_size=32).hexdigest(),
    )


def verify_sparse_image(path: str | Path, plan: SlushMediaPlan) -> SlushImageEvidence:
    image = Path(path)
    if not image.is_file() or image.stat().st_size != plan.capacity:
        raise SlushMediaError("image capacity does not match plan")
    boot = _region(plan, "compatibility-shim")
    slush = _region(plan, "aurum-slush")
    with image.open("rb") as handle:
        mbr = handle.read(SECTOR_BYTES)
        if mbr != build_mbr(plan):
            raise SlushMediaError("image MBR does not match plan")
        handle.seek(slush.offset)
        primary = handle.read(ANCHOR_BYTES)
        handle.seek(slush.offset + slush.size - ANCHOR_BYTES)
        mirror = handle.read(ANCHOR_BYTES)
    first = parse_slush_anchor(primary)
    second = parse_slush_anchor(mirror)
    if first["plan_identity"] != plan.identity or second["plan_identity"] != plan.identity:
        raise SlushMediaError("Slush anchor identity does not match media plan")
    if first["mirror"] or not second["mirror"]:
        raise SlushMediaError("Slush anchor roles are invalid")
    return SlushImageEvidence(
        path=str(image),
        logical_bytes=plan.capacity,
        boot_offset=boot.offset,
        boot_bytes=boot.size,
        slush_offset=slush.offset,
        slush_bytes=slush.size,
        plan_identity=plan.identity,
        primary_anchor_digest=hashlib.blake2s(primary, digest_size=32).hexdigest(),
        mirror_anchor_digest=hashlib.blake2s(mirror, digest_size=32).hexdigest(),
    )


__all__ = [
    "ANCHOR_BYTES",
    "AURUM_SLUSH_RAW_TYPE",
    "FAT32_LBA_TYPE",
    "MBR_SIGNATURE",
    "SECTOR_BYTES",
    "SlushImageEvidence",
    "assemble_sparse_image",
    "build_mbr",
    "build_slush_anchor",
    "parse_slush_anchor",
    "verify_sparse_image",
]
