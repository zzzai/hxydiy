"""Background collection and exact remote finance submission; never retry an unknown result."""
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import uuid

from bridge import invoke,sha
from contracts import require
from finance_schedule import FILES,verify_evidence
import runner


def apply_finance(root,directory,run_id):
    config=json.loads((runner.HERE/'server-runtime.json').read_bytes())
    runtime=config['path'];runtime_sha=config['manifest_sha256']
    require(re.fullmatch(r'/root/hxy-diy-private-operations/member-sync-agent/runtime/[a-f0-9]{40}',runtime) is not None,'finance_runtime_path_invalid')
    require(re.fullmatch(r'[a-f0-9]{64}',runtime_sha) is not None,'finance_runtime_sha_invalid')
    remote='/root/hxy-diy-private-operations/member-history-'+run_id[:8]+'/scheduled-'+run_id
    hashes={name:sha(directory/'source'/name) for name in FILES}
    runner.save(directory/'upload-sha256.json',hashes)
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','hxy']
    invoke(ssh+['cd /root/hxy-diy-private-operations && umask 077 && mkdir -p '+remote.rsplit('/',1)[0]+' && mkdir '+remote+' && mkdir '+remote+'/source'],30)
    invoke(['scp','-q','-o','BatchMode=yes','-o','ConnectTimeout=10',*[str(directory/'source'/n) for n in FILES],'hxy:'+remote+'/source/'],120)
    invoke(['scp','-q','-o','BatchMode=yes',str(directory/'upload-sha256.json'),'hxy:'+remote+'/'],30)
    command='cd '+runtime+' && python3 -B finance_server.py --runtime-sha256 '+runtime_sha+' --run-id '+run_id+' --upload-sha256 '+sha(directory/'upload-sha256.json')
    result=json.loads(invoke(ssh+[command],1200))
    require(result.get('status') in ('applied_verified','no_new'),'finance_server_result_unverified')
    target=directory/'server-result';target.mkdir(mode=0o700)
    invoke(['scp','-q','-r','-o','BatchMode=yes','-o','ConnectTimeout=10','hxy:'+remote+'/.',str(target)],240)
    inventory=json.loads((target/'receipt-sha256.json').read_bytes())
    require(bool(inventory),'finance_receipt_inventory_empty')
    for name,expected in inventory.items():
        relative=PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in name,'finance_receipt_path_invalid')
        require((target/name).resolve().is_relative_to(target.resolve()) and sha(target/name)==expected,'finance_receipt_hash_failed')
    require(json.loads((target/'PRODUCTION-RESULT.json').read_bytes())==result,'finance_receipt_result_mismatch')
    return dict(result,run_id=run_id,local_receipt_files_verified=len(inventory),model_calls=0)


def sync_finance(root,page):
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-')+uuid.uuid4().hex[:8]
    directory=root/'finance-runs'/run_id;directory.mkdir(parents=True,mode=0o700)
    source=directory/'source';source.mkdir(mode=0o700)
    runner.save(root/'state.json',{'blocked':True,'run_id':run_id,'mode':'controlled_financial','phase':'collecting','business_outcome':'finance_not_attempted'})
    from financial_ui import collect_finance
    collect_finance(page,source)
    verify_evidence(source)
    runner.save(root/'state.json',{'blocked':True,'run_id':run_id,'mode':'controlled_financial','phase':'submitting','business_outcome':'inspect_exact_server_receipt'})
    result=apply_finance(root,directory,run_id)
    runner.save(directory/'sync-result.json',result)
    return result
