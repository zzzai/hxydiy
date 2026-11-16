"""Server-side exact-batch backup, isolated rehearsal and single apply orchestration."""
import argparse
import contextlib
from datetime import datetime,timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess

DEPLOY=Path('/root/hxy-diy-20260811')
PRIVATE=Path('/root/hxy-diy-private-operations')

def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:json.dump(value,stream,sort_keys=True,indent=2)
def run(args,timeout=180,stdin=None,stdout=None):
    result=subprocess.run(args,stdin=stdin,stdout=stdout or subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if result.returncode:
        if globals().get("RUN_ROOT"):
            save(RUN_ROOT/("failure-"+str(__import__("time").time_ns())+".json"),{"returncode":result.returncode,"stderr":result.stderr.decode(errors="replace"),"stdout":result.stdout.decode(errors="replace") if isinstance(result.stdout,bytes) else None})
        raise RuntimeError("controlled_command_failed:"+str(result.returncode))
    return result.stdout

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','apply']);parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();os.umask(0o077)
    if root.parent.parent!=PRIVATE or not re.fullmatch(r'member-history-20[0-9]{6}',root.parent.name) or root.stat().st_mode&0o077 or root.is_symlink():raise ValueError('private_batch_root_invalid')
    global RUN_ROOT
    RUN_ROOT=root
    request=json.loads((root/'request.json').read_bytes());manifest=request['manifest_sha256']
    if not re.fullmatch(r'[a-f0-9]{64}',manifest):raise ValueError('invalid_manifest')
    runtime=request['runtime_sha256']
    container='/tmp/hxy-finance-'+manifest[:12]+'-'+runtime[:8]
    restore='hxy_diy_rehearsal_finance_'+manifest[:12]+'_'+runtime[:8]
    if digest(root/'runtime-index.json')!=runtime:raise ValueError('runtime_mismatch')
    if digest(Path(__file__))!=request['host_runner_sha256']:raise ValueError('host_runner_changed')
    if digest(root/'packet.json')!=request['input_sha256']:raise ValueError('packet_changed')
    for name,expected in json.loads((root/'runtime-index.json').read_bytes()).items():
        if Path(name).name!=name or digest(root/name)!=expected:raise ValueError('runtime_changed')
    def identity():
        values={'current':str((DEPLOY/'current').resolve(strict=True))}
        for label in ('api','db'):values[label+'_id']=run(['docker','inspect','--format','{{.Id}}','hxy-diy-'+label]).decode().strip()
        if any(values[k]!=request[k] for k in values):raise ValueError('production_runtime_changed')
        return values
    def entry(mode,database,extra=()):
        result=run(['docker','exec','--env','PYTHONPATH=/app','hxy-diy-api','python','-B',container+'/finance_entry.py',mode,
                    '--root',container,'--database',database,'--runtime-sha',runtime,'--manifest',manifest,*extra],timeout=180)
        return json.loads(result)
    def copyout(name):
        if (root/name).exists():raise ValueError('receipt_exists')
        run(['docker','cp','hxy-diy-api:'+container+'/'+name,str(root/name)])
        os.chmod(root/name,0o600)
    with contextlib.ExitStack() as stack:
        for name in ('.deploy.lock','.manual-deploy.lock'):
            path=DEPLOY/name;metadata=path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1:raise ValueError('unsafe_lock')
            stream=stack.enter_context(os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb'))
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity()
        if args.mode=='prepare':
            save(root/'prepare-attempt.json',{'manifest_sha256':manifest,'started_at':datetime.now(timezone.utc).isoformat()})
            run(['docker','exec','hxy-diy-api','mkdir','-m','700',container])
            run(['docker','cp',str(root)+'/.','hxy-diy-api:'+container])
            before=entry('baseline','hxy_diy');copyout('baseline-private.json');copyout('baseline.json')
            preview=entry('preview','hxy_diy');copyout('preview-result.json')
            if preview['status']!='preview' or preview['business_writes']!=0:raise ValueError('preview_not_readonly')
            memory={p[0].rstrip(':'):int(p[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(p:=line.split())>=2}
            if os.statvfs(root).f_bavail*os.statvfs(root).f_frsize<3*1024**3 or memory['MemAvailable']<1024**3:raise ValueError('resource_gate_failed')
            exists=run(['docker','exec','hxy-diy-db','psql','-v','ON_ERROR_STOP=1','-U','hxy_diy','-d','postgres','-At','-c',"SELECT count(*) FROM pg_database WHERE datname='"+restore+"'"])
            if exists.strip()!=b'0':raise ValueError('restore_database_exists')
            with os.fdopen(os.open(root/'pre-finance.dump',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
                run(['docker','exec','hxy-diy-db','pg_dump','-U','hxy_diy','-Fc','hxy_diy'],stdout=stream)
            run(['docker','exec','hxy-diy-db','psql','-v','ON_ERROR_STOP=1','-U','hxy_diy','-d','postgres','-c','CREATE DATABASE "'+restore+'" WITH TEMPLATE template0 OWNER hxy_diy'])
            with (root/'pre-finance.dump').open('rb') as stream:
                run(['docker','exec','-i','--env','PGOPTIONS=-c work_mem=4MB -c maintenance_work_mem=32MB','hxy-diy-db','pg_restore','--exit-on-error','-U','hxy_diy','-d',restore],stdin=stream)
            restored=entry('snapshot-check',restore)
            if restored['snapshot_sha256']!=before['snapshot_sha256'] or restored['database_identity']['database_oid']==before['database_identity']['database_oid']:raise ValueError('restore_validation_failed')
            rehearsal=entry('rehearse',restore);copyout('rehearse-result.json')
            verified=entry('verify',restore)
            if verified['status']!='verified' or verified['replay_business_writes']!=0:raise ValueError('rehearsal_acceptance_failed')
            after=entry('snapshot-check','hxy_diy');identity()
            if after['snapshot_sha256']!=before['snapshot_sha256']:raise ValueError('source_changed_during_recovery')
            recovery={'status':'passed','manifest_sha256':manifest,'input_sha256':request['input_sha256'],
                      'runtime_sha256':runtime,'baseline_sha256':before['snapshot_sha256'],'production_identity':before['database_identity'],
                      'backup_sha256':digest(root/'pre-finance.dump'),'restore_database':restore,'restored':restored,
                      'rehearsal':rehearsal,'verification':verified,'completed_at':datetime.now(timezone.utc).isoformat()}
            save(root/'recovery.json',recovery)
            run(['docker','cp',str(root/'recovery.json'),'hxy-diy-api:'+container+'/recovery.json'])
            print(json.dumps({'status':'prepared','manifest_sha256':manifest,'preview':preview,'rehearsal_verified':True,'production_business_writes':0}));return
        recovery_sha=digest(root/'recovery.json');recovery=json.loads((root/'recovery.json').read_bytes())
        if digest(root/'pre-finance.dump')!=recovery['backup_sha256']:raise ValueError('backup_changed')
        entry('snapshot-check','hxy_diy')
        save(root/'apply-attempt.json',{'manifest_sha256':manifest,'recovery_sha256':recovery_sha,'started_at':datetime.now(timezone.utc).isoformat()})
        result=entry('apply','hxy_diy',('--recovery-sha',recovery_sha));copyout('apply-result.json')
        verified=entry('verify','hxy_diy');identity()
        report={'status':'applied_verified','manifest_sha256':manifest,'input_sha256':request['input_sha256'],
                'result':result,'verification':verified,'old_data_unchanged':True,'runtime_unchanged':True,
                'finished_at':datetime.now(timezone.utc).isoformat()}
        save(root/'PRODUCTION-RESULT.json',report);print(json.dumps(report))

if __name__=='__main__':main()
