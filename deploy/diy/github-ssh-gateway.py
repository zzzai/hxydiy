#!/usr/bin/env python3
"""Forced-command boundary for the GitHub-only SSH key; never eval SSH input."""
import os
import hashlib
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile

POSIX_ROOT = PurePosixPath('/root/hxy-diy-20260811')
ROOT = Path(str(POSIX_ROOT))
RELEASE = re.compile(r'github-[0-9a-f]{12}-[0-9]+')


def command_args(command):
    parts = shlex.split(command)
    if parts[:3] == ['scp', '-d', '-t']:
        parts = ['scp', '-t', *parts[3:]]
    if parts == ['true']:
        return 'check', None
    if len(parts) == 3 and parts[:2] in [['hxy-deploy', 'prepare'], ['hxy-deploy', 'release']] and RELEASE.fullmatch(parts[2]):
        return parts[1], parts[2]
    if len(parts) == 3 and parts[:2] == ['scp', '-t']:
        path = PurePosixPath(parts[2])
        if path.parent == POSIX_ROOT / 'incoming' and RELEASE.fullmatch(path.name):
            return 'upload', path.name
    raise ValueError('Command not permitted for deployment key')


def safe_member(member):
    path = PurePosixPath(member.name)
    return not path.is_absolute() and '..' not in path.parts and (
        not path.parts or path.parts[0] in ['hxy-server', 'diy-web', 'admin-react', 'deploy']
    ) and (member.isfile() or member.isdir())


def main():
    action, release = command_args(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
    if action == 'check':
        return
    incoming = ROOT / 'incoming' / release
    workspace = ROOT / 'workspaces' / release
    if action == 'prepare':
        incoming.mkdir(parents=True, exist_ok=True)
        (ROOT / 'workspaces').mkdir(exist_ok=True)
    elif action == 'upload':
        if not incoming.is_dir() or incoming.is_symlink():
            raise ValueError('Prepare release first')
        os.execv('/usr/bin/scp', ['scp', '-t', str(incoming)])
    else:
        archive = incoming / (release + '.tar.gz')
        checksum = (incoming / (archive.name + '.sha256')).read_text().strip().split()
        if len(checksum) != 2 or checksum[1] != archive.name or not re.fullmatch(r'[0-9a-f]{64}', checksum[0]):
            raise ValueError('Invalid archive checksum')
        digest = hashlib.sha256()
        with archive.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != checksum[0]:
            raise ValueError('Archive checksum mismatch')
        workspace.mkdir()  # Existing workspaces are never overwritten on retries.
        with tarfile.open(archive, 'r:gz') as package:
            members = package.getmembers()
            if not all(safe_member(member) for member in members):
                raise ValueError('Unsafe release archive')
            package.extractall(workspace, members=members)
        subprocess.run(['cp', '-an', str(ROOT / 'current/diy-web/dist/assets') + '/.', str(workspace / 'diy-web/dist/assets') + '/'], check=True)
        subprocess.run(['flock', '-n', str(ROOT / '.manual-deploy.lock'), 'bash',
                        str(workspace / 'deploy/diy/deploy-production.sh'), release, str(workspace)], check=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('Deployment gateway refused or failed:', type(error).__name__, file=sys.stderr)
        sys.exit(1)
