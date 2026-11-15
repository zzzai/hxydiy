"""Upload private evidence and invoke the pinned, ordinary-code server coordinator."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from contracts import Stop
import runner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def invoke(args, timeout):
    value=subprocess.run(args,capture_output=True,timeout=timeout,
                         creationflags=0x08000000 if __import__("os").name == "nt" else 0)
    if value.returncode:
        raise Stop("controlled_server_step_failed_no_retry")
    return value.stdout


def apply(root, report):
    run_id=report["run_id"]
    assert re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}",run_id)
    config=json.loads((runner.HERE/"server-runtime.json").read_bytes())
    runtime=config["path"]; runtime_sha=config["manifest_sha256"]
    assert re.fullmatch(r"/root/hxy-diy-private-operations/member-sync-agent/runtime/[a-f0-9]{40}",runtime)
    assert re.fullmatch(r"[a-f0-9]{64}",runtime_sha)
    remote="/root/hxy-diy-private-operations/member-sync-agent/batches/"+run_id
    directory=root/"runs"/run_id
    ssh=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10","hxy"]
    invoke(ssh+["cd /root/hxy-diy-private-operations/member-sync-agent && umask 077 && mkdir "+remote],30)
    names=["source-private.json","index-private.json","candidates-private.json"]
    invoke(["scp","-q","-o","BatchMode=yes","-o","ConnectTimeout=10",
            *[str(directory/name) for name in names],"hxy:"+remote+"/"],60)
    command="cd "+runtime+" && python3 -B server.py --runtime-sha256 "+runtime_sha+" --run-id "+run_id
    for name in ("source","index","candidates"):
        command+=" --"+name+"-sha256 "+sha(directory/(name+"-private.json"))
    result=json.loads(invoke(ssh+[command],900))
    if result.get("status") != "completed_and_verified":
        raise Stop("server_outcome_not_verified_no_retry")
    target=directory/"server-result"
    target.mkdir(mode=0o700)
    invoke(["scp","-q","-r","-o","BatchMode=yes","-o","ConnectTimeout=10","hxy:"+remote+"/.",str(target)],120)
    inventory=json.loads((target/"receipt-sha256.json").read_bytes())
    for name,expected in inventory.items():
        if Path(name).name != name or name in {".",".."} or sha(target/name) != expected:
            raise Stop("server_receipt_copy_failed_no_retry")
    if json.loads((target/"PRODUCTION-RESULT.json").read_bytes()) != result:
        raise Stop("server_receipt_result_mismatch")
    return dict(result,local_receipt_files_verified=len(inventory),model_calls=0,run_id=run_id)


def sync_once(root, collect_fn):
    report=runner.run(root,collect_fn)
    if report["status"] == "no_new":
        report=dict(report,mode="controlled_additive",apply_enabled=True)
        runner.save(root/"report.json",report)
        runner.save(root/"state.json",{"blocked":False,"last_success":report.get("run_id"),
                    "mode":"controlled_additive","apply_enabled":True})
        return report
    if report["status"] != "readonly_passed" or not report.get("new_cards"):
        return report
    try:
        # Mark a durable local stop before the first server action. Never retry an unknown outcome.
        runner.save(root/"state.json",{"blocked":True,"run_id":report["run_id"],"code":"controlled_sync_in_progress"})
        result=apply(root,report)
        runner.save(root/"runs"/report["run_id"]/"sync-result.json",result)
        runner.save(root/"report.json",result)
        runner.save(root/"state.json",{"blocked":False,"last_success":report["run_id"],"mode":"controlled_additive","apply_enabled":True})
        return result
    except Exception as exc:
        code=str(exc) if isinstance(exc,Stop) else "controlled_sync_unexpected_failure_no_retry"
        result={"status":"blocked","code":code,"exception_type":type(exc).__name__,
                "run_id":report["run_id"],"model_calls":0,"business_outcome":"inspect_exact_server_receipt"}
        runner.save(root/"state.json",dict(result,blocked=True))
        runner.save(root/"runs"/report["run_id"]/"sync-result.json",result)
        runner.save(root/"report.json",result)
        result["notification"]=runner.notify(root)
        runner.save(root/"report.json",result)
        return result
