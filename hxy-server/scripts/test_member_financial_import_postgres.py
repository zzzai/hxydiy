"""Run importer tests against a new disposable local PostgreSQL container only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
NAME = "hxy-member-finance-test-" + uuid.uuid4().hex[:10]
LABEL = "hxy.member-finance-test=" + NAME


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30, **kwargs)


run(["docker", "image", "inspect", "postgres:16-alpine", "--format", "{{.Id}}"])
container = run(["docker", "run", "--rm", "-d", "--name", NAME, "--label", LABEL,
                 "--memory", "256m", "--cpus", "0.5", "-e", "POSTGRES_PASSWORD=synthetic-test-only",
                 "-e", "POSTGRES_DB=member_finance_test", "-p", "127.0.0.1::5432", "postgres:16-alpine"]).stdout.strip()
try:
    port = run(["docker", "port", container, "5432/tcp"]).stdout.strip()
    assert port.startswith("127.0.0.1:") and port.count("\n") == 0
    deadline=time.monotonic()+40
    while True:
        ready=subprocess.run(["docker","exec",container,"pg_isready","-U","postgres","-d","member_finance_test"],capture_output=True,timeout=10)
        if ready.returncode==0:
            break
        if time.monotonic()>deadline:
            raise RuntimeError("test_database_not_ready")
        time.sleep(0.5)
    env=os.environ.copy()
    env["MEMBER_FINANCE_TEST_DATABASE_URL"]="postgresql+psycopg://postgres:synthetic-test-only@"+port+"/member_finance_test"
    result=subprocess.run([sys.executable,"-m","pytest","-q","tests/test_member_financial_import.py","--disable-warnings"],cwd=ROOT,env=env,text=True,timeout=240)
    raise SystemExit(result.returncode)
finally:
    metadata=json.loads(run(["docker","inspect",container]).stdout)[0]
    assert metadata["Id"]==container and metadata["Config"]["Labels"].get("hxy.member-finance-test")==NAME
    run(["docker","stop",container])
