#!/usr/bin/env bash
# Read-only reserve check before backups, builds, or release activation.
set -Eeuo pipefail

release_root=${1:-}
minimum_kb=${2:-3145728}
if [[ ! -d "$release_root" || ! "$minimum_kb" =~ ^[1-9][0-9]{0,11}$ ]]; then
  echo "CAPACITY_INVALID: require a release directory and positive KiB reserve" >&2
  exit 2
fi
if ! available_kb=$(LC_ALL=C df -Pk "$release_root" | awk 'NR == 2 {print $4}'); then
  echo "CAPACITY_UNKNOWN: cannot read release filesystem" >&2
  exit 1
fi
if [[ ! "$available_kb" =~ ^[0-9]{1,12}$ ]]; then
  echo "CAPACITY_UNKNOWN: invalid available-space result" >&2
  exit 1
fi
if (( 10#$available_kb < 10#$minimum_kb )); then
  echo "CAPACITY_INSUFFICIENT: available_kb=$available_kb required_kb=$minimum_kb" >&2
  exit 1
fi
echo "CAPACITY_OK: available_kb=$available_kb required_kb=$minimum_kb"
