#!/usr/bin/env python3
"""Server-controlled release entry reusing deploy/diy/deploy-production.sh and its gates.

This is the small reusable server-side entry that replaces GitHub PR/CI as the
mandatory release critical path. GitHub remains an asynchronous mirror and a
secondary check; nothing here installs credentials, pushes, force-pushes, or
claims a mirror completed without a receipt.

Subcommands
-----------
prepare
    Verify a clean, exact-SHA development worktree, preflight free disk and
    memory, materialize an immutable ``git archive`` of the exact SHA into an
    isolated temporary path, build the two frontends serially at low priority
    with locked dependencies while preserving current build flags (staff-learning
    marker and customer base path), then export an immutable release workspace
    under ``<release-root>/workspaces/<release-id>`` with a MANIFEST.sha256 and a
    durable build report. Never deploys and never mutates the source worktree.
inspect  (default)
    Read-only status of prepared workspaces, the current release, pending
    GitHub backup records and the ``server-accepted`` ref. Never builds or
    deploys and never creates directories.
publish
    Consume an exact-SHA coordinator acceptance record, re-verify every gate
    (source SHA, previous/current release, artifact manifest, build report hash,
    structured successful evidence), write a durable attempt receipt before the
    single dispatch, reconcile any existing receipt instead of blindly repeating,
    then dispatch deploy-production.sh exactly once under its existing lock.
    Emits a pending-or-failed GitHub backup record and a locally verified Git
    bundle for recovery while GitHub is pending.
ref-init / ref-show / ref-advance
    Manage ``refs/heads/server-accepted``. ref-init performs an all-zero
    compare-and-swap so it never overwrites a concurrently created ref.
    ref-advance performs a compare-and-swap plus fast-forward and is intended
    for the coordinator only; this entry never calls it implicitly.

The entry reuses the existing create/activate/capacity/backup/restore/
migration/manifest/lock/health/rollback gates through deploy-production.sh and
the deploy/diy scripts; it does not duplicate or weaken them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disk_maintenance as dm  # reuse digest() and validate_root()

try:
    import fcntl
except ImportError:  # pragma: no cover - server entry is Linux-only
    fcntl = None

DEFAULT_ROOT = '/root/hxy-diy-20260811'
DEFAULT_REPO = '/root/hxy-diy-automation'

RELEASE_ID = re.compile(r'server-[0-9a-f]{12}-[0-9]{1,14}')
SHA = re.compile(r'[0-9a-f]{40}')
SHA256 = re.compile(r'[0-9a-f]{64}')
CHECK_ID = re.compile(r'[A-Za-z0-9._-]+')
ACCEPTANCE_SCHEMA = 'server-release-acceptance@1'
BUILD_SCHEMA = 'server-release-build@1'
ATTEMPT_SCHEMA = 'server-release-attempt@1'
PENDING_SCHEMA = 'server-release-pending-github-backup@1'
SERVER_ACCEPTED_REF = 'refs/heads/server-accepted'
ZERO_SHA = '0' * 40
EVIDENCE_MAX_AGE_SECONDS = 7 * 24 * 3600
MIN_FREE_KB_DEFAULT = 3145728  # matches deploy/diy/check-capacity.sh reserve (3 GiB)
MIN_MEMORY_MB_DEFAULT = 1536

# Matches create-release.sh so the immutable export contains the same inputs.
COPY_EXCLUDES = {
    '.git', '.venv', 'node_modules', '__pycache__', '__pycache__/',
    '.env', '.env.example.excluded', '*.pyc', '*.pyo', '*.db', '*.db-*',
}
COPY_EXCLUDED_NAMES = {'.git', '.venv', 'node_modules', '__pycache__', '.env'}
COPY_EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.db'}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def digest_file(path: Path) -> str:
    return dm.digest(path)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_of_text(value: str) -> str:
    return digest_bytes(value.encode('utf-8'))


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + os.urandom(6).hex() + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        if os.name == 'posix':
            os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    temporary.replace(path)


def load_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError('record_missing')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as error:
        raise ValueError('record_not_json') from error
    if not isinstance(value, dict):
        raise ValueError('record_not_object')
    return value


def parse_timestamp(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError('timestamp_invalid')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('timestamp_invalid')
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed


def ensure_root(root: Path) -> Path:
    root = Path(root)
    reject_symlink_ancestors(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('invalid_root')
    for name in ('workspaces', 'releases', 'release-records'):
        path = root / name
        if path.is_symlink():
            raise ValueError('unsafe_directory')
        path.mkdir(parents=True, exist_ok=True)
    return root


def current_release_name(root: Path) -> str:
    return dm.validate_root(root).name


def validate_release_id(release_id: str) -> str:
    if not RELEASE_ID.fullmatch(release_id or ''):
        raise ValueError('invalid_release_id')
    return release_id


def release_id_for_sha(release_id: str, source_sha: str) -> None:
    prefix = 'server-' + source_sha[:12] + '-'
    if not release_id.startswith(prefix):
        raise ValueError('release_id_sha_mismatch')


def reject_symlink_ancestors(path: Path) -> None:
    """Reject any symlink in the path itself or its ancestors."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('symlink_input')
    for ancestor in path.parents:
        if ancestor.is_symlink():
            raise ValueError('symlink_input')


