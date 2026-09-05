function docsOnly(paths) {
  return Array.isArray(paths) && paths.length > 0 && paths.every((path) =>
    typeof path === 'string' && !path.split('/').includes('..') && (
      /^docs\/.+\.md$/.test(path) ||
      ['README.md', 'AGENTS.md', 'tests/test_project_memory_contract.py'].includes(path)
    ));
}
module.exports = { docsOnly };

if (require.main === module) {
  const { execFileSync } = require('node:child_process');
  const [base, head] = process.argv.slice(2);
  let result = false;
  if ([base, head].every((sha) => /^[0-9a-f]{40}$/.test(sha || '') && !/^0+$/.test(sha))) {
    try {
      // Disable rename detection so a runtime file moved into docs stays full CI.
      const paths = execFileSync('git', ['diff', '--name-only', '--no-renames', '-z', base, head], { encoding: 'utf8' }).split('\0').filter(Boolean);
      result = docsOnly(paths);
    } catch { /* Missing base or invalid history must run full validation. */ }
  }
  console.log(`docs_only=${result}`);
}
