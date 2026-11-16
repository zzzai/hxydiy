"""Install an immutable reviewed server runtime outside the application release directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--expected-head",required=True)
    args=parser.parse_args()
    os.umask(0o077)
    repo=Path(__file__).resolve().parents[2]
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    assert head == args.expected_head and not subprocess.check_output(["git","status","--porcelain"],cwd=repo)
    source=Path(__file__).resolve().parent
    root=Path("/root/hxy-diy-private-operations/member-sync-agent/runtime")/head
    root.mkdir(parents=True,mode=0o700)
    names=["server.py","controlled_batch.py","packet.py","runner.py","contracts.py"]
    names += ["finance_server.py","finance_stage.py","finance_controlled.py","finance_entry.py","finance_packet.py","finance_acceptance.py","finance_schedule.py","financial_contracts.py"]
    names += ["batch/"+p.name for p in (source/"batch").glob("*.py")]
    entries={}
    for name in names:
        target=root/name
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copyfile(source/name,target)
        os.chmod(target,0o600)
        entries[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    for name,relative in [("member_financial_import.py","hxy-server/app/services/member_financial_import.py"),("member_finance_guard.py","hxy-server/scripts/member_finance_guard.py")]:
        shutil.copyfile(repo/relative,root/name)
        os.chmod(root/name,0o600)
        entries[name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
    payload=(json.dumps(entries,sort_keys=True,indent=2)+"\n").encode()
    (root/"runtime-manifest.json").write_bytes(payload)
    info={"path":str(root),"manifest_sha256":hashlib.sha256(payload).hexdigest(),"source_revision":head}
    (root/"server-runtime.json").write_text(json.dumps(info,sort_keys=True)+"\n")
    print(json.dumps(info))


if __name__ == "__main__":main()
