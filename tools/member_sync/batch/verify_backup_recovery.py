"""Create one real backup and restore only to a separate database; never apply or clean up."""

import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import re
import time

HOST = Path(__file__).resolve().parent
request = json.loads((HOST / 'batch-request.json').read_bytes())
config = json.loads((HOST / 'execution-config.json').read_bytes())
CONTAINER = request['container_path']
DEPLOY = Path('/root/hxy-diy-20260811')
CURRENT = request['current']
API_ID, DB_ID = request['api_id'], request['db_id']
MANIFEST_SHA = config['manifest_sha256']
RUNNER_SHA = '3f30e71c3909725e255d8ae7c41362e8f65938cbef384062261dc0c9faf23925'
PREFLIGHT_SHA = sys.argv[1]
assert re.fullmatch(r'[a-f0-9]{64}', PREFLIGHT_SHA)
RESTORE_DB = config['restore_database']
assert re.fullmatch(r'hxy_diy_rehearsal_msync[0-9]{8}_[a-f0-9]{8}', RESTORE_DB)
PGOPTIONS = '-c work_mem=4MB -c maintenance_work_mem=32MB -c lock_timeout=5000'
os.umask(0o077)
os.chdir(HOST)
assert HOST.resolve() == HOST and HOST.stat().st_mode & 0o077 == 0
report = {'steps': [], 'apply_executed': False, 'source_business_writes': 0,
          'isolated_database': RESTORE_DB, 'started_at_utc': datetime.now(timezone.utc).isoformat()}


