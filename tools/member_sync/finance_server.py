"""Pinned server finance coordinator sharing the member sync failure latch and lock."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from contracts import require
from finance_schedule import FILES,verify_evidence
from runner import save
from server import runtime_valid
import finance_controlled
from finance_controlled import digest,run,DEPLOY,PRIVATE

AGENT=PRIVATE/'member-sync-agent'
RUNTIME_FILES=('finance_entry.py','finance_packet.py','finance_acceptance.py','finance_schedule.py',
               'finance_stage.py','finance_controlled.py','financial_contracts.py','contracts.py','runner.py',
               'member_financial_import.py','member_finance_guard.py')


def process(root,run_id,upload_sha):
    finance_controlled.RUN_ROOT=root
    state_path=AGENT/'server-state.json'
    state=json.loads(state_path.read_bytes())
    require(state.get('blocked') is False,'server_failure_latched')
    require(not (root/'request.json').exists() and not (root/'attempt.json').exists(),'finance_attempt_exists_no_retry')
    require(digest(root/'upload-sha256.json')==upload_sha,'finance_upload_manifest_changed')
    hashes=json.loads((root/'upload-sha256.json').read_bytes())
    require(set(hashes)==set(FILES),'finance_source_files_invalid')
    for name,expected in hashes.items():
        require(digest(root/'source'/name)==expected,'finance_upload_integrity_failed')
    verify_evidence(root/'source')
    save(root/'attempt.json',{'run_id':run_id,'started_at':datetime.now(timezone.utc).isoformat()})
    save(state_path,{'blocked':True,'run_id':run_id,'phase':'finance_started','business_outcome':'not_attempted'})
    runtime=Path(__file__).resolve().parent
    for name in RUNTIME_FILES:
        shutil.copyfile(runtime/name,root/name);os.chmod(root/name,0o600)
    index={name:digest(root/name) for name in RUNTIME_FILES}
    save(root/'runtime-index.json',index)
    identity={'current':str((DEPLOY/'current').resolve(strict=True))}
    for name in ('api','db'):
        identity[name+'_id']=run(['docker','inspect','--format','{{.Id}}','hxy-diy-'+name]).decode().strip()
    container='/tmp/hxy-finance-stage-'+run_id
    run(['docker','exec','hxy-diy-api','mkdir','-m','700',container])
    run(['docker','cp',str(root)+'/.','hxy-diy-api:'+container])
    summary=json.loads(run(['docker','exec','--env','PYTHONPATH=/app','hxy-diy-api','python','-B',container+'/finance_stage.py',
                          '--root',container,'--batch-key','scheduled-finance-'+run_id],timeout=180))
    for name in ('packet.json','source-index.json','source-summary.json'):
        run(['docker','cp','hxy-diy-api:'+container+'/'+name,str(root/name)]);os.chmod(root/name,0o600)
    request=dict(identity,manifest_sha256=summary['manifest_sha256'],input_sha256=digest(root/'packet.json'),
                 runtime_sha256=digest(root/'runtime-index.json'),host_runner_sha256=digest(root/'finance_controlled.py'),
                 source_revision=runtime.name,run_id=run_id)
    save(root/'request.json',request)
    for mode in ('prepare','apply'):
        log=root/(mode+'-host.stdout');error=root/(mode+'-host.stderr')
        with log.open('xb') as out,error.open('xb') as err:
            value=subprocess.run([sys.executable,'-B',str(root/'finance_controlled.py'),mode,'--root',str(root)],stdout=out,stderr=err,timeout=900,cwd=root)
        require(value.returncode==0,'finance_controlled_'+mode+'_failed_no_retry')
        response=json.loads(log.read_bytes())
        if mode=='prepare':
            require(response.get('status') in ('prepared','no_new'),'finance_prepare_unverified')
            if response['status']=='no_new':break
    result=json.loads((root/'PRODUCTION-RESULT.json').read_bytes())
    require(result.get('status') in ('applied_verified','no_new') and result.get('old_data_unchanged') is True,'finance_result_unverified')
    inventory={p.relative_to(root).as_posix():digest(p) for p in root.rglob('*') if p.is_file() and p.name!='receipt-sha256.json'}
    save(root/'receipt-sha256.json',inventory)
    save(state_path,dict(state,blocked=False,last_finance_success=run_id))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime-sha256',required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--upload-sha256',required=True)
    args=parser.parse_args();os.umask(0o077)
    require(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}',args.run_id) is not None,'finance_run_id_invalid')
    root=PRIVATE/('member-history-'+args.run_id[:8])/('scheduled-'+args.run_id)
    runtime_valid(args.runtime_sha256)
    require(root.is_dir() and not root.is_symlink() and root.stat().st_mode&0o077==0,'finance_private_root_invalid')
    with (AGENT/'operation.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            result=process(root,args.run_id,args.upload_sha256)
            print(json.dumps(result));return 0
        except Exception as exc:
            result={'status':'blocked','run_id':args.run_id,'exception_type':type(exc).__name__,
                    'code':'finance_server_failed_no_retry','apply_attempted':(root/'apply-attempt.json').exists(),
                    'production_result_available':(root/'PRODUCTION-RESULT.json').exists()}
            save(root/'failure.json',result)
            state_path=AGENT/'server-state.json';prior=json.loads(state_path.read_bytes())
            if prior.get('blocked') is not True or prior.get('run_id')==args.run_id:
                save(state_path,dict(result,blocked=True))
            print(json.dumps(result));return 2

if __name__=='__main__':raise SystemExit(main())
