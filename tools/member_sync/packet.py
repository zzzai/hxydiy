"""Bind two verified read-only passes to a fresh reviewed-import packet."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from contracts import verify, source_key, digest
from controlled_batch import BASE, RUNNER_SHA, save, sha


def prepare_packet(root, context):
    os.umask(0o077)
    report=json.loads((root/"candidates-private.json").read_bytes())
    index=json.loads((root/"index-private.json").read_bytes())
    scans=json.loads((root/"source-private.json").read_bytes())
    observed=datetime.fromisoformat(report["verified_at_utc"])
    assert 0 <= (datetime.now(timezone.utc)-observed).total_seconds() <= 7200, "source_observation_stale"
    checked=verify(index,scans,now=observed)
    assert checked["candidates"] == report["candidates"]
    assert checked["source_keyset_sha256"] == report["source_keyset_sha256"]
    assert digest(scans) == report["source_evidence_sha256"]
    assert 0 < checked["new_cards"] <= 100
    candidates={r["source_key"]:r for r in checked["candidates"]}
    rows=[]
    for page in scans[0]["pages"]:
        for r in page["rows"]:
            row={"card_number":r["card_number"]}
            key=source_key(r["card_number"])
            if key in candidates:
                row=dict(candidates[key])
                row["principal_yuan"]=str(Decimal(row["balance_cents"])/100)
                row["ownership_evidence"]="same raw card and full phone independently verified in normal detail on both passes"
            rows.append(row)
    today=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    assert observed.astimezone(timezone(timedelta(hours=8))).date().isoformat() == today
    facts={"scope":checked["scope"],"rows":rows,"source_keyset_sha256":checked["source_keyset_sha256"],
           "source_evidence_sha256":checked["source_evidence_sha256"],"verified_at_utc":observed.isoformat()}
    save(root,"source-ui-facts-private.json",facts)
    save(root,"source-status-attestation.json",{"scope":checked["scope"],
        "source_keyset_sha256":checked["source_keyset_sha256"],"user_confirmation_date":"2026-10-25",
        "confirmation":"这个问题 以后不用问了，都是正常的，直接新增即可",
        "applies_only_to_frozen_snapshot":True,"new_candidates_only":True,
        "verification_date":today,"confirmation_basis":"standing_confirmation_not_a_new_user_confirmation"})
    helper=Path(__file__).resolve().parent/"batch"
    for source in helper.glob("*.py"):
        assert not (root/source.name).exists()
        shutil.copyfile(source,root/source.name)
    for name,ref in context["files"].items():
        assert Path(name).name == name and name not in {".",".."}
        source=Path(ref["path"])
        assert sha(source) == ref["sha256"]
        if (root/name).exists():
            assert sha(root/name) == ref["sha256"]
        else:
            shutil.copyfile(source,root/name)
    for path in root.iterdir():
        assert path.is_file() and not path.is_symlink()
        os.chmod(path,0o600)
    identities={name:subprocess.check_output(["docker","inspect","--format","{{.Id}}","hxy-diy-"+name],text=True).strip() for name in ("api","db")}
    request={"batch_id":"MEMBER-SYNC-"+root.name,"container_path":"/tmp/hxy-msync-"+root.name,
        "runner_sha256":RUNNER_SHA,"new_cards":checked["new_cards"],"source_cards":checked["source_cards"],
        "verification_date":today,"source_keyset_sha256":checked["source_keyset_sha256"],
        "facts_sha256":sha(root/"source-ui-facts-private.json"),
        "confirmation_sha256":sha(root/"source-status-attestation.json"),
        "current":str(Path("/root/hxy-diy-20260811/current").resolve(strict=True)),
        "api_id":identities["api"],"db_id":identities["db"],
        "continuity_mode":context["mode"],"prior_protection_sha256":context["files"]["prior-protection-private.json"]["sha256"],
        "prior_manifest_sha256":context["prior_manifest_sha256"],
        "prior_input_sha256":context["files"]["prior-input-private.json"]["sha256"],
        "input_files":{p.name:sha(p) for p in root.iterdir()}}
    save(root,"batch-request.json",request)
    return {"request_sha256":sha(root/"batch-request.json"),"new_cards":checked["new_cards"],"source_cards":checked["source_cards"]}


if __name__ == "__main__":
    root=Path(sys.argv[1])
    assert root.parent == BASE and root.resolve() == root and root.stat().st_mode & 0o077 == 0
    context=json.loads((BASE.parent/"continuity.json").read_bytes())
    print(json.dumps(prepare_packet(root,context)))
