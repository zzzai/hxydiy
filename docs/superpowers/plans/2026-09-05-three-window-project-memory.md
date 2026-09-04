# Three-Window Project Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the single GitHub monorepo the reliable source of shared project memory for the customer, admin, and technician Codex windows.

**Architecture:** Keep memory as small, Git-tracked Markdown files in the same repository as the code. Each window works in an isolated worktree, loads only a compact current-state entry plus its own workstream, and retrieves contracts/history only when needed. A static contract test prevents the core memory files and the current service-reference decision from silently disappearing.

**Tech Stack:** Git worktrees, Markdown, Python `unittest`, existing GitHub PR/CI workflows.

## Global Constraints

- All user-facing text and project instructions remain Simplified Chinese.
- Do not modify business runtime code, database schema, production services, secrets, or existing dirty worktrees.
- `origin/main` is the only shared truth; uncommitted files and chat history are not shared memory.
- Obsidian is an editor only; no Obsidian Sync, vector database, RAG, or new SaaS dependency.
- Default context must remain small: `AGENTS.md`, `CONTEXT-MANIFEST.md`, `CURRENT-STATE.md`, and one workstream file.
- Production facts must match the verified release `main-bf0bddf-20260905-1`, image `hxy-diy-api:bf0bddf`, and Alembic head `20260904_service_reference_v2`.

---

### Task 1: Establish the memory contract and canonical current state

**Files:**
- Create: `tests/test_project_memory_contract.py`
- Create: `docs/CONTEXT-MANIFEST.md`
- Create: `docs/CURRENT-STATE.md`
- Modify: `docs/TEAM-MEMORY.md`

**Interfaces:**
- Consumes: verified production facts and the `service_reference_v1` contract already present in `origin/main`.
- Produces: canonical current context files used by all three window prompts and workstreams.

- [ ] **Step 1: Write the failing static contract test**

