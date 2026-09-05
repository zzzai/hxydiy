#!/usr/bin/env bash
# Deploy a release already built and checked by CI. Database schema migrations
# are deliberately blocked here: they require a separately reviewed runbook.
set -Eeuo pipefail

release_id=${1:-}
workspace_root=${2:-}
case "$release_id" in
  ''|*[!A-Za-z0-9._-]*)
    echo "usage: $0 <release-id> <workspace-root>" >&2
    exit 2
    ;;
esac
if [[ -z "$workspace_root" || ! -d "$workspace_root" ]]; then
  echo "workspace root does not exist" >&2
  exit 2
fi

release_root=${HXY_DIY_RELEASE_ROOT:-/root/hxy-diy-20260811}
workspace_root=$(cd "$workspace_root" && pwd -P)
case "$workspace_root" in
  "$release_root"/workspaces/*) ;;
  *)
    echo "workspace must be under $release_root/workspaces" >&2
    exit 2
    ;;
esac

current="$release_root/current"
backups_dir="$release_root/backups"
stable_deploy_dir="$release_root/deploy/diy"
env_file="$stable_deploy_dir/.env"
compose_file="$stable_deploy_dir/docker-compose.hxy.yml"
db_container=${DIY_DB_CONTAINER:-hxy-diy-db}
db_user=${DIY_POSTGRES_USER:-hxy_diy}
db_name=${DIY_POSTGRES_DB:-hxy_diy}
api_health_url=${DIY_API_HEALTH_URL:-https://diy.hexiaoyue.com/api/v1/health}
admin_url=${DIY_ADMIN_URL:-https://diy.hexiaoyue.com/admin/}
customer_url=${DIY_CUSTOMER_URL:-https://diy.hexiaoyue.com/}
previous_release=''
backup_file=''
backup_checksum=''
rehearsal_db=''
compose_backup=''
activated=false
migration_required=false

for required in \
  "$workspace_root/hxy-server/requirements.txt" \
  "$workspace_root/diy-web/dist/index.html" \
  "$workspace_root/admin-react/dist/index.html" \
  "$workspace_root/deploy/diy/create-release.sh" \
  "$workspace_root/deploy/diy/activate-release.sh" \
  "$workspace_root/deploy/diy/docker-compose.hxy.yml" \
  "$env_file"; do
  if [[ ! -f "$required" ]]; then
    echo "missing deployment input: $required" >&2
    exit 1
  fi
done

if [[ -L "$current" || -d "$current" ]]; then
  previous_release=$(readlink -f "$current")
fi
if [[ -z "$previous_release" || ! -d "$previous_release" ]]; then
  echo "current release cannot be resolved" >&2
  exit 1
fi

wait_for_url() {
  local url=$1
  local attempts=${2:-20}
  local delay=${3:-3}
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if curl -fsS --max-time 10 "$url" >/dev/null; then
      return 0
    fi
    sleep "$delay"
  done
  echo "health check failed: $url" >&2
  return 1
}

drop_rehearsal_database() {
  if [[ -n "$rehearsal_db" ]]; then
    docker exec "$db_container" psql -v ON_ERROR_STOP=1 -U "$db_user" -d postgres \
      -c "DROP DATABASE IF EXISTS \"$rehearsal_db\" WITH (FORCE)" >/dev/null || true
    rehearsal_db=''
  fi
}

rollback() {
  local status=$?
  trap - ERR
  set +e
  echo "deployment failed; rolling back release and API container" >&2
  drop_rehearsal_database
  if [[ "$activated" == true && -d "$previous_release" ]]; then
    local rollback_link="$release_root/.current.rollback.$$"
    ln -s "$previous_release" "$rollback_link" && mv -Tf "$rollback_link" "$current"
  fi
  if [[ -n "$compose_backup" && -f "$compose_backup" ]]; then
    cp "$compose_backup" "$compose_file"
  fi
  if [[ "$activated" == true ]]; then
    HXY_DIY_CURRENT="$current" docker compose --env-file "$env_file" -f "$compose_file" up -d --build api
    wait_for_url "$api_health_url" 10 3 || true
  fi
  rm -f -- "$compose_backup"
  exit "$status"
}
trap rollback ERR

mkdir -p "$backups_dir" "$stable_deploy_dir"
backup_file="$backups_dir/pre-${release_id}-$(date -u +%Y%m%dT%H%M%SZ).dump"
backup_checksum="$backup_file.sha256"
docker exec "$db_container" pg_dump -U "$db_user" -Fc "$db_name" > "$backup_file"
sha256sum "$backup_file" > "$backup_checksum"
sha256sum -c "$backup_checksum"

# A real restore rehearsal proves that this backup can be read before release.
rehearsal_suffix=$(printf '%s' "$release_id" | tr -cd 'A-Za-z0-9' | cut -c1-36)
rehearsal_db="hxy_diy_rehearsal_${rehearsal_suffix}"
docker exec "$db_container" psql -v ON_ERROR_STOP=1 -U "$db_user" -d postgres \
  -c "CREATE DATABASE \"$rehearsal_db\"" >/dev/null
docker exec -i "$db_container" pg_restore --exit-on-error -U "$db_user" -d "$rehearsal_db" < "$backup_file"
docker exec "$db_container" psql -v ON_ERROR_STOP=1 -U "$db_user" -d "$rehearsal_db" -c 'SELECT 1' >/dev/null

# Only the reviewed additive membership verification migration is permitted.
# Any removed or unknown revision remains blocked.
if ! diff -q \
  <(find "$previous_release/hxy-server/alembic/versions" -maxdepth 1 -type f -printf '%f\n' | sort) \
  <(find "$workspace_root/hxy-server/alembic/versions" -maxdepth 1 -type f -printf '%f\n' | sort) >/dev/null; then
  mapfile -t added_migrations < <(comm -13 \
    <(find "$previous_release/hxy-server/alembic/versions" -maxdepth 1 -type f -printf '%f\n' | sort) \
    <(find "$workspace_root/hxy-server/alembic/versions" -maxdepth 1 -type f -printf '%f\n' | sort))
  mapfile -t removed_migrations < <(comm -23 \
    <(find "$previous_release/hxy-server/alembic/versions" -maxdepth 1 -type f -printf '%f\n' | sort) \
    <(find "$workspace_root/hxy-server/alembic/versions" -maxdepth 1 -type f -printf '%f\n' | sort))
  if [[ "${#added_migrations[@]}" -ne 1 || "${added_migrations[0]}" != '20260905_membership_verification.py' ||
        "${#removed_migrations[@]}" -ne 0 ]]; then
    echo "Unapproved Alembic migration change detected." >&2
    exit 1
  fi
  migration_required=true
fi

compose_backup=$(mktemp "$release_root/.docker-compose.hxy.yml.XXXXXX")
if [[ -f "$compose_file" ]]; then
  cp "$compose_file" "$compose_backup"
fi
install -m 0644 "$workspace_root/deploy/diy/docker-compose.hxy.yml" "$compose_file"

if [[ "$migration_required" == true ]]; then
  HXY_DIY_CURRENT="$workspace_root" docker compose --env-file "$env_file" -f "$compose_file" build api
  HXY_DIY_CURRENT="$workspace_root" docker compose --env-file "$env_file" -f "$compose_file" run --rm --no-deps \
    api sh -c 'export DATABASE_URL="${DATABASE_URL%/*}/'"$rehearsal_db"'"; alembic upgrade head'
  drop_rehearsal_database
  HXY_DIY_CURRENT="$workspace_root" docker compose --env-file "$env_file" -f "$compose_file" run --rm --no-deps \
    api alembic upgrade head
else
  drop_rehearsal_database
fi

HXY_DIY_RELEASE_ROOT="$release_root" "$workspace_root/deploy/diy/create-release.sh" "$release_id" "$workspace_root"
HXY_DIY_RELEASE_ROOT="$release_root" "$workspace_root/deploy/diy/activate-release.sh" "$release_id"
activated=true

HXY_DIY_CURRENT="$current" docker compose --env-file "$env_file" -f "$compose_file" up -d --build api
wait_for_url "$api_health_url"
wait_for_url "$admin_url"
wait_for_url "$customer_url"

rm -f -- "$compose_backup"
compose_backup=''
trap - ERR
printf 'deployed release=%s previous=%s backup=%s\n' "$release_id" "$previous_release" "$backup_file"
