"""Bounded, dependency-free GitHub waiter. No LLM calls; logs never contain credentials.

Read-only by default. --merge explicitly authorizes one exact PR head to merge
after trusted checks; production is handled only by the existing Actions gates.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = 'zzzai/hxydiy'
ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ['Static contracts', 'Admin tests and build', 'Customer tests and build',
            'Backend tests', 'Trusted PR Gate']
TERMINAL = {'checks_failed', 'ci_failed', 'deployment_failed', 'deployment_skipped',
            'deployment_unverified', 'deployment_succeeded', 'timeout', 'head_changed',
            'pr_ineligible', 'merge_blocked', 'superseded', 'setup_failed'}


def gate(checks, sha):
    latest = {}
    for check in sorted(checks, key=lambda c: c['id']):
        if check.get('app', {}).get('slug') == 'github-actions' and check.get('head_sha') == sha:
            latest[check['name']] = check
    waiting = False
    for name in REQUIRED + ['AI PR Review']:
        check = latest.get(name)
        if not check or check['status'] != 'completed':
            waiting = True
            continue
        allowed = ('success', 'skipped') if name == 'AI PR Review' else ('success',)
        if check['conclusion'] not in allowed:
            return 'checks_failed'
    return 'waiting_for_checks' if waiting else 'ready'


def pr_problem(pr, sha):
    if pr['head']['sha'] != sha:
        return 'head_changed'
    if pr.get('merged'):
        return None
    if (pr['state'] != 'open' or pr['draft'] or pr['base']['ref'] != 'main'
            or (pr['head'].get('repo') or {}).get('full_name') != REPO):
        return 'pr_ineligible'
    return None


def release_state(ci, deploy, job):
    if not ci or ci['status'] != 'completed':
        return 'waiting_for_ci'
    if ci['conclusion'] != 'success':
        return 'ci_failed'
    if not deploy:
        return 'waiting_for_deployment'
    if deploy['status'] != 'completed':
        return 'deploying'
    if deploy['conclusion'] != 'success':
        return 'deployment_failed'
    return {'success': 'deployment_succeeded', 'skipped': 'deployment_skipped',
            'failure': 'deployment_failed'}.get(job, 'deployment_unverified')


def save(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class AlreadyRunning(Exception):
    pass


@contextmanager
def lock(path):
    # OS lock is released even on process termination; no stale PID guessing.
    with path.open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise AlreadyRunning() from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise AlreadyRunning() from None
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def git(*args, input=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    result = subprocess.run(['git', '-C', str(ROOT), *args], input=input,
                            text=True, capture_output=True, timeout=30, env=env)
    if result.returncode:
        raise RuntimeError('git_command_failed')
    return result.stdout.strip()


class GitHub:
    def __init__(self):
        credential = git('credential', 'fill', input='protocol=https\nhost=github.com\n\n')
        fields = dict(line.split('=', 1) for line in credential.splitlines() if '=' in line)
        self.token = fields.get('password')
        if not self.token:
            raise RuntimeError('credential_unavailable')

    def get(self, path, body=None):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Accept': 'application/vnd.github+json', 'User-Agent': 'hxy-release-waiter'}
        request = Request('https://api.github.com/repos/' + REPO + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None,
                          method='PUT' if body is not None else 'GET')
        with urlopen(request, timeout=25) as response:
            return json.load(response)

    def pages(self, path, key):
        values = []
        for page in range(1, 11):
            chunk = self.get(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')[key]
            values.extend(chunk)
            if len(chunk) < 100:
                return values
        raise RuntimeError('pagination_limit')


def compact(run):
    return {k: run.get(k) for k in ('id', 'status', 'conclusion', 'html_url')} if run else None


def step(api, args, report):
    sha = report['commit']
    if args.pr and not sha:
        pr = api.get(f'/pulls/{args.pr}')
        problem = pr_problem(pr, args.head)
        if problem:
            return problem
        if pr['merged']:
            sha = report['commit'] = pr['merge_commit_sha']
        else:
            checks = api.pages(f'/commits/{args.head}/check-runs?filter=latest', 'check_runs')
            state = gate(checks, args.head)
            if state != 'ready':
                return state
            if not args.merge:
                return 'waiting_for_merge'
            if pr.get('mergeable_state') not in ('clean', 'has_hooks'):
                return 'merge_blocked' if pr.get('mergeable') is False else 'waiting_for_mergeability'
            # Explicit opt-in + exact SHA. No force, no admin bypass, no retry on rejection.
            merged = api.get(f'/pulls/{args.pr}/merge', {'sha': args.head, 'merge_method': 'squash'})
            if not merged.get('merged'):
                return 'merge_blocked'
            sha = report['commit'] = merged['sha']
    latest = api.get('/git/ref/heads/main')['object']['sha']
    if latest != sha:
        return 'superseded'
    runs = api.pages(f'/actions/runs?head_sha={sha}', 'workflow_runs')
    runs.sort(key=lambda r: r['id'], reverse=True)
    ci = next((r for r in runs if r['path'] == '.github/workflows/ci.yml'
               and r['event'] == 'push' and r['head_branch'] == 'main'), None)
    deploy = next((r for r in runs if r['path'] == '.github/workflows/deploy-production.yml'
                   and r['event'] == 'workflow_run' and r['head_branch'] == 'main'), None)
    report.update(ci=compact(ci), deployment=compact(deploy))
    job = None
    if deploy and deploy['status'] == 'completed':
        jobs = api.pages(f'/actions/runs/{deploy["id"]}/jobs', 'jobs')
        job = next((j['conclusion'] for j in jobs
                    if j['name'] == 'Backup, rehearse, deploy and verify'), None)
    return release_state(ci, deploy, job)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--commit')
    target.add_argument('--pr', type=int)
    parser.add_argument('--head', help='Required exact reviewed PR head SHA')
    parser.add_argument('--merge', action='store_true', help='Explicitly authorize gated squash merge')
    parser.add_argument('--interval', type=int, default=45)
    parser.add_argument('--timeout', type=int, default=3600, help='Total seconds')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.commit or args.head or ''):
        parser.error('A full lowercase 40-character SHA is required')
    if args.merge and not args.pr or args.pr is not None and args.pr < 1:
        parser.error('--merge requires a positive --pr and --head')
    if not 15 <= args.interval <= 300 or not 1 <= args.timeout <= 7200:
        parser.error('interval: 15..300; timeout: 1..7200 seconds')
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir'))
    key = f'pr-{args.pr}-{args.head}' if args.pr else args.commit
    folder = common / 'hxy-release-reports' / key
    folder.mkdir(parents=True, exist_ok=True)
    target_path = folder / 'report.json'
    report = dict(status='starting', commit=args.commit, pr=args.pr, head=args.head,
                  mergeAuthorized=args.merge, terminal=False, error=None,
                  evidence='GitHub trusted CI and deployment job conclusions; not live current identity or store acceptance',
                  ci=None, deployment=None)
    deadline = time.monotonic() + args.timeout
    try:
        with lock(folder / 'worker.lock'):
            try:
                api = GitHub()
                while True:
                    report['error'] = None
                    try:
                        report['status'] = step(api, args, report)
                    except HTTPError as error:
                        report['error'] = f'github_http_{error.code}'
                        report['status'] = 'merge_blocked' if error.code in (401, 403, 405, 409, 422) else 'connection_retry'
                    except Exception as error:
                        report['error'] = type(error).__name__
                        report['status'] = 'connection_retry'
                    if report['status'] not in TERMINAL and time.monotonic() >= deadline:
                        report['status'] = 'timeout'
                    report.update(terminal=report['status'] in TERMINAL,
                                  updatedAt=datetime.now(timezone.utc).isoformat())
                    save(target_path, report)
                    if report['terminal'] or args.once:
                        break
                    time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
            except Exception as error:
                report.update(status='setup_failed', terminal=True, error=type(error).__name__)
                save(target_path, report)
    except AlreadyRunning:
        print(f'Already running. Report: {target_path}')
        return 0
    print(json.dumps({'status': report['status'], 'report': str(target_path)}, ensure_ascii=False))
    if not report['terminal']:
        return 2
    return 0 if report['status'] in ('deployment_succeeded', 'deployment_skipped', 'superseded') else 1


if __name__ == '__main__':
    sys.exit(main())
