const { test } = require('node:test');
const assert = require('node:assert/strict');
const { assertScope, selectRun, validateResult, waitForTrustedRun } = require('./trusted-run-gate.cjs');
const pr = { number: 479, state: 'open', draft: false, base: { ref: 'main' }, head: { sha: 'abc', ref: 'feature', repo: { full_name: 'owner/repo' } } };
const run = { id: 100, run_number: 1, run_attempt: 1, head_sha: 'abc', head_branch: 'feature', event: 'pull_request_target', path: '.github/workflows/trusted-pr-gate.yml', head_repository: { full_name: 'owner/repo' }, status: 'completed', conclusion: 'success', html_url: 'https://github.com/owner/repo/actions/runs/100' };
const jobs = ['Validate PR scope', 'Static contracts', 'Admin tests and build', 'Customer tests and build', 'Backend tests', 'Publish trusted result'].map(name => ({ name, status: 'completed', conclusion: 'success' }));
test('accepts only the authorized open same-repository head', () => {
  assert.doesNotThrow(() => assertScope(pr, 'abc', 'owner/repo'));
  for (const patch of [{ state: 'closed' }, { draft: true }, { base: { ref: 'other' } }, { head: { ...pr.head, sha: 'stale' } }, { head: { ...pr.head, repo: { full_name: 'fork/repo' } } }]) {
    assert.throws(() => assertScope({ ...pr, ...patch }, 'abc', 'owner/repo'));
  }
});
test('ignores unrelated, stale, forked or untrusted runs', () => {
  for (const patch of [{ head_sha: 'old' }, { head_branch: 'other' }, { event: 'pull_request' }, { path: '.github/workflows/ci.yml' }, { head_repository: { full_name: 'fork/repo' } }]) {
    assert.equal(selectRun([{ ...run, ...patch }], 'abc', 'feature', 'owner/repo'), undefined);
  }
});
test('latest run and latest attempt take precedence over an older success', () => {
  const newer = { ...run, id: 101, run_number: 2, conclusion: 'failure' };
  assert.equal(selectRun([run, newer], 'abc', 'feature', 'owner/repo').id, 101);
  assert.equal(selectRun([run, { ...run, run_attempt: 2 }], 'abc', 'feature', 'owner/repo').run_attempt, 2);
});
test('accepts all six successful trusted jobs', () => assert.equal(validateResult(run, jobs), true));
test('pending run is not success', () => assert.equal(validateResult({ ...run, status: 'in_progress' }, jobs), false));
test('failure cancellation skipped and timeout never pass', () => {
  for (const conclusion of ['failure', 'cancelled', 'skipped', 'timed_out', null]) {
    assert.throws(() => validateResult({ ...run, conclusion }, jobs));
    assert.throws(() => validateResult(run, jobs.map((j, i) => i === 1 ? { ...j, conclusion } : j)));
  }
});
test('missing duplicate and incomplete jobs fail closed', () => {
  assert.throws(() => validateResult(run, jobs.slice(1)));
  assert.throws(() => validateResult(run, [...jobs, jobs[0]]));
  assert.throws(() => validateResult(run, jobs.map((j, i) => i === 0 ? { ...j, status: 'queued' } : j)));
});
function fixture(runs, current = [pr, pr]) {
  const summary = { addHeading() { return this; }, addLink() { return this; }, addRaw() { return this; }, async write() {} };
  let index = 0;
  return { context: { repo: { owner: 'owner', repo: 'repo' }, payload: { pull_request: pr } }, core: { summary }, sleep: async () => {}, attempts: 2,
    github: { rest: { pulls: { get: async () => ({ data: current[Math.min(index++, current.length - 1)] }) }, actions: { listWorkflowRuns: async () => ({ data: { workflow_runs: runs } }), listJobsForWorkflowRunAttempt: 'jobs' } },
      paginate: async (endpoint, params) => { assert.equal(endpoint, 'jobs'); assert.equal(params.attempt_number, 1); return jobs; } } };
}
test('waiter returns only real trusted run evidence', async () => assert.equal(await waitForTrustedRun(fixture([run])), 100));
test('missing workflow times out instead of passing', async () => await assert.rejects(waitForTrustedRun(fixture([])), /Timed out/));
test('head changes during verification invalidate result', async () => await assert.rejects(waitForTrustedRun(fixture([run], [pr, { ...pr, head: { ...pr.head, sha: 'new' } }])), /head changed/));
