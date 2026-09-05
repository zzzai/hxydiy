function eligibleRun(run, sha, latest, repo) {
  return /^[0-9a-f]{40}$/.test(sha || '') && sha === latest &&
    run?.head_sha === sha && run.head_branch === 'main' && run.event === 'push' &&
    run.path === '.github/workflows/ci.yml' && run.status === 'completed' &&
    run.conclusion === 'success' && run.head_repository?.full_name === repo;
}
function hasBuilds(artifacts, sha) {
  return ['admin', 'customer'].every((name) => artifacts.some((item) =>
    item.name === `${name}-dist-${sha}` && item.expired === false));
}
module.exports = { eligibleRun, hasBuilds };
