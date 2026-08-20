# Aurum prepared builder

`Dockerfile.builder` packages only the stable host-side dependencies used by
the Aurum PC ISO and its two mandatory QEMU verification profiles. The Debian
base is digest-pinned. The published image records every resolved Debian
package version in `/usr/share/aurum-builder/dpkg-versions.txt`.

`.github/workflows/aurum-builder.yml` publishes an amd64 image only when the
builder definition changes or a manual dispatch requests a missing image. Its
tag is derived from the most recent builder-infrastructure commit. Existing
tags are never rebuilt in place; PC jobs resolve the tag once and pass the
resulting `@sha256` reference to every downstream job.

The PC workflow mounts a live-build cache whose identity includes the exact
builder digest, architecture, build configuration, and dependency definition.
Source identity remains part of the ISO artifact identity, while source-only
changes do not discard safely reusable downloaded Debian packages. A miss is
always allowed and only costs time. Package indices and live-build stages are
never restored, so security/update resolution remains fresh; only package files
whose names and hashes are revalidated by Debian tooling cross runs. The cache
is staged onto the live-build filesystem and is committed back only after a
successful build, avoiding cross-device hard-link failures and failed-build
contamination.

## Compiler cache

Kernel/native lanes mount `.cache/ccache` at `/cache/ccache`. Cache identity
includes the relevant source/config hash, architecture, compiler version,
dependency definition, and exact builder digest. `ccache` checks compiler
content. A missing or mismatched cache rebuilds and never changes a verifier.

## Distributed evidence and authority

`evidence.py` records source SHA, architecture, builder digest, build-config
hash, artifact SHA-256, provider, lane, result, timestamp, and authority.
Convergence fails closed on any identity mismatch and requires distinct
verifier lanes.

- `BUILD-ONLY`: may create artifacts, never promote.
- `VERIFY-ONLY`: may test artifacts, never promote.
- `PHYSICAL-EVIDENCE`: Hopper/Pi4 observations, never direct promotion.
- `PROMOTION`: only the Aurum convergence gate.

CircleCI configuration is at `.circleci/config.yml`; optional GCP and OCI
setup is under `gcp/` and `oci/`. External providers remain accelerators and
are never dependencies of the GitHub/local verified path.
