#!/usr/bin/env bash
set -Eeuo pipefail

release_id=${1:-}
case "$release_id" in
  ''|*[!A-Za-z0-9._-]*)
    echo "usage: $0 <release-id>" >&2
    exit 2
    ;;
esac

release_root=${HXY_DIY_RELEASE_ROOT:-/root/hxy-diy-20260811}
target="$release_root/releases/$release_id"
current="$release_root/current"
next="$release_root/.current.next.$$"

for required in MANIFEST.sha256 hxy-server diy-web/dist/index.html admin-react/dist/index.html deploy/diy; do
  if [[ ! -e "$target/$required" ]]; then
    echo "incomplete release: missing $required" >&2
    exit 1
  fi
done

(
  cd "$target"
  sha256sum -c MANIFEST.sha256 >/dev/null
)

ln -s "$target" "$next"
mv -Tf "$next" "$current"
printf '%s\n' "$target"
