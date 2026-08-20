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