```python
class ProjectMemoryContractTests(unittest.TestCase):
    def test_core_memory_files_are_tracked_and_define_authority(self):
        for relative in ("docs/CONTEXT-MANIFEST.md", "docs/CURRENT-STATE.md", "docs/TEAM-MEMORY.md"):
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
        manifest = read("docs/CONTEXT-MANIFEST.md")
        self.assertIn("origin/main", manifest)
        self.assertIn("生产服务器", manifest)

    def test_current_state_matches_verified_production(self):
        current = read("docs/CURRENT-STATE.md")
        self.assertIn("main-bf0bddf-20260905-1", current)
        self.assertIn("20260904_service_reference_v2", current)

    def test_team_memory_uses_the_versioned_service_reference_contract(self):
        memory = read("docs/TEAM-MEMORY.md")
        self.assertIn("service_reference_v1", memory)
        self.assertNotIn("第一屏填写年龄段、性别、体型、职业场景", memory)
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `python -m unittest tests.test_project_memory_contract -v`

Expected: FAIL because `CONTEXT-MANIFEST.md` and `CURRENT-STATE.md` do not exist on the branch and `TEAM-MEMORY.md` contains the retired decision.

- [ ] **Step 3: Create the context manifest**

Define:

```markdown
默认读取：AGENTS.md、CONTEXT-MANIFEST.md、CURRENT-STATE.md、本端 workstream。
按需读取：TEAM-MEMORY、contracts、WORK-STATUS。
权威顺序：实时生产 → origin/main 代码/迁移/测试 → contracts → CURRENT-STATE → TEAM-MEMORY → workstreams → history → chat。
```

- [ ] **Step 4: Create the current-state entry**

Record the verified production release, image, Alembic head, HTTP checks, three-end status, known baseline status, and only the next cross-end actions. Keep the file below approximately 150 lines.

- [ ] **Step 5: Reconcile team memory**

Replace the retired demographic-first technician profile decision with:

```markdown
服务参考使用 schema_version=2、taxonomy_version=service_reference_v1 和稳定英文编码；区分顾客表达、技师观察、顾客确认与下次建议。结构化服务参考不得转写为普通运营标签。
```

- [ ] **Step 6: Run the contract test and commit**

Run: `python -m unittest tests.test_project_memory_contract -v`

Expected: PASS.

Commit: `docs: establish canonical project memory`

---

### Task 2: Align three window workflows and startup instructions

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Create: `docs/AI-WINDOW-PROMPTS.md`
- Modify: `docs/workstreams/customer.md`
- Modify: `docs/workstreams/admin.md`
- Modify: `docs/workstreams/technician.md`
- Modify: `docs/WORK-STATUS.md`
- Modify: `tests/test_project_memory_contract.py`

**Interfaces:**
- Consumes: canonical files created in Task 1.
- Produces: consistent start/end protocol for the three Codex windows and an accurate production handoff record.

- [ ] **Step 1: Extend the failing contract test for all window files**

```python
def test_each_window_has_a_bounded_workstream_and_prompt(self):
    prompts = read("docs/AI-WINDOW-PROMPTS.md")
    for name in ("customer", "admin", "technician"):
        self.assertTrue((REPO_ROOT / f"docs/workstreams/{name}.md").is_file())
    for heading in ("顾客端窗口", "管理端窗口", "技师端窗口"):
        self.assertIn(heading, prompts)
    self.assertIn("git fetch origin", prompts)
    self.assertIn("docs/CURRENT-STATE.md", prompts)
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m unittest tests.test_project_memory_contract -v`

Expected: FAIL because the tracked main branch does not yet contain `AI-WINDOW-PROMPTS.md`.

- [ ] **Step 3: Tighten repository instructions**

Add concise rules to `AGENTS.md` and `README.md`:

```markdown
- Each task starts from the latest origin/main in an isolated worktree.
- Shared facts count only after merge to main.
- Cross-end contract changes update code, contract tests, TEAM-MEMORY, and the relevant contract in one PR.
- The production publisher updates CURRENT-STATE and WORK-STATUS.
```

- [ ] **Step 4: Add compact three-window prompts**

Create one common startup block and three short role appendices. Do not duplicate the full product history or PRD. Each appendix names its directories, responsibilities, forbidden scope, tests, and workstream file.

- [ ] **Step 5: Update the three workstreams**

- Customer: no implementation change; recognize the backend-owned service-reference contract only if customer confirmation is later exposed.
- Admin: record the need to render v2 records, consume a backend-owned taxonomy, and add basic store aggregation without mixing structured fields into generic tags.
- Technician: mark the quick service reference as merged and published, including release and Alembic head.

- [ ] **Step 6: Append the production memory rollout record**

Add a short top entry to `WORK-STATUS.md` with the already verified PR #15 release, backup, tests, and health status. Do not rewrite old history.

- [ ] **Step 7: Run static tests and commit**

Run:

```powershell
python -m unittest tests.test_project_memory_contract -v
python -m unittest tests.test_github_automation_contract -v
git diff --check
```

Expected: all tests pass and whitespace check is clean.

Commit: `docs: align three-window collaboration workflow`

---

### Task 3: Verify, publish, and hand off the shared memory

**Files:**
- Verify only: all files changed in Tasks 1 and 2.

**Interfaces:**
- Consumes: two reviewed documentation commits.
- Produces: a clean branch, GitHub PR, and short instructions for the other two windows.

- [ ] **Step 1: Run final verification**

Run:

```powershell
python -m unittest discover -s tests -p "test_*contract.py" -v
git diff --check origin/main...HEAD
git status --short
```

Expected: contract tests pass, diff check is clean, and no uncommitted files remain.

- [ ] **Step 2: Review the branch diff**

Confirm that no files under `diy-web/`, `admin-react/`, `hxy-server/app/`, or `hxy-server/alembic/` changed.

- [ ] **Step 3: Push and create a PR**

Push `codex/shared/project-memory-v2`, create a concise PR, and merge after required checks. Do not publish production because this change is documentation and static contracts only.

- [ ] **Step 4: Hand off to the other windows**

Send only this operational instruction:

```text
保存你当前分支的未提交工作；执行 git fetch origin，将最新 origin/main 合入或 rebase 到当前任务分支；重新开始任务时读取 AGENTS.md、docs/CONTEXT-MANIFEST.md、docs/CURRENT-STATE.md 和本端 workstream。不要复制旧聊天或覆盖当前工作区。
```
