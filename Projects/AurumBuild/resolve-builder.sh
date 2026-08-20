#!/usr/bin/env bash
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
image=${AURUM_BUILDER_REPOSITORY:-ghcr.io/formatx66/boxbrain/aurum-builder}
attempts=${AURUM_BUILDER_PULL_ATTEMPTS:-60}
revision=$(python3 "$repo_root/Projects/AurumBuild/build_acceleration.py" \
  builder-revision --repo-root "$repo_root")
tag="$image:git-$revision"

for attempt in $(seq 1 "$attempts"); do
  if docker pull "$tag" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq "$attempts" ]; then
    echo "Aurum builder is unavailable after $attempts bounded attempts: $tag" >&2
    exit 1
  fi
  sleep 15
done

digest_ref=$(docker image inspect "$tag" --format '{{json .RepoDigests}}' \
  | python3 -c 'import json, sys
prefix = sys.argv[1] + "@sha256:"
matches = [item for item in json.load(sys.stdin) if item.startswith(prefix)]
if len(matches) != 1:
    raise SystemExit(f"expected one repository digest for {sys.argv[1]}, found {len(matches)}")
print(matches[0])' "$image")
if [[ ! "$digest_ref" =~ ^${image}@sha256:[0-9a-f]{64}$ ]]; then
  echo "Builder did not resolve to an immutable digest: $digest_ref" >&2
  exit 1
fi
observed_revision=$(docker image inspect "$digest_ref" \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')
if [ "$observed_revision" != "$revision" ]; then
  echo "Builder revision label mismatch: expected=$revision observed=$observed_revision" >&2
  exit 1
fi

digest=${digest_ref##*@}
definition_sha256=$(python3 "$repo_root/Projects/AurumBuild/cache_identity.py" hash-files \
  "$repo_root/Projects/AurumBuild/Dockerfile.builder" \
  "$repo_root/Projects/AurumBuild/packages.builder.txt")
printf 'AURUM_BUILDER_RESOLVED revision=%s digest=%s\n' "$revision" "$digest"
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "reference=$digest_ref"
    echo "digest=$digest"
    echo "revision=$revision"
    echo "definition_sha256=$definition_sha256"
  } >> "$GITHUB_OUTPUT"
fi
