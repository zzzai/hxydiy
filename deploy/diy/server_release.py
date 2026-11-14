#!/usr/bin/env python3
"""Server-controlled release entry reusing deploy/diy/deploy-production.sh and its gates.

This is the small reusable server-side entry that replaces GitHub PR/CI as the
mandatory release critical path. GitHub remains an asynchronous mirror and a
secondary check; nothing here installs credentials, pushes, force-pushes, or
claims a mirror completed without a receipt.

Subcommands
-----------
prepare
    Verify a clean, exact-SHA development worktree, build the two frontends
    serially with locked dependencies while preserving current build flags
    (staff-learning marker and customer base path), then export an immutable
    release workspace under ``<release-root>/workspaces/<release-id>`` with a
    MANIFEST.sha256 and a durable build report. Never deploys.
inspect  (default)
    Read-only status of prepared workspaces, the current release, pending
    GitHub backup records and the ``server-accepted`` ref. Never builds or
    deploys.
publish
    Consume an exact-SHA coordinator acceptance record, re-verify every gate
    (source SHA, previous/current release, artifact manifest, evidence hashes),
    reconcile any existing receipt, then dispatch deploy-production.sh exactly
    once under its existing lock. Emits a pending GitHub backup record and a
    locally verified Git bundle for recovery while GitHub is pending.
ref-init / ref-show / ref-advance
    Manage ``refs/heads/server-accepted``. ref-advance performs a
    compare-and-swap plus fast-forward and is intended for the coordinator
    only; this entry never calls it implicitly.

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
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disk_maintenance as dm  # reuse digest() and validate_root()

DEFAULT_ROOT = '/root/hxy-diy-20260811'
DEFAULT_REPO = '/root/hxy-diy-automation'

RELEASE_ID = re.compile(r'server-[0-9a-f]{12}-[0-9]{1,14}')
SHA = re.compile(r'[0-9a-f]{40}')
SHA256 = re.compile(r'[0-9a-f]{64}')
ACCEPTANCE_SCHEMA = 'server-release-acceptance@1'
BUILD_SCHEMA = 'server-release-build@1'
PENDING_SCHEMA = 'server-release-pending-github-backup@1'
SERVER_ACCEPTED_REF = 'refs/heads/server-accepted'

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


def ensure_root(root: Path) -> Path:
    root = Path(root)
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


# --------------------------------------------------------------------------- #
# prepare: verify, build, export
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
    """Inspect current build markers and preserve them explicitly."""
    current = dm.validate_root(root)
    learning = False
    learning_source = 'default-false'
    marker = current / 'admin-react' / 'dist' / 'staff-learning-build.json'
    if marker.exists():
        if marker.is_symlink():
            raise ValueError('unsafe_learning_marker')
        data = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(data.get('enabled'), bool):
            raise ValueError('invalid_learning_marker')
        learning = data['enabled']
        learning_source = 'current-release-marker'
    # The customer app is served from the domain root; the vite default is '/'.
    # Record it explicitly rather than letting a future change drift silently.
    return {'staff_learning_enabled': learning,
            'learning_source': learning_source,
            'customer_base_path': '/'}


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
        if not (source / required).is_file():
            raise ValueError('missing_build_output')

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
    if root.is_symlink() or not root.is_dir():
        raise ValueError('invalid_root')
    current = current_release_name(root)
    workspaces = []
    for entry in sorted((root / 'workspaces').iterdir()):
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
    if records.is_dir():
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
    if record.get('schema') != ACCEPTANCE_SCHEMA:
        raise ValueError('unknown_acceptance_schema')
    source_sha = record.get('source_sha')
    previous_release = record.get('previous_release')
    manifest_sha256 = record.get('manifest_sha256')
    evidence = record.get('evidence')
    release_id = record.get('release_id')
    if not SHA.fullmatch(source_sha or ''):
        raise ValueError('acceptance_source_sha_invalid')
    if not isinstance(previous_release, str) or not previous_release:
        raise ValueError('acceptance_previous_release_missing')
    if not SHA256.fullmatch(manifest_sha256 or ''):
        raise ValueError('acceptance_manifest_sha256_invalid')
    if release_id not in (None, ''):
        validate_release_id(release_id)
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('acceptance_evidence_missing')
    if previous_release != current_name:
        raise ValueError('unexpected_current_release')
    return record


def validate_evidence(record: dict, workspace: Path) -> None:
    evidence_root = workspace / 'evidence'
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise ValueError('evidence_directory_missing')
    seen = set()
    for item in record['evidence']:
        if not isinstance(item, dict):
            raise ValueError('evidence_item_invalid')
        kind = item.get('kind')
        relative = item.get('path')
        expected = item.get('sha256')
        if not isinstance(kind, str) or not kind:
            raise ValueError('evidence_kind_missing')
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
# publish
# --------------------------------------------------------------------------- #

def dispatch_deploy(workspace: Path, release_id: str, root: Path,
                    run=subprocess.run) -> str:
    script = workspace / 'deploy' / 'diy' / 'deploy-production.sh'
    if script.is_symlink() or not script.is_file() or not os.access(script, os.X_OK):
        raise ValueError('deploy_script_missing')
    env = dict(os.environ)
    env['HXY_DIY_RELEASE_ROOT'] = str(root)
    result = run(['bash', str(script), release_id, str(workspace)],
                 cwd=str(root), check=True, capture_output=True, text=True,
                 env=env, timeout=3600)
    return result.stdout


def parse_deploy_output(stdout: str) -> dict:
    parsed = {}
    for token in stdout.split():
        for key in ('release', 'previous', 'backup'):
            if token.startswith(key + '='):
                parsed[key] = token.split('=', 1)[1]
    return parsed


def create_pending_backup_record(root: Path, release_id: str, source_sha: str,
                                 repo: str, run=subprocess.run) -> dict:
    root = ensure_root(root)
    repo = repo or DEFAULT_REPO
    bundle = root / 'release-records' / (release_id + '.bundle')
    if bundle.exists() and not bundle.is_symlink():
        # Reconcile instead of blindly overwriting an uncertain prior bundle.
        run(['git', '-C', repo, 'bundle', 'verify', str(bundle)],
            check=True, capture_output=True, text=True)
    else:
        # A raw commit SHA cannot be bundled directly; pin it with a transient,
        # non-branch ref and remove the ref afterwards.
        temporary_ref = 'refs/server-release-bundle-tmp'
        try:
            run(['git', '-C', repo, 'update-ref', temporary_ref, source_sha],
                check=True, capture_output=True, text=True)
            run(['git', '-C', repo, 'bundle', 'create', str(bundle), temporary_ref],
                check=True, capture_output=True, text=True)
        finally:
            run(['git', '-C', repo, 'update-ref', '-d', temporary_ref],
                check=False, capture_output=True, text=True)
        run(['git', '-C', repo, 'bundle', 'verify', str(bundle)],
            check=True, capture_output=True, text=True)
    record = {'schema': PENDING_SCHEMA, 'release_id': release_id,
              'source_sha': source_sha,
              'bundle': str(bundle),
              'bundle_sha256': digest_file(bundle),
              'github_backup': 'pending',
              'github_receipt': None,
              'created_at': utcnow()}
    path = root / 'release-records' / ('pending-github-backup-' + release_id + '.json')
    save_json(path, record)
    return record


def publish(root: Path, release_id: str, acceptance: dict, repo: str | None = None,
            run=subprocess.run) -> dict:
    root = ensure_root(root)
    validate_release_id(release_id)
    workspace = root / 'workspaces' / release_id
    release_target = root / 'releases' / release_id
    # Reconcile an uncertain prior attempt before re-validating against current.
    if release_target.exists() or release_target.is_symlink():
        if (current_release_name(root) == release_id
                and (release_target / 'MANIFEST.sha256').is_file()):
            return {'status': 'already_deployed', 'release_id': release_id,
                    'note': 'existing receipt reconciled; not re-dispatched'}
        raise ValueError('inconsistent_existing_release')

    current = current_release_name(root)
    validate_acceptance(acceptance, current)
    source_sha = acceptance['source_sha']
    manifest_sha256 = acceptance['manifest_sha256']
    verify_workspace(workspace, source_sha, release_id, manifest_sha256)
    validate_evidence(acceptance, workspace)

    # Guard expected-current again immediately before the single dispatch.
    if current_release_name(root) != acceptance['previous_release']:
        raise ValueError('current_changed_before_dispatch')

    stdout = dispatch_deploy(workspace, release_id, root, run=run)
    parsed = parse_deploy_output(stdout)
    if parsed.get('release') != release_id:
        raise ValueError('deploy_release_mismatch')
    if parsed.get('previous') != acceptance['previous_release']:
        # A competing deployment changed current between validation and activation.
        raise ValueError('deploy_previous_changed')

    if current_release_name(root) != release_id:
        raise ValueError('deploy_activation_mismatch')

    pending = create_pending_backup_record(root, release_id, source_sha,
                                           repo or DEFAULT_REPO, run=run)
    return {'status': 'published', 'release_id': release_id,
            'source_sha': source_sha, 'previous_release': parsed['previous'],
            'backup': parsed.get('backup'),
            'pending_github_backup': pending}


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
    try:
        current = show_accepted_ref(repo, run=run)
    except subprocess.CalledProcessError:
        current = None
    if current is None:
        run(['git', '-C', repo, 'update-ref', SERVER_ACCEPTED_REF, sha],
            check=True, capture_output=True, text=True)
        return {'status': 'initialized', 'ref': SERVER_ACCEPTED_REF, 'sha': sha}
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

    prepare = sub.add_parser('prepare', help='build and export an immutable workspace')
    prepare.add_argument('--source', required=True)
    prepare.add_argument('--sha', required=True)
    prepare.add_argument('--release-id')
    prepare.add_argument('--release-root', default=os.environ.get(
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
        args.command = 'inspect'

    try:
        if args.command == 'prepare':
            root = ensure_root(Path(args.release_root))
            source = Path(args.source)
            verify_source_clean(source, args.sha)
            settings = read_build_settings(root)
            build_report = build_source(source, args.sha, settings)
            release_id = args.release_id or (
                'server-' + args.sha[:12] + '-' + str(int(time.time())))
            workspace = export_workspace(source, args.sha, release_id,
                                         build_report, root)
            report = read_build_report(workspace)
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