def reject_unsafe_tree(root: Path) -> None:
    """Reject symlinks and non-regular files anywhere under a source tree."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('symlink_input')
    for item in root.rglob('*'):
        if item.is_symlink():
            raise ValueError('symlink_input')
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError('non_regular_input')


# --------------------------------------------------------------------------- #
# prepare: verify, preflight, archive, build, export
# --------------------------------------------------------------------------- #

def verify_source_clean(source: Path, sha: str, run=subprocess.run) -> str:
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('invalid_source')
    if not SHA.fullmatch(sha or ''):
        raise ValueError('invalid_sha')
    git = ['git', '-C', str(source)]
    head = run(git + ['rev-parse', 'HEAD'], check=True,
               capture_output=True, text=True).stdout.strip()
    if head != sha:
        raise ValueError('head_mismatch')
    status = run(git + ['status', '--porcelain'], check=True,
                 capture_output=True, text=True).stdout
    if status.strip():
        raise ValueError('dirty_source')
    return sha


def read_build_settings(root: Path) -> dict:
    """Inspect current build markers and preserve them explicitly.

    A missing marker is ambiguous, not "disabled": refusing to guess keeps an
    active learning feature from being silently turned off by a rebuild.
    """
    current = dm.validate_root(root)
    marker = current / 'admin-react' / 'dist' / 'staff-learning-build.json'
    if marker.exists():
        if marker.is_symlink():
            raise ValueError('unsafe_learning_marker')
        data = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(data.get('enabled'), bool):
            raise ValueError('invalid_learning_marker')
        return {'staff_learning_enabled': data['enabled'],
                'learning_source': 'current-release-marker',
                'customer_base_path': '/'}
    override = os.environ.get('DIY_STAFF_LEARNING_ENABLED')
    if override in ('true', 'false'):
        return {'staff_learning_enabled': override == 'true',
                'learning_source': 'explicit-override',
                'customer_base_path': '/'}
    raise ValueError('learning_marker_missing')


def _run_capture(run, args, **kwargs):
    return run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def build_source(source: Path, sha: str, build_settings: dict,
                 run=subprocess.run) -> dict:
    source = Path(source)
    node = _run_capture(run, ['node', '--version'])
    npm = _run_capture(run, ['npm', '--version'])
    steps = []
    started = time.time()

    def build_app(app_dir: str, env: dict | None = None):
        app = source / app_dir
        if app.is_symlink() or not app.is_dir():
            raise ValueError('missing_frontend_source')
        merged = dict(os.environ)
        merged['NODE_OPTIONS'] = '--max-old-space-size=1024'
        if env:
            merged.update(env)
        # Serial, low-priority, locked-dependency build; one frontend at a time.
        for args in (['npm', 'ci'], ['npm', 'run', 'build']):
            command = ['nice', '-n', '19'] + args
            before = time.time()
            try:
                run(command, cwd=str(app), check=True, env=dict(merged),
                    capture_output=True, text=True, timeout=1800)
                steps.append({'app': app_dir, 'command': ' '.join(command),
                              'exit': 0, 'seconds': round(time.time() - before, 2)})
            except subprocess.CalledProcessError as error:
                steps.append({'app': app_dir, 'command': ' '.join(command),
                              'exit': error.returncode,
                              'seconds': round(time.time() - before, 2),
                              'stderr_tail': (error.stderr or '')[-2000:]})
                raise ValueError('frontend_build_failed')

    build_app('diy-web')
    build_app('admin-react',
              env={'VITE_STAFF_LEARNING_ENABLED':
                   'true' if build_settings['staff_learning_enabled'] else 'false'})

    marker = source / 'admin-react' / 'dist' / 'staff-learning-build.json'
    if marker.parent.is_symlink():
        raise ValueError('unsafe_dist_directory')
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({'enabled': build_settings['staff_learning_enabled'],
                                  'commit': sha}) + '\n', encoding='utf-8')

    return {'node': node, 'npm': npm,
            'staff_learning_enabled': build_settings['staff_learning_enabled'],
            'learning_source': build_settings['learning_source'],
            'customer_base_path': build_settings['customer_base_path'],
            'serial': True, 'locked_dependencies': True,
            'total_seconds': round(time.time() - started, 2), 'steps': steps}


def _should_exclude(relative: Path) -> bool:
    parts = relative.parts
    if any(part in COPY_EXCLUDED_NAMES for part in parts):
        return True
    name = parts[-1]
    if name == '.env' or name.startswith('.env.'):
        return True
    if relative.suffix in COPY_EXCLUDED_SUFFIXES:
        return True
    if '.db-' in name or name.endswith('.db'):
        return True
    return False


def _copy_regular(src_root: Path, dst_root: Path, exclude: bool = False) -> None:
    if src_root.is_symlink():
        raise ValueError('symlink_input')
    for item in src_root.rglob('*'):
        if item.is_symlink():
            raise ValueError('symlink_input')
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError('non_regular_input')
        relative = item.relative_to(src_root)
        if exclude and _should_exclude(relative):
            continue
        target = dst_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def write_manifest(workspace: Path) -> str:
    """Write a create-release.sh-format MANIFEST.sha256 over deploy content."""
    manifest = workspace / 'MANIFEST.sha256'
    deploy_roots = [workspace / name for name in
                    ('hxy-server', 'diy-web', 'admin-react', 'deploy')]
    lines = []
    for root_dir in deploy_roots:
        for item in sorted(root_dir.rglob('*')):
            if item.is_symlink():
                raise ValueError('unsafe_export_file')
            if item.is_dir():
                continue
            if not item.is_file():
                raise ValueError('unsafe_export_file')
            relative = item.relative_to(workspace).as_posix()
            lines.append(digest_file(item) + '  ./' + relative + '\n')
    manifest.write_text(''.join(lines), encoding='utf-8')
    return digest_file(manifest)


def export_workspace(source: Path, sha: str, release_id: str,
                     build_report: dict, root: Path) -> Path:
    source = Path(source)
    root = ensure_root(root)
    validate_release_id(release_id)
    release_id_for_sha(release_id, sha)
    workspace = root / 'workspaces' / release_id
    if workspace.exists() or workspace.is_symlink():
        raise ValueError('workspace_exists')
    if (root / 'releases' / release_id).exists():
        raise ValueError('release_exists')
    for required in ('hxy-server/requirements.txt',
                     'diy-web/dist/index.html',
                     'admin-react/dist/index.html',
                     'deploy/diy/deploy-production.sh',
                     'deploy/diy/create-release.sh',
                     'deploy/diy/activate-release.sh'):
        if (source / required).is_symlink() or not (source / required).is_file():
            raise ValueError('missing_build_output')
    for built in ('diy-web/dist/index.html', 'admin-react/dist/index.html'):
        if (source / built).stat().st_size == 0:
            raise ValueError('empty_build_output')

    staging = root / 'workspaces' / ('.' + release_id + '.tmp.' + os.urandom(6).hex())
    try:
        staging.mkdir(parents=True)
        _copy_regular(source / 'hxy-server', staging / 'hxy-server', exclude=True)
        _copy_regular(source / 'diy-web' / 'dist', staging / 'diy-web' / 'dist')
        _copy_regular(source / 'admin-react' / 'dist', staging / 'admin-react' / 'dist')
        _copy_regular(source / 'deploy', staging / 'deploy')
        (staging / 'evidence').mkdir()
        manifest_sha256 = write_manifest(staging)
        report = {'schema': BUILD_SCHEMA, 'release_id': release_id,
                  'source_sha': sha, 'manifest_sha256': manifest_sha256,
                  'build': build_report,
                  'previous_release': current_release_name(root),
                  'created_at': utcnow(), 'workspace': str(workspace)}
        save_json(staging / 'build-report.json', report)
        os.replace(staging, workspace)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return workspace


def _free_disk_kb(root: Path):
    try:
        return shutil.disk_usage(root).free // 1024
    except OSError:
        return None


def _available_memory_mb():
    try:
        info = Path('/proc/meminfo').read_text(encoding='utf-8')
    except OSError:
        return None
    for line in info.splitlines():
        if line.startswith('MemAvailable:'):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                return int(fields[1]) // 1024
    return None


def preflight_resources(root: Path, free_disk_kb=None,
                        available_memory_mb=None) -> dict:
    """Refuse heavy work before running out of disk or memory mid-build."""
    free_disk_kb = _free_disk_kb(root) if free_disk_kb is None else free_disk_kb
    available_memory_mb = (_available_memory_mb() if available_memory_mb is None
                           else available_memory_mb)
    min_free_kb = int(os.environ.get('DIY_MIN_FREE_KB', MIN_FREE_KB_DEFAULT))
    min_memory_mb = max(MIN_MEMORY_MB_DEFAULT, int(os.environ.get('DIY_MIN_MEMORY_MB', MIN_MEMORY_MB_DEFAULT)))
    if free_disk_kb is None:
        raise ValueError('disk_unknown')
    if available_memory_mb is None:
        raise ValueError('memory_unknown')
    if free_disk_kb < min_free_kb:
        raise ValueError('insufficient_disk')
    if available_memory_mb < min_memory_mb:
        raise ValueError('insufficient_memory')
    return {'free_disk_kb': free_disk_kb, 'available_memory_mb': available_memory_mb,
            'min_free_kb': min_free_kb, 'min_memory_mb': min_memory_mb}


def materialize_archive(source: Path, sha: str, build_dir: Path,
                        run=subprocess.run) -> Path:
    """Extract an immutable ``git archive`` of the exact SHA into build_dir/src."""
    source = Path(source)
    reject_symlink_ancestors(source)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('invalid_source')
    if not SHA.fullmatch(sha or ''):
        raise ValueError('invalid_sha')
    build_dir = Path(build_dir)
    reject_symlink_ancestors(build_dir)
    if not build_dir.is_dir():
        raise ValueError('invalid_build_dir')
    src = build_dir / 'src'
    if src.exists() or src.is_symlink():
        raise ValueError('build_dir_conflict')
    archive = build_dir / 'source.tar'
    run(['git', '-C', str(source), 'archive', '--format=tar',
         '--output', str(archive), sha], check=True, capture_output=True, text=True)
    with tarfile.open(archive) as stream:
        for member in stream:
            if Path(member.name).is_absolute() or '..' in Path(member.name).parts or not (member.isfile() or member.isdir()):
                raise ValueError('unsafe_archive_member')
    src.mkdir(parents=True)
    run(['tar', '-xf', str(archive), '-C', str(src)], check=True,
        capture_output=True, text=True)
    return src


def prepare(root: Path, source: Path, sha: str, release_id: str | None = None,
            run=subprocess.run) -> dict:
    """Verify, preflight, archive-build in isolation, export; never deploy."""
    root = ensure_root(root)
    source = Path(source)
    verify_source_clean(source, sha, run=run)
    settings = read_build_settings(root)
    preflight_resources(root)
    release_id = release_id or ('server-' + sha[:12] + '-' + str(int(time.time())))
    validate_release_id(release_id)
    release_id_for_sha(release_id, sha)
    if (root / 'workspaces' / release_id).exists() or (root / 'releases' / release_id).exists():
        raise ValueError('release_id_exists')
    previous = current_release_name(root)
    build_parent = root / 'workspaces'
    with tempfile.TemporaryDirectory(dir=str(build_parent), prefix='.build-') as tmp:
        build_tree = materialize_archive(source, sha, Path(tmp), run=run)
        reject_unsafe_tree(build_tree)
        tracked = {str(item.relative_to(build_tree)): digest_file(item)
                   for item in build_tree.rglob('*') if item.is_file()}
        build_report = build_source(build_tree, sha, settings, run=run)
        if any(not (build_tree / name).is_file() or digest_file(build_tree / name) != value
               for name, value in tracked.items()):
            raise ValueError('build_modified_tracked_source')
        if current_release_name(root) != previous:
            raise ValueError('current_changed_during_prepare')
        build_report['source_archive_sha256'] = digest_file(Path(tmp) / 'source.tar')
        verify_source_clean(source, sha, run=run)
        export_workspace(build_tree, sha, release_id, build_report, root)
    return read_build_report(root / 'workspaces' / release_id)


# --------------------------------------------------------------------------- #
# inspect
# --------------------------------------------------------------------------- #

def read_build_report(workspace: Path) -> dict:
    report = load_json(workspace / 'build-report.json')
    if report.get('schema') != BUILD_SCHEMA:
        raise ValueError('unknown_build_schema')
    return report


def inspect(root: Path, repo: str | None = None, run=subprocess.run) -> dict:
    root = Path(root)
    reject_symlink_ancestors(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('invalid_root')
    current = current_release_name(root)
    workspaces = []
    workspaces_dir = root / 'workspaces'
    if workspaces_dir.is_dir() and not workspaces_dir.is_symlink():
        for entry in sorted(workspaces_dir.iterdir()):
            if entry.name.startswith('.') or not entry.is_dir() or entry.is_symlink():
                continue
            try:
                report = read_build_report(entry)
                workspaces.append({'release_id': entry.name,
                                   'source_sha': report['source_sha'],
                                   'created_at': report['created_at']})
            except (ValueError, KeyError):
                workspaces.append({'release_id': entry.name, 'state': 'incomplete'})
    pending = []
    records = root / 'release-records'
    if records.is_dir() and not records.is_symlink():
        for entry in sorted(records.glob('pending-github-backup-*.json')):
            try:
                pending.append(load_json(entry))
            except ValueError:
                continue
    accepted = None
    if repo:
        try:
            accepted = show_accepted_ref(repo, run=run)
        except (ValueError, subprocess.CalledProcessError):
            accepted = None
    return {'current': current, 'prepared_workspaces': workspaces,
            'pending_github_backup': pending, 'server_accepted': accepted}


# --------------------------------------------------------------------------- #
# acceptance record and evidence
# --------------------------------------------------------------------------- #

def validate_acceptance(record: dict, current_name: str) -> dict:
    if not isinstance(record, dict):
        raise ValueError('acceptance_not_object')
    if record.get('schema') != ACCEPTANCE_SCHEMA:
        raise ValueError('unknown_acceptance_schema')
    source_sha = record.get('source_sha')
    previous_release = record.get('previous_release')
    manifest_sha256 = record.get('manifest_sha256')
    build_report_sha256 = record.get('build_report_sha256')
    release_id = record.get('release_id')
    evidence = record.get('evidence')
    if not SHA.fullmatch(source_sha or ''):
        raise ValueError('acceptance_source_sha_invalid')
    if not isinstance(previous_release, str) or not previous_release:
        raise ValueError('acceptance_previous_release_missing')
    if not SHA256.fullmatch(manifest_sha256 or ''):
        raise ValueError('acceptance_manifest_sha256_invalid')
    if not SHA256.fullmatch(build_report_sha256 or ''):
        raise ValueError('acceptance_build_report_sha256_invalid')
    validate_release_id(release_id)
    accepted_at = parse_timestamp(record.get('accepted_at'))
    age = (datetime.now(timezone.utc) - accepted_at).total_seconds()
    if age < -120 or age > 24 * 3600:
        raise ValueError('acceptance_stale')
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('acceptance_evidence_missing')
    if previous_release != current_name:
        raise ValueError('unexpected_current_release')
    checks = record.get('required_checks')
    if not isinstance(checks, list) or not checks or any(not isinstance(x, str) or not CHECK_ID.fullmatch(x) for x in checks) or len(set(checks)) != len(checks):
        raise ValueError('required_checks_invalid')
    return record


def validate_evidence(record: dict, workspace: Path) -> None:
    source_sha = record.get('source_sha')
    accepted_time = parse_timestamp(record.get('accepted_at'))
    evidence_root = workspace / 'evidence'
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise ValueError('evidence_directory_missing')
    seen = set()
    checked = set()
    for item in record.get('evidence', []):
        if not isinstance(item, dict):
            raise ValueError('evidence_item_invalid')
        kind = item.get('kind')
        relative = item.get('path')
        expected = item.get('sha256')
        if not isinstance(kind, str) or not CHECK_ID.fullmatch(kind):
            raise ValueError('evidence_kind_invalid')
        if not isinstance(relative, str) or not relative \
                or Path(relative).name != relative or relative in seen:
            raise ValueError('evidence_path_unsafe')
        seen.add(relative)
        if not SHA256.fullmatch(expected or ''):
            raise ValueError('evidence_sha256_invalid')
        path = evidence_root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('evidence_file_missing')
        if path.stat().st_size == 0:
            raise ValueError('evidence_file_empty')
        if digest_file(path) != expected:
            raise ValueError('evidence_hash_mismatch')
        data = load_json(path)
        if data.get('check', data.get('kind')) != kind:
            raise ValueError('evidence_check_mismatch')
        if data.get('source_sha') != source_sha:
            raise ValueError('evidence_source_sha_mismatch')
        environment = data.get('environment')
        if not isinstance(environment, str) or not environment:
            raise ValueError('evidence_environment_missing')
        status = data.get('status')
        if status != 'passed' or data.get('success', True) is not True or type(data.get('failed')) is not int or data['failed'] != 0:
            raise ValueError('evidence_not_successful')
        if not isinstance(data.get('command'), str) or not data['command'].strip():
            raise ValueError('evidence_command_missing')
        checked.add(kind)
        evidence_time = parse_timestamp(data.get('timestamp'))
        if evidence_time > accepted_time:
            raise ValueError('evidence_timestamp_invalid')
        if (accepted_time - evidence_time).total_seconds() > EVIDENCE_MAX_AGE_SECONDS:
            raise ValueError('evidence_stale')
    if checked != set(record['required_checks']):
        raise ValueError('evidence_checks_incomplete')


def verify_workspace(workspace: Path, source_sha: str, release_id: str,
                     manifest_sha256: str) -> dict:
    validate_release_id(release_id)
    release_id_for_sha(release_id, source_sha)
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError('workspace_missing')
    report = read_build_report(workspace)
    if report.get('source_sha') != source_sha:
        raise ValueError('build_source_sha_mismatch')
    if report.get('manifest_sha256') != manifest_sha256:
        raise ValueError('build_manifest_sha256_mismatch')
    manifest = workspace / 'MANIFEST.sha256'
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError('manifest_missing')
    if digest_file(manifest) != manifest_sha256:
        raise ValueError('manifest_hash_mismatch')
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  \./(.+)', line)
        if not match or match[2] in entries:
            raise ValueError('manifest_invalid')
        entries[match[2]] = match[1]
    found = {}
    for name in ('hxy-server', 'diy-web', 'admin-react', 'deploy'):
        deploy_root = workspace / name
        if deploy_root.is_symlink() or not deploy_root.is_dir():
            raise ValueError('missing_deploy_root')
        for item in deploy_root.rglob('*'):
            if item.is_symlink():
                raise ValueError('unsafe_export_file')
            if item.is_dir():
                continue
            if not item.is_file():
                raise ValueError('unsafe_export_file')
            relative = item.relative_to(workspace).as_posix()
            found[relative] = digest_file(item)
    if set(found) != set(entries) or any(found[key] != entries[key] for key in found):
        raise ValueError('manifest_content_mismatch')
    return report


# --------------------------------------------------------------------------- #
# GitHub backup bundle + pending/failed record
# --------------------------------------------------------------------------- #

def _bundle_path(root: Path, release_id: str) -> Path:
    path = root / 'release-records' / (release_id + '.bundle')
    if path.is_symlink():
        raise ValueError('unsafe_bundle_path')
    if path.parent.resolve() != (root / 'release-records').resolve():
        raise ValueError('unsafe_bundle_path')
    return path


def _unique_temp_ref() -> str:
    return 'refs/server-release-bundle-tmp-%d-%s' % (os.getpid(), os.urandom(6).hex())


def _bundle_head_sha(repo: str, bundle: Path, run=subprocess.run) -> list:
    heads = run(['git', '-C', repo, 'bundle', 'list-heads', str(bundle)],
                check=True, capture_output=True, text=True).stdout
    return [line.split()[0] for line in heads.splitlines() if line.split()]


def ensure_bundle(bundle: Path, repo: str, source_sha: str, run=subprocess.run) -> None:
    """Create (or reconcile) a bundle whose advertised head is exactly source_sha."""
    def local_run(args, **kwargs):
        # A partial clone must never turn a local backup into a remote fetch.
        env = dict(os.environ, GIT_ALLOW_PROTOCOL='')
        return run(args, env=env, timeout=120, **kwargs)

    if bundle.is_symlink():
        raise ValueError('unsafe_bundle_path')
    if bundle.exists():
        local_run(['git', '-C', repo, 'bundle', 'verify', str(bundle)],
            check=True, capture_output=True, text=True)
        if source_sha not in _bundle_head_sha(repo, bundle, run=local_run):
            raise ValueError('bundle_head_mismatch')
        return
    temporary_ref = _unique_temp_ref()
    try:
        local_run(['git', '-C', repo, 'update-ref', temporary_ref, source_sha],
            check=True, capture_output=True, text=True)
        local_run(['git', '-C', repo, 'bundle', 'create', str(bundle), temporary_ref],
            check=True, capture_output=True, text=True)
    finally:
        local_run(['git', '-C', repo, 'update-ref', '-d', temporary_ref, source_sha],
            check=False, capture_output=True, text=True)
    local_run(['git', '-C', repo, 'bundle', 'verify', str(bundle)],
        check=True, capture_output=True, text=True)
    if source_sha not in _bundle_head_sha(repo, bundle, run=local_run):
        raise ValueError('bundle_head_mismatch')


def record_github_backup(root: Path, release_id: str, source_sha: str,
                         repo: str, run=subprocess.run) -> dict:
    """Emit a pending-or-failed backup record; never raise into the publish path."""
    root = ensure_root(root)
    try:
        bundle = _bundle_path(root, release_id)
        ensure_bundle(bundle, repo, source_sha, run=run)
        bundle_sha256 = digest_file(bundle)
        state = 'pending'
        error = None
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        bundle_sha256 = None
        state = 'failed'
        error = repr(exc)
    record = {'schema': PENDING_SCHEMA, 'release_id': release_id,
              'source_sha': source_sha,
              'bundle': str(root / 'release-records' / (release_id + '.bundle')),
              'bundle_sha256': bundle_sha256,
              'github_backup': state,
              'github_receipt': None,
              'error': error,
              'created_at': utcnow()}
    path = root / 'release-records' / ('pending-github-backup-' + release_id + '.json')
    save_json(path, record)
    return record


# --------------------------------------------------------------------------- #
# publish
# --------------------------------------------------------------------------- #

def parse_deploy_output(stdout: str) -> dict:
    parsed = {}
    for token in stdout.split():
        for key in ('release', 'previous', 'backup'):
            if token.startswith(key + '='):
                parsed[key] = token.split('=', 1)[1]
    return parsed


def normalize_release_path(root: Path, previous) -> str:
    """Return the release basename, validating any absolute path stays in root."""
    if not isinstance(previous, str) or not previous.strip():
        raise ValueError('deploy_previous_missing')
    previous = previous.strip()
    path = Path(previous)
    name = path.name
    if path.is_absolute():
        resolved = path.resolve()
        expected = (root / 'releases' / name).resolve()
        if resolved != expected:
            raise ValueError('deploy_previous_changed')
    return name


def dispatch_deploy(workspace: Path, release_id: str, root: Path,
                    expected_previous: str, run=subprocess.run) -> str:
    script = workspace / 'deploy' / 'diy' / 'deploy-production.sh'
    if script.is_symlink() or not script.is_file() or not os.access(script, os.X_OK):
        raise ValueError('deploy_script_missing')
    env = dict(os.environ)
    env['HXY_DIY_RELEASE_ROOT'] = str(root)
    env['HXY_DIY_EXPECTED_PREVIOUS'] = expected_previous
    result = run(['bash', str(script), release_id, str(workspace)],
                 cwd=str(root), check=True, capture_output=True, text=True,
                 env=env, timeout=3600)
    return result.stdout


def _attempt_record_path(root: Path, release_id: str) -> Path:
    return root / 'release-records' / ('attempt-' + release_id + '.json')


def _attempt_lock_path(root: Path, release_id: str) -> Path:
    return root / 'release-records' / ('.attempt-' + release_id + '.lock')


def _flock(fd, operation) -> None:
    if fcntl is not None:
        fcntl.flock(fd.fileno(), operation)


def _unflock(fd) -> None:
    if fcntl is not None:
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)


def verify_installed_release(root: Path, release_id: str, workspace: Path) -> str:
    target = root / 'releases' / release_id
    if target.is_symlink() or not target.is_dir():
        raise ValueError('installed_release_missing')
    manifest = target / 'MANIFEST.sha256'
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError('installed_manifest_missing')
    entries = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  \./(.+)', line)
        if not match or match[2] in entries:
            raise ValueError('installed_manifest_invalid')
        entries[match[2]] = match[1]
    expected = {}
    found = {}
    for base, values in ((workspace, expected), (target, found)):
        for name in ('hxy-server', 'diy-web', 'admin-react', 'deploy'):
            folder = base / name
            reject_unsafe_tree(folder)
            for item in folder.rglob('*'):
                if item.is_file():
                    values[item.relative_to(base).as_posix()] = digest_file(item)
    if found != expected or entries != found:
        raise ValueError('installed_content_mismatch')
    return digest_file(manifest)


def reconcile_attempt(root: Path, release_id: str, expected: dict) -> dict | None:
    path = _attempt_record_path(root, release_id)
    if path.is_symlink():
        raise ValueError('unsafe_attempt_record')
    if not path.exists():
        return None
    record = load_json(path)
    if record.get('schema') != ATTEMPT_SCHEMA:
        raise ValueError('unknown_attempt_schema')
    if record.get('status') != 'succeeded':
        raise ValueError('attempt_incomplete_' + str(record.get('status')))
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError('attempt_receipt_mismatch')
    if current_release_name(root) != release_id:
        raise ValueError('attempt_current_changed')
    installed = verify_installed_release(root, release_id, root / 'workspaces' / release_id)
    if installed != record.get('installed_manifest_sha256'):
        raise ValueError('attempt_manifest_changed')
    return record


def publish(root: Path, release_id: str, acceptance: dict, repo: str | None = None,
            run=subprocess.run) -> dict:
    root = ensure_root(root)
    validate_release_id(release_id)
    workspace = root / 'workspaces' / release_id
    # A successful retry validates its original acceptance and receipt, rather
    # than comparing the already activated release with the previous release.
    validate_acceptance(acceptance, acceptance.get('previous_release'))
    if acceptance['release_id'] != release_id:
        raise ValueError('acceptance_release_id_mismatch')
    source_sha = acceptance['source_sha']
    manifest_sha256 = acceptance['manifest_sha256']
    report = verify_workspace(workspace, source_sha, release_id, manifest_sha256)
    if report.get('release_id') != release_id or report.get('previous_release') != acceptance['previous_release']:
        raise ValueError('build_release_binding_mismatch')
    if digest_file(workspace / 'build-report.json') != acceptance['build_report_sha256']:
        raise ValueError('build_report_hash_mismatch')
    validate_evidence(acceptance, workspace)
    expected = {'release_id': release_id, 'source_sha': source_sha,
                'manifest_sha256': manifest_sha256,
                'previous_release': acceptance['previous_release'],
                'acceptance_sha256': sha256_of_text(json.dumps(acceptance, sort_keys=True))}
    lock_path = _attempt_lock_path(root, release_id)
    if lock_path.is_symlink() or fcntl is None:
        raise ValueError('unsafe_attempt_lock')
    with lock_path.open('a+') as lock_fd:
        _flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            existing = reconcile_attempt(root, release_id, expected)
            if existing is not None:
                pending_path = root / 'release-records' / ('pending-github-backup-' + release_id + '.json')
                pending = load_json(pending_path) if pending_path.exists() else {'github_backup': 'pending'}
                return {'status': 'already_deployed', 'release_id': release_id,
                        'source_sha': source_sha, 'github_backup': pending['github_backup'],
                        'note': 'successful receipt and installed content verified; no dispatch'}
            if (root / 'releases' / release_id).exists() or (root / 'releases' / release_id).is_symlink():
                raise ValueError('inconsistent_existing_release')
            if current_release_name(root) != acceptance['previous_release']:
                raise ValueError('unexpected_current_release')
            try:
                accepted_sha = show_accepted_ref(repo or DEFAULT_REPO, run=run)
            except subprocess.CalledProcessError:
                raise ValueError('server_accepted_missing')
            if accepted_sha != source_sha:
                raise ValueError('acceptance_not_server_accepted')
            attempt_path = _attempt_record_path(root, release_id)
            attempt = {'schema': ATTEMPT_SCHEMA, 'status': 'dispatched', **expected,
                       'dispatched_at': utcnow()}
            save_json(attempt_path, attempt)
            try:
                stdout = dispatch_deploy(workspace, release_id, root, acceptance['previous_release'], run=run)
                parsed = parse_deploy_output(stdout)
                if parsed.get('release') != release_id:
                    raise ValueError('deploy_release_mismatch')
                if normalize_release_path(root, parsed.get('previous')) != acceptance['previous_release']:
                    raise ValueError('deploy_previous_changed')
                if current_release_name(root) != release_id:
                    raise ValueError('deploy_activation_mismatch')
                attempt['installed_manifest_sha256'] = verify_installed_release(root, release_id, workspace)
                backup = Path(parsed.get('backup', ''))
                if backup.is_symlink() or backup.resolve().parent != root.resolve() / 'backups' or not backup.is_file():
                    raise ValueError('deploy_backup_invalid')
                attempt.update(status='succeeded', deploy_backup=str(backup),
                               backup_sha256=digest_file(backup), deploy_stdout=stdout,
                               finished_at=utcnow())
                save_json(attempt_path, attempt)
            except BaseException as error:
                attempt.update(status='failed' if isinstance(error, subprocess.CalledProcessError) else 'uncertain',
                               error=repr(error), finished_at=utcnow())
                if isinstance(error, subprocess.CalledProcessError):
                    attempt['stderr_tail'] = (error.stderr or '')[-4000:]
                save_json(attempt_path, attempt)
                raise
        finally:
            _unflock(lock_fd)
    try:
        github_record = record_github_backup(root, release_id, source_sha, repo or DEFAULT_REPO, run=run)
    except Exception as error:
        github_record = {'schema': PENDING_SCHEMA, 'release_id': release_id,
                         'source_sha': source_sha, 'github_backup': 'failed',
                         'github_receipt': None, 'error': repr(error), 'created_at': utcnow()}
        try:
            save_json(root / 'release-records' / ('pending-github-backup-' + release_id + '.json'), github_record)
        except OSError:
            pass  # Production success is already durable in its independent receipt.
    return {'status': 'published', 'release_id': release_id, 'source_sha': source_sha,
            'previous_release': acceptance['previous_release'], 'deploy_backup': attempt['deploy_backup'],
            'github_backup': github_record['github_backup'], 'pending_github_backup': github_record}


# --------------------------------------------------------------------------- #
# server-accepted ref (coordinator only)
# --------------------------------------------------------------------------- #

def show_accepted_ref(repo: str, run=subprocess.run) -> str:
    result = run(['git', '-C', repo, 'rev-parse', '--verify', SERVER_ACCEPTED_REF],
                 check=True, capture_output=True, text=True)
    return result.stdout.strip()


def init_accepted_ref(repo: str, sha: str, run=subprocess.run) -> dict:
    if not SHA.fullmatch(sha or ''):
        raise ValueError('invalid_sha')
    # All-zero CAS: only succeeds when the ref does not already exist, so a
    # concurrent initializer can never be silently overwritten.
    result = run(['git', '-C', repo, 'update-ref', SERVER_ACCEPTED_REF, sha, ZERO_SHA],
                 check=False, capture_output=True, text=True)
    if result.returncode == 0:
        return {'status': 'initialized', 'ref': SERVER_ACCEPTED_REF, 'sha': sha}
    try:
        current = show_accepted_ref(repo, run=run)
    except subprocess.CalledProcessError:
        current = None
    if current is None:
        raise ValueError('ref_init_failed')
    if current != sha:
        raise ValueError('ref_already_set')
    return {'status': 'unchanged', 'ref': SERVER_ACCEPTED_REF, 'sha': sha}


def advance_accepted_ref(repo: str, new_sha: str, expect_sha: str,
                         run=subprocess.run) -> dict:
    if not SHA.fullmatch(new_sha or '') or not SHA.fullmatch(expect_sha or ''):
        raise ValueError('invalid_sha')
    current = show_accepted_ref(repo, run=run)
    if current != expect_sha:
        raise ValueError('ref_compare_and_swap_failed')
    ancestor = run(['git', '-C', repo, 'merge-base', '--is-ancestor',
                    expect_sha, new_sha], check=False, capture_output=True, text=True)
    if ancestor.returncode != 0:
        raise ValueError('ref_not_fast_forward')
    run(['git', '-C', repo, 'update-ref', SERVER_ACCEPTED_REF, new_sha, expect_sha],
        check=True, capture_output=True, text=True)
    return {'status': 'advanced', 'ref': SERVER_ACCEPTED_REF,
            'previous': expect_sha, 'sha': new_sha}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _fail(message: str) -> None:
    print(json.dumps({'status': 'rejected', 'reason': message}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')

    prepare_parser = sub.add_parser('prepare', help='build and export an immutable workspace')
    prepare_parser.add_argument('--source', required=True)
    prepare_parser.add_argument('--sha', required=True)
    prepare_parser.add_argument('--release-id')
    prepare_parser.add_argument('--release-root', default=os.environ.get(
        'HXY_DIY_RELEASE_ROOT', DEFAULT_ROOT))

    inspect_p = sub.add_parser('inspect', help='read-only release status (default)')
    inspect_p.add_argument('--release-root', default=os.environ.get(
        'HXY_DIY_RELEASE_ROOT', DEFAULT_ROOT))
    inspect_p.add_argument('--repo')

    publish_p = sub.add_parser('publish', help='accept, verify, and deploy once')
    publish_p.add_argument('--release-id', required=True)
    publish_p.add_argument('--acceptance', required=True)
    publish_p.add_argument('--release-root', default=os.environ.get(
        'HXY_DIY_RELEASE_ROOT', DEFAULT_ROOT))
    publish_p.add_argument('--repo')

    init = sub.add_parser('ref-init', help='initialize server-accepted baseline')
    init.add_argument('--sha', required=True)
    init.add_argument('--repo', default=DEFAULT_REPO)

    show = sub.add_parser('ref-show', help='show server-accepted')
    show.add_argument('--repo', default=DEFAULT_REPO)

    advance = sub.add_parser('ref-advance', help='CAS + fast-forward server-accepted')
    advance.add_argument('--new', required=True, dest='new_sha')
    advance.add_argument('--expect', required=True, dest='expect_sha')
    advance.add_argument('--repo', default=DEFAULT_REPO)

    args = parser.parse_args(argv)
    if args.command is None:
        # Default inspect is read-only; populate its attributes without ensure_root.
        args.command = 'inspect'
        args.release_root = os.environ.get('HXY_DIY_RELEASE_ROOT', DEFAULT_ROOT)
        args.repo = None

    try:
        if args.command == 'prepare':
            report = prepare(Path(args.release_root), Path(args.source), args.sha,
                             args.release_id)
            print(json.dumps({'status': 'prepared', **report}, ensure_ascii=False,
                             indent=2))
            return 0
        if args.command == 'inspect':
            print(json.dumps(inspect(Path(args.release_root), args.repo),
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == 'publish':
            acceptance = load_json(Path(args.acceptance))
            result = publish(Path(args.release_root), args.release_id,
                             acceptance, args.repo)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == 'ref-init':
            print(json.dumps(init_accepted_ref(args.repo, args.sha),
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == 'ref-show':
            print(json.dumps({'ref': SERVER_ACCEPTED_REF,
                              'sha': show_accepted_ref(args.repo)},
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == 'ref-advance':
            print(json.dumps(advance_accepted_ref(args.repo, args.new_sha,
                                                  args.expect_sha),
                             ensure_ascii=False, indent=2))
            return 0
    except ValueError as error:
        _fail(str(error))
    except subprocess.CalledProcessError as error:
        _fail('command_failed_' + type(error).__name__)
    return 1


if __name__ == '__main__':
    sys.exit(main())
