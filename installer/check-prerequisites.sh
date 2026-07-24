#!/usr/bin/env sh

set -u

missing=""

for command_name in git python3 flutter; do
  if command -v "$command_name" >/dev/null 2>&1; then
    version=$("$command_name" --version 2>&1 | head -n 1)
    printf '[found]   %s: %s\n' "$command_name" "$version"
  else
    printf '[missing] %s\n' "$command_name"
    missing="$missing $command_name"
  fi
done

if [ -n "$missing" ]; then
  printf '\nMissing prerequisites:%s\nNo changes were made.\n' "$missing"
  exit 1
fi

printf '\nAll base prerequisites are available. No changes were made.\n'

