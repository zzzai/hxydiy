"""Deterministic add-only intake; an unresolved server attempt blocks every later batch."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from controlled_batch import BASE, Batch, sha, save
from packet import prepare_packet
from runner import save as atomic_save


def runtime_valid(expected):
    root=Path(__file__).resolve().parent
    manifest=root/"runtime-manifest.json"
    assert sha(manifest) == expected, "runtime_manifest_mismatch"
    entries=json.loads(manifest.read_bytes())
    assert {"server.py","controlled_batch.py","packet.py","runner.py","contracts.py"}.issubset(entries)
    for name,value in entries.items():
        path=root/name
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert path.resolve().is_relative_to(root) and not path.is_symlink()
        assert sha(path) == value, "runtime_file_mismatch"


def advance(root):
    result=json.loads((root/"PRODUCTION-RESULT.json").read_bytes())
    assert result["status"] == "completed_and_verified" and result["formal_apply_count"] == 1
    assert result["repeat_preview_new_cards"] == result["repeat_preview_new_users"] == 0
    assert result["old_users_cards_wallets_unchanged"] and result["six_financial_tables_unchanged"]
    config={"mode":"previous_success","prior_manifest_sha256":result["manifest_sha256"],
        "files":{name:{"path":str(root/filename),"sha256":sha(root/filename)} for name,filename in [
            ("prior-protection-private.json","post-protection-private.json"),("prior-input-private.json","candidate-input.json")]}}
    assert config["files"]["prior-input-private.json"]["sha256"] == result["input_sha256"]
    previous=json.loads((BASE.parent/"continuity.json").read_bytes())
    if previous != config:
        save(BASE.parent,"continuity-before-"+root.name+".json",previous)
        atomic_save(BASE.parent/"continuity.json",config)
    atomic_save(BASE.parent/"server-state.json",{"blocked":False,"last_success":root.name})
    inventory={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.name != "receipt-sha256.json"}
    atomic_save(root/"receipt-sha256.json",inventory)
    return result


def process(root, hashes):
    state_path=BASE.parent/"server-state.json"
    if state_path.exists():
        state=json.loads(state_path.read_bytes())
        assert state.get("blocked") is False, "server_failure_latched"
    assert not (root/"batch-request.json").exists(), "batch_already_prepared_no_retry"
    for name,expected in hashes.items():
        assert sha(root/name) == expected, "upload_integrity_failed"
    atomic_save(state_path,{"blocked":True,"run_id":root.name,"phase":"started","business_outcome":"not_attempted"})
    prepared=prepare_packet(root,json.loads((BASE.parent/"continuity.json").read_bytes()))
    batch=Batch(root,prepared["request_sha256"])
    batch.prepare()
    batch.run("backup-restore",[sys.executable,"-B",str(root/"verify_backup_recovery.py"),
              sha(root/"formal-preflight.json")],timeout=600)
    batch.apply_once()
    return advance(root)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--runtime-sha256",required=True)
    parser.add_argument("--run-id",required=True)
    for name in ["source","index","candidates"]:parser.add_argument("--"+name+"-sha256",required=True)
    args=parser.parse_args()
    os.umask(0o077)
    assert re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}",args.run_id)
    root=BASE/args.run_id
    try:
        runtime_valid(args.runtime_sha256)
        with (BASE.parent/"operation.lock").open("a+b") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=process(root,{name+"-private.json":getattr(args,name+"_sha256") for name in ["source","index","candidates"]})
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as exc:
        result={"status":"blocked","run_id":args.run_id,"exception_type":type(exc).__name__,
                "code":"server_controlled_sync_failed_no_retry","apply_attempted":(root/"formal-apply-attempt.json").exists(),
                "production_result_available":(root/"PRODUCTION-RESULT.json").exists()}
        # Preserve the failure latch even if a receipt exists; recovery must inspect that exact attempt.
        atomic_save(BASE.parent/"server-state.json",dict(result,blocked=True))
        atomic_save(BASE.parent/"failure.json",result)
        print(json.dumps(result))
        return 2


if __name__ == "__main__":raise SystemExit(main())