def save(name, content):
    data = content if isinstance(content, bytes) else (json.dumps(content, sort_keys=True, indent=2) + '\n').encode()
    with os.fdopen(os.open(HOST / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(data)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(part)
    return value.hexdigest()


def run(name, args, *, stdin=None, stdout=None, timeout=180):
    started = time.monotonic()
    child = subprocess.run(args, stdin=stdin, stdout=stdout if stdout is not None else subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    save('recovery-' + name + '.stderr', child.stderr)
    if stdout is None:
        save('recovery-' + name + '.stdout', child.stdout)
    report['steps'].append({'name': name, 'returncode': child.returncode, 'elapsed_seconds': round(time.monotonic() - started, 3)})
    if child.returncode:
        raise RuntimeError(name + '_failed')
    return child.stdout


def snapshot(name, database):
    value = json.loads(run(name, ['docker', 'exec', '--env', 'PYTHONPATH=/app', 'hxy-diy-api', 'python', '-B',
                                  CONTAINER + '/verify_batch_database.py', database, 'before']))
    assert value['status'] == 'passed' and value['identity']['database'] == database
    return value


save('recovery-attempt.json', {'started_at_utc': report['started_at_utc'], 'manifest_sha256': MANIFEST_SHA, 'apply_executed': False})
try:
    with contextlib.ExitStack() as locks:
        for name in ['.deploy.lock', '.manual-deploy.lock']:
            path = DEPLOY / name
            metadata = path.lstat()
            assert stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
            stream = locks.enter_context(os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert str((DEPLOY / 'current').resolve(strict=True)) == CURRENT
        for label, expected in [('api', API_ID), ('db', DB_ID)]:
            assert run(label + '_identity_before', ['docker', 'inspect', '--format', '{{.Id}}', 'hxy-diy-' + label]).decode().strip() == expected
        assert digest(HOST / 'candidate-manifest.json') == MANIFEST_SHA
        assert digest(HOST / 'import_member_card_batch.py') == RUNNER_SHA
        assert digest(HOST / 'formal-preflight.json') == PREFLIGHT_SHA
        preview = json.loads((HOST / 'formal-preflight.json').read_bytes())
        manifest = json.loads((HOST / 'candidate-manifest.json').read_bytes())
        for reference in manifest['files'].values():
            assert Path(reference['name']).name == reference['name']
            assert digest(HOST / reference['name']) == reference['sha256']
        assert preview['mode'] == 'dry-run' and preview['applied'] is False
        assert preview['manifest_sha256'] == MANIFEST_SHA
        assert 0 <= (datetime.now(timezone.utc) - datetime.fromisoformat(preview['created_at_utc'])).total_seconds() <= 3600
        before = snapshot('source_before_backup', 'hxy_diy')
        assert before['identity'] == preview['database_identity'] and before['snapshot_sha256'] == preview['snapshot_sha256']
        networks = json.loads(run('db_network_identity', ['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}', 'hxy-diy-db']))
        assert before['identity']['address'].split('/')[0] in {v['IPAddress'] for v in networks.values()}
        sql = "SELECT json_build_object('database',current_database(),'schema',current_schema(),'role',current_user,'database_oid',(SELECT oid::bigint FROM pg_database WHERE datname=current_database()),'postmaster_started_at',pg_postmaster_start_time()::text)::text"
        backup_identity = json.loads(run('backup_target_identity', ['docker', 'exec', 'hxy-diy-db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'hxy_diy', '-d', 'hxy_diy', '-At', '-c', sql]))
        assert all(backup_identity[k] == before['metadata'][k] for k in backup_identity)
        memory = {parts[0].rstrip(':'): int(parts[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(parts := line.split()) >= 2}
        available = os.statvfs(HOST).f_bavail * os.statvfs(HOST).f_frsize
        required = 3 * 1024**3 + 2 * before['metadata']['database_bytes'] + 64 * 1024**2
        assert available >= required and memory['MemAvailable'] >= 1024**3
        report['resource_gate'] = {'available_disk_bytes': available, 'required_disk_bytes': required, 'available_memory_bytes': memory['MemAvailable']}
        exists_sql = "SELECT count(*) FROM pg_database WHERE datname='" + RESTORE_DB + "'"
        assert run('restore_name_absent', ['docker', 'exec', 'hxy-diy-db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'hxy_diy', '-d', 'postgres', '-At', '-c', exists_sql]).decode().strip() == '0'
        partial = HOST / 'pre-member-sync.partial'
        backup = HOST / 'pre-member-sync.dump'
        with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            run('pg_dump', ['docker', 'exec', '--env', 'PGOPTIONS=' + PGOPTIONS, 'hxy-diy-db', 'pg_dump', '-U', 'hxy_diy', '-Fc', 'hxy_diy'], stdout=stream)
        with partial.open('rb') as stream:
            assert stream.read(5) == b'PGDMP'
        assert partial.stat().st_size > 5 and not backup.exists()
        partial.rename(backup)
        backup_sha = digest(backup)
        create_sql = 'CREATE DATABASE "' + RESTORE_DB + '" WITH TEMPLATE template0 OWNER hxy_diy'
        run('create_isolated_database', ['docker', 'exec', '--env', 'PGOPTIONS=' + PGOPTIONS, 'hxy-diy-db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'hxy_diy', '-d', 'postgres', '-c', create_sql])
        with backup.open('rb') as stream:
            run('pg_restore', ['docker', 'exec', '-i', '--env', 'PGOPTIONS=' + PGOPTIONS, 'hxy-diy-db', 'pg_restore', '--exit-on-error', '-U', 'hxy_diy', '-d', RESTORE_DB], stdin=stream)
        restored = snapshot('restored_database_validation', RESTORE_DB)
        assert restored['snapshot_sha256'] == preview['snapshot_sha256']
        assert restored['metadata']['database_oid'] != before['metadata']['database_oid']
        after = snapshot('source_after_restore', 'hxy_diy')
        assert after['snapshot_sha256'] == before['snapshot_sha256'] and after['identity'] == before['identity']
        assert str((DEPLOY / 'current').resolve(strict=True)) == CURRENT
        for label, expected in [('api', API_ID), ('db', DB_ID)]:
            assert run(label + '_identity_after', ['docker', 'inspect', '--format', '{{.Id}}', 'hxy-diy-' + label]).decode().strip() == expected
        container_backup = CONTAINER + '/' + backup.name
        run('stage_verified_backup', ['docker', 'cp', str(backup), 'hxy-diy-api:' + container_backup])
        run('backup_mode', ['docker', 'exec', 'hxy-diy-api', 'chmod', '600', container_backup])
        assert run('backup_hash', ['docker', 'exec', 'hxy-diy-api', 'sha256sum', container_backup]).decode().split()[0] == backup_sha
        evidence = {'version': 1, 'manifest_sha256': MANIFEST_SHA, 'runner_sha256': RUNNER_SHA,
                    'preflight_sha256': PREFLIGHT_SHA, 'database_identity': preview['database_identity'],
                    'backup': {'path': container_backup, 'host_path': str(backup), 'sha256': backup_sha, 'bytes': backup.stat().st_size},
                    'restore': {'status': 'passed', 'database': RESTORE_DB, 'snapshot_sha256': restored['snapshot_sha256'],
                                'identity': restored['identity'], 'users': restored['users'], 'cards': restored['cards'],
                                'database_oid': restored['metadata']['database_oid'], 'read_only_validation': True},
                    'source_snapshot_before_after_unchanged': True, 'financial_tables_unchanged': True,
                    'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'apply_executed': False}
        save('recovery-evidence.json', evidence)
        recovery_sha = digest(HOST / 'recovery-evidence.json')
        run('stage_evidence', ['docker', 'cp', str(HOST / 'recovery-evidence.json'), 'hxy-diy-api:' + CONTAINER + '/recovery-evidence.json'])
        run('evidence_mode', ['docker', 'exec', 'hxy-diy-api', 'chmod', '600', CONTAINER + '/recovery-evidence.json'])
        assert run('evidence_hash', ['docker', 'exec', 'hxy-diy-api', 'sha256sum', CONTAINER + '/recovery-evidence.json']).decode().split()[0] == recovery_sha
        assert os.statvfs(HOST).f_bavail * os.statvfs(HOST).f_frsize >= 3 * 1024**3
        report.update(status='backup_and_real_recovery_passed', recovery_evidence_sha256=recovery_sha,
                      preflight_sha256=PREFLIGHT_SHA, backup=evidence['backup'], source_before=before, restored=restored, source_after=after)
except Exception as error:
    report.update(status='failed', error_type=type(error).__name__)
report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
save('backup-recovery-result.json', report)
print(json.dumps({k: v for k, v in report.items() if k not in {'steps', 'source_before', 'source_after', 'restored'}}, sort_keys=True))
raise SystemExit(0 if report.get('status') == 'backup_and_real_recovery_passed' else 1)
