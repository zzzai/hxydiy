"""Push one clean task branch and create or reuse its GitHub Pull Request.

This script never stages files, creates commits, merges Pull Requests, or
deploys production. It uses GH_TOKEN or the server's existing Git Credential
Manager credential only in memory and never writes or prints that credential.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO = "zzzai/hxydiy"
ROOT = Path(__file__).resolve().parents[2]


def git(*args: str, input: str | None = None) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        check=False,
        env=env,
        input=input,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("git_command_failed")
    return result.stdout.strip()


class GitHub:
    def __init__(self) -> None:
        self._token = os.environ.get("GH_TOKEN")
        if not self._token:
            credential = git("credential", "fill", input="protocol=https\nhost=github.com\n\n")
            fields = dict(line.split("=", 1) for line in credential.splitlines() if "=" in line)
            self._token = fields.get("password")
        if not self._token:
            raise RuntimeError("credential_unavailable")

    def request(self, method: str, path: str, body: dict | None = None):
        request = Request(
            "https://api.github.com/repos/" + REPO + path,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "hxy-pr-submit",
            },
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            method=method,
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)


def clean_branch(base: str) -> tuple[str, str]:
    if git("status", "--porcelain"):
        raise RuntimeError("working_tree_not_clean")
    branch = git("branch", "--show-current")
    if not branch or branch == base:
        raise RuntimeError("task_branch_required")
    remote = git("remote", "get-url", "origin")
    if "github.com/zzzai/hxydiy" not in remote.replace(".git", ""):
        raise RuntimeError("unexpected_origin")
    git("fetch", "origin", base)
    git("push", "--set-upstream", "origin", branch)
    return branch, git("rev-parse", "HEAD")


def create_or_reuse_pr(api: GitHub, branch: str, head_sha: str, title: str, body: str, base: str) -> dict:
    head = quote(f"zzzai:{branch}", safe=":/")
    pulls = api.request("GET", f"/pulls?state=open&head={head}&base={quote(base, safe='')}")
    if pulls:
        pr = pulls[0]
        if pr["head"]["sha"] != head_sha:
            raise RuntimeError("remote_pr_head_mismatch")
        return pr
    return api.request("POST", "/pulls", {
        "title": title,
        "head": branch,
        "base": base,
        "body": body,
        "draft": False,
    })


def start_watch(pr: int, head_sha: str) -> Path:
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    report = common / "hxy-release-reports" / f"pr-{pr}-{head_sha}" / "report.json"
    subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "release" / "watch_release.py"), "--pr", str(pr), "--head", head_sha],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Non-draft Pull Request title")
    parser.add_argument("--body-file", type=Path, help="UTF-8 Markdown Pull Request description")
    parser.add_argument("--base", default="main", choices=["main"])
    parser.add_argument("--watch", action="store_true", help="Start the existing read-only CI watcher in the background")
    args = parser.parse_args()

    body = args.body_file.read_text(encoding="utf-8") if args.body_file else (
        "## 修改内容\n- 见本 PR 代码差异。\n\n"
        "## 验证\n- 已在提交前完成本地验证。\n\n"
        "## 发布状态\n- 未发布生产。\n\n"
        "## 未完成事项\n- 等待 GitHub CI 与合并门禁。"
    )
    branch, head_sha = clean_branch(args.base)
    pr = create_or_reuse_pr(GitHub(), branch, head_sha, args.title, body, args.base)
    result = {
        "branch": branch,
        "head_sha": head_sha,
        "pr": pr["number"],
        "url": pr["html_url"],
        "watch_started": args.watch,
        "production_deployed": False,
    }
    if args.watch:
        result["report"] = str(start_watch(pr["number"], head_sha))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"error": type(error).__name__}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
