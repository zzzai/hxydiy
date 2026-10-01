"""Scoped production backup and monitoring; no business data mutations."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


ROOT = Path('/root/hxy-diy-20260811')
RESERVE = 3 * 1024 ** 3
HEALTH_URL = 'https://diy.hexiaoyue.com/api/v1/health'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        if os.name == 'posix':
            os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_backup(root):
    daily = root / 'backups/daily'
    try:
        metadata = json.loads((daily / 'latest.json').read_text(encoding='utf-8'))
        name = metadata['file']
        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.dump'):
            return None
        source = (daily / name).resolve()
        if source.parent != daily.resolve() or not source.is_file():
            return None
        metadata['checksum_valid'] = digest(source) == metadata.get('sha256')
        return metadata
    except (OSError, ValueError, KeyError, TypeError):
        return None


def assess(disk, health, backup, now):
    issues = []
    severity = 'ok'
    if disk['used_percent'] >= 80:
        issues.append('disk_usage_warning')
        severity = 'warning'
    if disk['used_percent'] >= 90 or disk['available_bytes'] < RESERVE:
        issues.append('disk_capacity_critical')
        severity = 'critical'
    if health.get('environment') != 'production' or health.get('status') != 'ok':
        issues.append('health_failed')
        severity = 'critical'
    try:
        created = datetime.fromisoformat(backup['created_at'])
        age = (now - created).total_seconds()
        if backup.get('restored') is not True or backup.get('checksum_valid') is not True:
            issues.append('backup_unverified')
        elif age < 0 or age > 26 * 3600:
            issues.append('backup_stale')
    except (TypeError, KeyError, ValueError):
        issues.append('backup_missing')
    if any(item.startswith('backup_') for item in issues):
        severity = 'critical'
    return {'checked_at': now.isoformat(), 'severity': severity, 'issues': issues,
            'disk': disk, 'backup_created_at': backup.get('created_at') if isinstance(backup, dict) else None}


def backup(root, run=subprocess.run, capacity_bytes=None):
    root = root.resolve()
    available = shutil.disk_usage(root).free if capacity_bytes is None else capacity_bytes
    if available < RESERVE:
        raise ValueError('capacity_below_reserve')
    lock = (root / '.deploy.lock').open('a+')
    try:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = datetime.now(timezone.utc)
        identifier = uuid.uuid4().hex[:24]
        folder = root / 'backups/daily'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = folder / ('daily-' + now.strftime('%Y%m%dT%H%M%SZ') + '-' + identifier + '.partial')
        target = partial.with_suffix('.dump')
        database = 'hxy_diy_ops_' + identifier
        docker = ['docker', 'exec', 'hxy-diy-db']
        options = {'check': True, 'stderr': subprocess.PIPE, 'timeout': 180}
        with partial.open('xb') as stream:
            if os.name == 'posix':
                os.fchmod(stream.fileno(), 0o600)
            run(docker + ['pg_dump', '-U', 'hxy_diy', '-Fc', 'hxy_diy'], stdout=stream, **options)
        with partial.open('rb') as stream:
            if stream.read(5) != b'PGDMP':
                raise ValueError('invalid_dump_header')
        created = False
        try:
            run(docker + ['psql', '-v', 'ON_ERROR_STOP=1', '-U', 'hxy_diy', '-d', 'postgres',
                          '-c', f'CREATE DATABASE "{database}"'], stdout=subprocess.PIPE, **options)
            created = True
            with partial.open('rb') as stream:
                run(['docker', 'exec', '-i', 'hxy-diy-db', 'pg_restore', '--exit-on-error',
                     '-U', 'hxy_diy', '-d', database], stdin=stream, stdout=subprocess.PIPE, **options)
            run(docker + ['psql', '-v', 'ON_ERROR_STOP=1', '-U', 'hxy_diy', '-d', database,
                          '-c', 'SELECT 1'], stdout=subprocess.PIPE, **options)
        finally:
            if created:
                run(docker + ['psql', '-v', 'ON_ERROR_STOP=1', '-U', 'hxy_diy', '-d', 'postgres',
                              '-c', f'DROP DATABASE "{database}"'], stdout=subprocess.PIPE, **options)
        partial.replace(target)
        metadata = {'created_at': now.isoformat(), 'file': target.name, 'sha256': digest(target),
                    'bytes': target.stat().st_size, 'restored': True, 'source_database': 'hxy_diy'}
        save(folder / 'latest.json', metadata)
        return metadata
    finally:
        lock.close()


def check(root):
    result = subprocess.run(['df', '-Pk', str(root)], check=True, capture_output=True,
                            text=True, timeout=10)
    fields = result.stdout.splitlines()[-1].split()
    disk = {'available_bytes': int(fields[3]) * 1024, 'used_percent': int(fields[4].rstrip('%'))}
    try:
        with urlopen(HEALTH_URL, timeout=10) as response:
            health = json.load(response) if response.status == 200 else {}
    except Exception:
        health = {}
    report = assess(disk, health, read_backup(root), datetime.now(timezone.utc))
    save(root / 'operations/status.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'check'])
    args = parser.parse_args()
    if not ROOT.is_dir() or ROOT.is_symlink():
        raise SystemExit('invalid_production_root')
    try:
        report = backup(ROOT) if args.action == 'backup' else check(ROOT)
        print(json.dumps(report, ensure_ascii=False))
        return 2 if report.get('severity') == 'critical' else 1 if report.get('severity') == 'warning' else 0
    except Exception as error:
        report = {'action': args.action, 'severity': 'critical', 'error': type(error).__name__,
                  'checked_at': datetime.now(timezone.utc).isoformat()}
        save(ROOT / 'operations' / (args.action + '-failure.json'), report)
        print(json.dumps(report), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
