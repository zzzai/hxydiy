"""After successful deployment, remove only verified duplicate inputs for that release."""
import argparse
from contextlib import ExitStack
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import disk_maintenance as ops


def cleanup(root, name, state_reader=ops.runtime):
    current = ops.validate_root(root)
    if not ops.RELEASE.fullmatch(name) or current.name != name:
        raise ValueError('not_current_successful_release')
    workspace = root / 'workspaces' / name
    upload = root / 'incoming' / name
    if (root / 'incoming').is_symlink() or upload.is_symlink() or not upload.is_dir():
        raise ValueError('unsafe_upload_directory')
    archive = upload / (name + '.tar.gz')
    checksum = upload / (archive.name + '.sha256')
    if archive.is_symlink() or checksum.is_symlink() or not archive.is_file() or not checksum.is_file():
        raise ValueError('unsafe_upload_file')
    expected = checksum.read_text(encoding='utf-8').strip().split()
    if len(expected) != 2 or expected[1] != archive.name or not re.fullmatch('[0-9a-f]{64}', expected[0]):
        raise ValueError('invalid_upload_checksum')
    if ops.digest(archive) != expected[0]:
        raise ValueError('upload_checksum_mismatch')
    if {item.name for item in upload.iterdir()} != {archive.name, checksum.name}:
        raise ValueError('unexpected_upload_files')
    installed, _ = ops.tree(current)
    extracted, _ = ops.tree(workspace)
    if installed != extracted or not ops.manifest_valid(current, installed):
        raise ValueError('not_verified_duplicate')
    state = state_reader()
    for target in (workspace, upload):
        if ops.in_use(target, state['paths']) or ops.mounted(target, state.get('mounts', [])):
            raise ValueError('input_in_use')
    # The caller holds both production locks. Releases and backups are never targets.
    shutil.rmtree(workspace)
    archive.unlink()
    checksum.unlink()
    upload.rmdir()
    return {'cleanup': 'completed', 'release': name, 'recovery': str(current),
            'removed_workspace': str(workspace), 'removed_upload_files': 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release')
    args = parser.parse_args()
    import fcntl
    ops.validate_root(ops.ROOT)
    with ExitStack() as stack:
        for name in ('.deploy.lock', '.manual-deploy.lock'):
            path = ops.ROOT / name
            if path.is_symlink():
                raise ValueError('unsafe_lock')
            lock = stack.enter_context(path.open('a+'))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(cleanup(ops.ROOT, args.release), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(json.dumps({'cleanup': 'skipped', 'reason': type(error).__name__}), file=sys.stderr)
        sys.exit(1)
