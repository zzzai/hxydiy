"""Run the existing reviewed additive importer through preview, real restore and one apply."""
import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

DEPLOY = Path("/root/hxy-diy-20260811")
BASE = Path("/root/hxy-diy-private-operations/member-sync-agent/batches")
RUNNER_SHA = "3f30e71c3909725e255d8ae7c41362e8f65938cbef384062261dc0c9faf23925"
PREFIX = ["docker", "exec", "--env", "PYTHONPATH=/app", "hxy-diy-api", "python", "-B"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(root, name, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2)+"\n").encode()
    with os.fdopen(os.open(root/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), "wb") as stream:
        stream.write(data)


class Batch:
    def __init__(self, root, expected):
        assert root.parent == BASE and re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", root.name)
        assert root.resolve() == root and root.stat().st_mode & 0o077 == 0
        assert sha(root/"batch-request.json") == expected
        self.root = root
        self.request = json.loads((root/"batch-request.json").read_bytes())
        self.container = "/tmp/hxy-msync-"+root.name
        assert self.request["container_path"] == self.container
        assert self.request["runner_sha256"] == RUNNER_SHA
        assert self.request["batch_id"] == "MEMBER-SYNC-"+root.name
        assert 0 < self.request["new_cards"] <= 100
        for name, expected_sha in self.request["input_files"].items():
            assert Path(name).name == name and name not in {".", ".."}
            path = root/name
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_mode & 0o077 == 0
            assert sha(path) == expected_sha
        assert sha(root/"import_member_card_batch.py") == RUNNER_SHA

    def run(self, label, args, timeout=120):
        result = subprocess.run(args, capture_output=True, timeout=timeout)
        save(self.root,label+".stdout",result.stdout)
        save(self.root,label+".stderr",result.stderr)
        assert result.returncode == 0, label+"_failed_no_automatic_retry"
        return result.stdout

    def identity(self, phase):
        assert str((DEPLOY/"current").resolve(strict=True)) == self.request["current"]
        for name in ("api", "db"):
            actual=self.run(phase+"-identity-"+name,["docker","inspect","--format","{{.Id}}","hxy-diy-"+name]).decode().strip()
            assert actual == self.request[name+"_id"]

    @contextlib.contextmanager
    def release_locks(self):
        with contextlib.ExitStack() as stack:
            for name in (".deploy.lock", ".manual-deploy.lock"):
                path=DEPLOY/name
                info=path.lstat()
                assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                lock=stack.enter_context(os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),"rb"))
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield

    def stage(self, name):
        self.run("stage-"+name,["docker","cp",str(self.root/name),"hxy-diy-api:"+self.container+"/"+name])
        self.run("mode-"+name,["docker","exec","hxy-diy-api","chmod","600",self.container+"/"+name])

    def persist(self, name):
        self.run("persist-"+name,["docker","cp","hxy-diy-api:"+self.container+"/"+name,str(self.root/name)])
        os.chmod(self.root/name,0o600)

    def prepare(self):
        with self.release_locks():
            self.identity("prepare")
            self.run("create-evidence",["docker","exec","hxy-diy-api","mkdir","-m","700",self.container])
            for name in ["batch-request.json",*self.request["input_files"]]:
                self.stage(name)
            prepared=json.loads(self.run("prepare",PREFIX+[self.container+"/prepare_current_batch.py"]))
            for name in ["source-cards.json","bound-attestation.json","candidate-input.json","candidate-phones.txt",
                         "baseline-private.json","candidate-manifest.json","preparation-summary.json","continuity-result.json"]:
                self.persist(name)
            manifest_sha=prepared["manifest_sha256"]
            assert sha(self.root/"candidate-manifest.json") == manifest_sha
            config={"manifest_sha256":manifest_sha,"restore_database":"hxy_diy_rehearsal_msync"+
                    self.request["verification_date"].replace("-","")+"_"+manifest_sha[:8],
                    "prior_manifest_sha256":self.request["prior_manifest_sha256"]}
            save(self.root,"execution-config.json",config)
            self.stage("execution-config.json")
            preview=json.loads(self.run("formal-preview",PREFIX+[self.container+"/import_member_card_batch.py",
                self.container+"/candidate-manifest.json","--manifest-sha256",manifest_sha,
                "--report",self.container+"/formal-preflight.json"]))
            self.persist("formal-preflight.json")
            assert preview["mode"] == "dry-run" and preview["applied"] is False
            assert preview["new_cards"] == self.request["new_cards"]
            return prepared

    def apply_once(self):
        config=json.loads((self.root/"execution-config.json").read_bytes())
        manifest=json.loads((self.root/"candidate-manifest.json").read_bytes())
        manifest_sha=config["manifest_sha256"]
        assert sha(self.root/"candidate-manifest.json") == manifest_sha
        recovery=json.loads((self.root/"backup-recovery-result.json").read_bytes())
        continuity=json.loads((self.root/"continuity-result.json").read_bytes())
        assert recovery["status"] == "backup_and_real_recovery_passed" and recovery["apply_executed"] is False
        assert continuity["status"] == "passed" and continuity["unexpected_account_changes"] == 0
        with self.release_locks():
            self.identity("apply-before")
            before=json.loads(self.run("immediate-before-apply",PREFIX+[self.container+"/verify_batch_database.py","hxy_diy","before"]))
            assert before["status"] == "passed"
            save(self.root,"exact-batch-authorization.json",{"manifest_sha256":manifest_sha,
                "source_keyset_sha256":self.request["source_keyset_sha256"],"new_cards":manifest["cards"],
                "new_users":manifest["new_users"],"standing_confirmation_date":"2026-10-25",
                "authorization_basis":"user authorized controlled additive automation; current source and protection verified",
                "verification_date":self.request["verification_date"]})
            save(self.root,"formal-apply-attempt.json",{"manifest_sha256":manifest_sha,"retry_permitted":False,
                "started_at_utc":datetime.now(timezone.utc).isoformat()})
            applied=json.loads(self.run("formal-apply",PREFIX+[self.container+"/import_member_card_batch.py",
                self.container+"/candidate-manifest.json","--manifest-sha256",manifest_sha,"--apply",
                "--approved-manifest-sha256",manifest_sha,"--preflight-file",self.container+"/formal-preflight.json",
                "--preflight-sha256",sha(self.root/"formal-preflight.json"),"--recovery-file",self.container+"/recovery-evidence.json",
                "--recovery-sha256",sha(self.root/"recovery-evidence.json"),"--report",self.container+"/formal-apply.json"]))
            self.persist("formal-apply.json")
            assert applied["applied"] is True and applied["new_cards"] == manifest["cards"]
            assert applied["new_users"] == manifest["new_users"] and applied["protected_old_records_unchanged"] is True
            after=json.loads(self.run("immediate-after-apply",PREFIX+[self.container+"/verify_batch_database.py","hxy_diy","after"]))
            self.persist("post-protection-private.json")
            replay=json.loads(self.run("replay-preview",PREFIX+[self.container+"/import_member_card_batch.py",
                self.container+"/candidate-manifest.json","--manifest-sha256",manifest_sha,
                "--report",self.container+"/replay-preview.json"]))
            self.persist("replay-preview.json")
            assert replay["mode"] == "already-applied" and replay["new_cards"] == replay["new_users"] == 0
            assert replay["applied"] is False
            self.identity("apply-after")
            result={"status":"completed_and_verified","completed_at_utc":datetime.now(timezone.utc).isoformat(),
                "manifest_sha256":manifest_sha,"input_sha256":manifest["files"]["input"]["sha256"],
                "new_cards":manifest["cards"],"new_users":manifest["new_users"],
                "existing_member_cards_added":manifest["cards"]-manifest["new_users"],
                "protected_users":before["users"],"protected_cards":before["cards"],
                "users_after":after["users"],"cards_after":after["cards"],
                "old_users_cards_wallets_unchanged":after["old_users_and_cards_unchanged"],
                "six_financial_tables_unchanged":after["financial_tables_unchanged"],
                "formal_apply_count":1,"repeat_preview_new_cards":0,"repeat_preview_new_users":0,"deployment_unchanged":True}
            save(self.root,"PRODUCTION-RESULT.json",result)
            return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--batch",type=Path,required=True)
    parser.add_argument("--request-sha256",required=True)
    parser.add_argument("--phase",choices=["prepare","backup","apply"],required=True)
    args=parser.parse_args()
    os.umask(0o077)
    batch=Batch(args.batch,args.request_sha256)
    # No retries: each phase writes exclusive evidence, and apply has a durable attempt marker.
    lock_path=BASE.parent/"operation.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.phase == "prepare":
            result=batch.prepare()
        elif args.phase == "backup":
            batch.run("backup-restore",["python3","-B",str(args.batch/"verify_backup_recovery.py"),
                      sha(args.batch/"formal-preflight.json")],timeout=600)
            result=json.loads((args.batch/"backup-recovery-result.json").read_bytes())
            result={k:v for k,v in result.items() if k in {"status","apply_executed","recovery_evidence_sha256","source_business_writes"}}
        else:
            result=batch.apply_once()
        print(json.dumps(result,sort_keys=True))


if __name__ == "__main__":
    main()
