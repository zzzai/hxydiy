"""Preview or remove exact, old CI workspace duplicates; never prune releases/data."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time


ROOT = Path('/root/hxy-diy-20260811')
RELEASE = re.compile(r'github-[0-9a-f]{12}-[0-9]+')
MIN_AGE = 7 * 24 * 3600


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def tree(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError('unsafe_directory')
    result = {}
    latest = path.stat().st_mtime
    for item in path.rglob('*'):
        metadata = item.lstat()
        latest = max(latest, metadata.st_mtime)
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError('unsafe_file_type')
        name = item.relative_to(path).as_posix()
        source_example = name in ('deploy/diy/.env.example',
                                  'hxy-server/scripts/repair_diy_page_content.sql')
        if not source_example and (item.name.startswith('.env') or
                                   item.suffix in ('.db', '.dump', '.sql', '.pem', '.key')):
            raise ValueError('protected_file')
        if name != 'MANIFEST.sha256':
            result[name] = (digest(item), metadata.st_size, stat.S_IMODE(metadata.st_mode))
    if not result:
        raise ValueError('empty_tree')
    return result, latest


def manifest_valid(release, files):
    manifest = release / 'MANIFEST.sha256'
    if manifest.is_symlink() or not manifest.is_file():
        return False
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  \./(.+)', line)
        if not match or match[2] in entries:
            return False
        entries[match[2]] = match[1]
    return entries == {name: value[0] for name, value in files.items()}


def validate_root(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('invalid_root')
    for name in ('workspaces', 'releases'):
        if (root / name).is_symlink() or not (root / name).is_dir():
            raise ValueError('invalid_parent')
    current = (root / 'current').resolve(strict=True)
    if current.parent != root.resolve() / 'releases':
        raise ValueError('invalid_current')
    return current


def candidate(root, name, cutoff):
    current = validate_root(root)
    if not RELEASE.fullmatch(name) or name == current.name:
        raise ValueError('protected_or_invalid_name')
    workspace = root / 'workspaces' / name
    release = root / 'releases' / name
    installed, _ = tree(release)
    extracted, modified = tree(workspace)
    if modified > cutoff:
        raise ValueError('recent_workspace')
    if installed != extracted or not manifest_valid(release, installed):
        raise ValueError('not_verified_duplicate')
    identity = hashlib.sha256(json.dumps(extracted, sort_keys=True).encode()).hexdigest()
    return {'name': name, 'tree_sha256': identity,
            'bytes': sum(value[1] for value in extracted.values()),
            'recovery': str(release)}


def runtime():
    identifiers = subprocess.check_output(['docker', 'ps', '-aq'], text=True).split()
    containers = json.loads(subprocess.check_output(['docker', 'inspect', *identifiers], text=True)) if identifiers else []
    mounts = [mount['Source'] for item in containers for mount in item['Mounts']]
    paths = []
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            references = [process / 'cwd', process / 'exe', *(process / 'fd').iterdir()]
            for reference in references:
                try:
                    paths.append(os.readlink(reference))
                except FileNotFoundError:
                    pass
            for line in (process / 'maps').read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) == 6 and fields[5].startswith('/'):
                    paths.append(fields[5])
            for argument in (process / 'cmdline').read_bytes().split(b'\0'):
                value = argument.decode('utf-8', errors='replace')
                if value.startswith(('/root/hxy-diy-20260811/', '/root/.vscode-server/')):
                    paths.append(value)
        except FileNotFoundError:
            pass
    return {'containers': sorted(item['Id'] for item in containers), 'paths': paths, 'mounts': mounts}


def in_use(target, paths):
    value = target.as_posix()
    return any(Path(path).as_posix() == value or Path(path).as_posix().startswith(value + '/')
               for path in paths)


def mounted(target, sources):
    return in_use(target, sources) or any(target.as_posix().startswith(Path(source).as_posix().rstrip('/') + '/')
                                         for source in sources)


def preview(root, now=None, state=None):
    current = validate_root(root)
    cutoff = (time.time() if now is None else now) - MIN_AGE
    state = runtime() if state is None else state
    selected, skipped = [], []
    for workspace in sorted((root / 'workspaces').iterdir()):
        try:
            if in_use(workspace, state['paths']) or mounted(workspace, state.get('mounts', [])):
                raise ValueError('workspace_in_use')
            selected.append(candidate(root, workspace.name, cutoff))
        except (ValueError, FileNotFoundError) as error:
            skipped.append({'name': workspace.name, 'reason': str(error)})
    return {'version': 1, 'root': str(root), 'current': str(current), 'cutoff': cutoff,
            'containers': state['containers'], 'candidates': selected, 'skipped': skipped,
            'recoverable_bytes': sum(item['bytes'] for item in selected)}


def apply(root, plan, state_reader=runtime, remove=shutil.rmtree):
    if plan['version'] != 1 or plan['root'] != str(root):
        raise ValueError('invalid_plan_root')
    if plan['cutoff'] > time.time() - MIN_AGE:
        raise ValueError('invalid_age_cutoff')
    if str(validate_root(root)) != plan['current']:
        raise ValueError('current_changed')
    names = [item['name'] for item in plan['candidates']]
    if len(names) != len(set(names)):
        raise ValueError('duplicate_target')
    # Validate every target before deleting anything; recheck runtime before each removal.
    for item in plan['candidates']:
        if candidate(root, item['name'], plan['cutoff']) != item:
            raise ValueError('candidate_changed')
    removed = []
    for item in plan['candidates']:
        state = state_reader()
        if state['containers'] != plan['containers'] or str(validate_root(root)) != plan['current']:
            raise ValueError('runtime_changed')
        target = root / 'workspaces' / item['name']
        if in_use(target, state['paths']) or mounted(target, state.get('mounts', [])):
            raise ValueError('workspace_in_use')
        if candidate(root, item['name'], plan['cutoff']) != item:
            raise ValueError('candidate_changed')
        remove(target)
        removed.append(item['name'])
        print(json.dumps({'removed_workspace': item['name'], 'recovery': item['recovery']}), flush=True)
    return {'removed_count': len(removed), 'removed': removed, 'current': plan['current']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-plan', type=Path)
    parser.add_argument('--approved-sha256')
    args = parser.parse_args()
    if bool(args.apply_plan) != bool(args.approved_sha256):
        parser.error('apply requires an exact plan and its approved SHA256')
    import fcntl
    validate_root(ROOT)
    with ExitStack() as stack:
        for name in ('.deploy.lock', '.manual-deploy.lock'):
            path = ROOT / name
            if path.is_symlink():
                raise ValueError('unsafe_lock')
            lock = stack.enter_context(path.open('a+'))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.apply_plan:
            if digest(args.apply_plan) != args.approved_sha256:
                raise ValueError('plan_hash_mismatch')
            report = apply(ROOT, json.loads(args.apply_plan.read_text(encoding='utf-8')))
        else:
            report = preview(ROOT)
        print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
