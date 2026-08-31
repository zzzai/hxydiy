#!/usr/bin/env bash
set -Eeuo pipefail

release_id=${1:-}
case "$release_id" in
  ''|*[!A-Za-z0-9._-]*)
    echo "usage: $0 <release-id> [workspace-root]" >&2
    exit 2
    ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workspace_root=${2:-$(cd "$script_dir/../.." && pwd -P)}
release_root=${HXY_DIY_RELEASE_ROOT:-/root/hxy-diy-20260811}
releases_dir="$release_root/releases"
target="$releases_dir/$release_id"
staging="$releases_dir/.${release_id}.tmp.$$"

for required in hxy-server diy-web/dist admin-react/dist deploy/diy; do
  if [[ ! -e "$workspace_root/$required" ]]; then
    echo "missing release input: $workspace_root/$required" >&2
    exit 1
  fi
done

if [[ -e "$target" ]]; then
  echo "release already exists: $target" >&2
  exit 1
fi

mkdir -p "$releases_dir" "$staging/diy-web" "$staging/admin-react" "$staging/hxy-server"
cleanup_staging() {
  rm -rf -- "$staging"
}
trap cleanup_staging EXIT INT TERM

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.db' \
  --exclude='*.db-*' \
  --exclude='.env' \
  --exclude='.env.*' \
  -C "$workspace_root/hxy-server" -cf - . \
  | tar -C "$staging/hxy-server" -xf -
cp -R "$workspace_root/deploy" "$staging/deploy"
cp -R "$workspace_root/diy-web/dist" "$staging/diy-web/dist"
cp -R "$workspace_root/admin-react/dist" "$staging/admin-react/dist"

(
  cd "$staging"
  find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256
  sha256sum -c MANIFEST.sha256 >/dev/null
)

mv "$staging" "$target"
trap - EXIT INT TERM
printf '%s\n' "$target"
