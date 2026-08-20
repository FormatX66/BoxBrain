#!/usr/bin/env bash
set -euo pipefail

branch=aurum/trunk-v0.01
repo=https://github.com/FormatX66/BoxBrain.git
state=/var/lib/aurum-arm
python_image='docker.io/library/python@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1'
source_sha=${AURUM_SOURCE_SHA:-}

if [ "$(uname -m)" != aarch64 ]; then
  echo 'OCI Aurum verifier requires a native aarch64 node.' >&2
  exit 2
fi
if [ -z "$source_sha" ]; then
  source_sha=$(git ls-remote "$repo" "refs/heads/$branch" | awk '{print $1}')
fi
if [[ ! "$source_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid exact source SHA: $source_sha" >&2
  exit 2
fi

work=$(mktemp -d "$state/work.XXXXXX")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT
git -C "$work" init -q
git -C "$work" remote add origin "$repo"
git -C "$work" fetch -q --depth=1 origin "$source_sha"
git -C "$work" checkout -q --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$source_sha"

output="$state/evidence/$source_sha"
mkdir -p "$output"
podman pull "$python_image" >/dev/null
podman run --rm \
  --arch arm64 \
  -v "$work:/workspace:ro,Z" \
  -v "$output:/evidence:Z" \
  -w /workspace \
  "$python_image" \
  sh -ceu '
    test "$(uname -m)" = aarch64
    python3 -m unittest \
      Projects.Codelation.tests.test_distributed_build \
      Projects.Codelation.tests.test_capacity_mesh \
      Projects.Codelation.tests.test_mesh_efficiency \
      -v
    python3 Projects/AurumBuild/deterministic_bundle.py \
      --output /evidence/arm-selected.tar.gz \
      Projects/AurumBuild Projects/Codelation/field \
      Projects/Codelation/tests/test_distributed_build.py
  '
config_hash=$(python3 "$work/Projects/AurumBuild/cache_identity.py" hash-files \
  "$work/Projects/AurumBuild/Dockerfile.builder" \
  "$work/Projects/AurumBuild/packages.builder.txt" \
  "$work/Projects/Codelation/autobuild/capacity_mesh_policy.json")
python3 "$work/Projects/AurumBuild/evidence.py" record \
  --source-sha "$source_sha" \
  --architecture arm64 \
  --builder-image-digest sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 \
  --build-config-hash "$config_hash" \
  --artifact "$output/arm-selected.tar.gz" \
  --provider oci-arm \
  --lane native-arm-portability \
  --result passed \
  --authority VERIFY-ONLY \
  --output "$output/result.json"
echo "AURUM_OCI_ARM_VERIFIED source_sha=$source_sha evidence=$output/result.json"
