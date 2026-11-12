// Bind the native check to completed validation from the trusted base workflow.
const WORKFLOW = '.github/workflows/trusted-pr-gate.yml';
const JOBS = ['Validate PR scope', 'Static contracts', 'Admin tests and build',
  'Customer tests and build', 'Backend tests', 'Publish trusted result'];

function assertScope(pr, expectedHead, repository) {
  if (!pr || pr.state !== 'open' || pr.draft || pr.base.ref !== 'main' ||
      pr.head.sha !== expectedHead || pr.head.repo?.full_name !== repository) {
    throw new Error('PR scope or head changed; trusted validation cannot be reused.');
  }
}

function selectRun(runs, sha, branch, repository) {
  return runs.filter(run => run.head_sha === sha && run.head_branch === branch &&
    run.event === 'pull_request_target' && run.path === WORKFLOW &&
    run.head_repository?.full_name === repository)
    .sort((a, b) => b.run_number - a.run_number || b.run_attempt - a.run_attempt)[0];
}

function validateResult(run, jobs) {
  if (run.status !== 'completed') return false;
  if (run.conclusion !== 'success') throw new Error(`Trusted workflow ${run.id}: ${run.conclusion}`);
  for (const name of JOBS) {
    const matches = jobs.filter(job => job.name === name);
    if (matches.length !== 1 || matches[0].status !== 'completed' || matches[0].conclusion !== 'success') {
      throw new Error(`Trusted job did not pass: ${name}`);
    }
  }
  return true;
}

async function waitForTrustedRun({ github, context, core, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), attempts = 60 }) {
  const { owner, repo } = context.repo;
  const expected = context.payload.pull_request;
  const repository = `${owner}/${repo}`;
  for (let attempt = 0; attempt < attempts; attempt++) {
    const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: expected.number });
    assertScope(pr, expected.head.sha, repository);
    const { data } = await github.rest.actions.listWorkflowRuns({ owner, repo,
      workflow_id: 'trusted-pr-gate.yml', head_sha: expected.head.sha,
      event: 'pull_request_target', per_page: 100 });
    const run = selectRun(data.workflow_runs, expected.head.sha, expected.head.ref, repository);
    if (run?.status === 'completed') {
      const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRunAttempt, {
        owner, repo, run_id: run.id, attempt_number: run.run_attempt, per_page: 100,
      });
      validateResult(run, jobs);
      const { data: latest } = await github.rest.pulls.get({ owner, repo, pull_number: expected.number });
      assertScope(latest, expected.head.sha, repository);
      await core.summary.addHeading('Trusted validation passed')
        .addLink(`Run ${run.id}, attempt ${run.run_attempt}`, run.html_url)
        .addRaw(`\n\nHead: ${expected.head.sha}\n`).write();
      return run.id;
    }
    await sleep(15000);
  }
  throw new Error('Timed out waiting for the exact-head trusted workflow.');
}

module.exports = { assertScope, selectRun, validateResult, waitForTrustedRun };
