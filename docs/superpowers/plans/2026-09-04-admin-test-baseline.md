# 管理后台全量测试基线收口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不修改生产权限和业务行为的前提下，校正当前 11 个过期后端测试失败，使全量回归重新可信。

**Architecture:** 只调整测试夹具和断言，使其匹配现行角色模型、Alembic 唯一迁移链及 release/current 发布方式。生产 API、认证逻辑、迁移脚本和部署配置保持不变。

**Tech Stack:** Python 3.11、pytest/unittest、FastAPI TestClient、SQLAlchemy、Alembic、Docker Compose 发布契约。

## Global Constraints

- 旧 `staff` 测试账号不恢复登录，不新增普通员工角色。
- 正式角色仅使用 `admin`、`manager`、绑定技师档案的 `technician`。
- 不修改顾客端、技师端业务或智慧宝逻辑。
- 不通过修改生产代码迎合过期测试。

---

### Task 1: 对齐账号与服务位续留测试夹具

**Files:**
- Modify: `hxy-server/tests/test_occupancy_retention_api.py`
- Modify: `hxy-server/tests/test_staff_temporary_expiry.py`

**Interfaces:**
- Consumes: `Staff.role`、`Staff.status`、`Staff.technician_id` 与现行登录校验。
- Produces: 使用规范角色且仍覆盖续留、批量释放和临时账号过期行为的测试夹具。

- [ ] **Step 1: 单独运行现有失败，保留 RED 证据**

Run: `python -m pytest tests/test_occupancy_retention_api.py tests/test_staff_temporary_expiry.py -q`

Expected: 4 项因 `ROLE_MIGRATION_REQUIRED` 失败。

- [ ] **Step 2: 将续留测试的普通操作账号改为 manager**

在 `test_occupancy_retention_api.py` 中将前台夹具的 `role="staff"` 改为 `role="manager"`；保留独立 `admin` 夹具验证批量释放边界，不改接口实现。

- [ ] **Step 3: 将临时技师测试改为真实技师绑定**

在 `test_staff_temporary_expiry.py` 中创建 `Technician(store_id=store.id, code=..., name=...)`，flush 后创建 `role="technician"` 且 `technician_id=technician.id` 的 Staff；成功登录断言改为 `role == "technician"`。过期测试也使用同样规范绑定，确保失败原因仍是过期而非角色错误。

- [ ] **Step 4: 运行专项测试确认 GREEN**

Run: `python -m pytest tests/test_occupancy_retention_api.py tests/test_staff_temporary_expiry.py -q`

Expected: 7 passed。

- [ ] **Step 5: 提交账号测试基线**

```bash
git add hxy-server/tests/test_occupancy_retention_api.py hxy-server/tests/test_staff_temporary_expiry.py
git commit -m "test: align admin account fixtures with normalized roles"
```

### Task 2: 对齐 Alembic 迁移测试基线

**Files:**
- Modify: `hxy-server/tests/test_occupancy_retention_migration.py`
- Modify: `hxy-server/tests/test_task2_alembic_chain.py`

**Interfaces:**
- Consumes: 当前 tracked Alembic revisions，唯一 head `20260830_media_assets`。
- Produces: 可从 `20260815_member_grants` 构造旧库并升级至当前 head 的测试。

- [ ] **Step 1: 单独运行迁移失败，保留 RED 证据**

Run: `python -m pytest tests/test_occupancy_retention_migration.py tests/test_task2_alembic_chain.py -q`

Expected: media_assets 重复建表与旧 head 断言两项失败。

- [ ] **Step 2: 修正旧库元数据边界**

在构造 `previous_metadata` 时，与已经排除的 `service_position_qrs` 一样排除 `media_assets`，因为该表由 `20260830_media_assets` 在 stamp 之后创建；保留现有字段移除逻辑。

- [ ] **Step 3: 对齐唯一迁移 head**

将 `test_task2_alembic_chain.py` 的唯一 head 期望从 `20260829_tech_profile_note` 更新为 `20260830_media_assets`，继续断言历史基点存在。

- [ ] **Step 4: 运行迁移专项确认 GREEN**

Run: `python -m pytest tests/test_occupancy_retention_migration.py tests/test_task2_alembic_chain.py -q`

Expected: 3 passed。

- [ ] **Step 5: 提交迁移测试基线**

```bash
git add hxy-server/tests/test_occupancy_retention_migration.py hxy-server/tests/test_task2_alembic_chain.py
git commit -m "test: align alembic checks with current migration head"
```

### Task 3: 删除失效发布断言并保留真实发布契约

**Files:**
- Modify: `hxy-server/tests/test_release_consistency.py`
- Modify: `hxy-server/tests/test_release_layout.py`
- Modify: `hxy-server/tests/test_release_scripts.py`

**Interfaces:**
- Consumes: `deploy/diy/docker-compose.hxy.yml` 的 `${HXY_DIY_CURRENT:-../../current}` build context、FastAPI `release_static.py` 静态站点挂载、现有 release scripts。
- Produces: 验证仓库实际支持的 immutable release/current 机制，不依赖未跟踪临时文件或已删除 nginx 配置。

- [ ] **Step 1: 单独运行发布失败，保留 RED 证据**

Run: `python -m pytest tests/test_release_consistency.py tests/test_release_layout.py tests/test_release_scripts.py -q`

Expected: 5 项因未跟踪临时脚本、已删除 nginx 文件及旧 compose 文本断言失败。

- [ ] **Step 2: 移除临时发布工具源码解析测试**

删除 `test_catalog_publish_tool_targets_every_configured_service` 及仅为它使用的 `ast`、`TARGET_CODES` import。该测试引用仓库外 `tmp-codex/publish_body_part_catalogs.py`，不验证可发布代码行为；保留 `configure_footbath_options.py` 被镜像包含的测试。

- [ ] **Step 3: 将发布布局测试对齐 FastAPI 静态挂载**

把 compose 断言改为包含 `context: ${HXY_DIY_CURRENT:-../../current}` 与 release Dockerfile；把已删除 nginx 文件断言替换为调用 `mount_release_static_files` 的临时目录行为测试，验证 `/admin`、`/technician` 和 `/` 均由同一 release 根目录挂载。

- [ ] **Step 4: 校正发布脚本的现行配置断言**

将 build context 期望对齐 `${HXY_DIY_CURRENT:-../../current}`。短信/号码认证变量断言统一为当前可选透传形式 `${VARIABLE:-}`，与微信支付变量契约一致。

- [ ] **Step 5: 运行发布专项确认 GREEN**

Run: `python -m pytest tests/test_release_consistency.py tests/test_release_layout.py tests/test_release_scripts.py -q`

Expected: 所有发布专项通过或仅因 Windows 缺少 Git Bash按既有条件跳过。

- [ ] **Step 6: 提交发布测试基线**

```bash
git add hxy-server/tests/test_release_consistency.py hxy-server/tests/test_release_layout.py hxy-server/tests/test_release_scripts.py
git commit -m "test: align release checks with immutable current layout"
```

### Task 4: 全量验证与 GitHub 交付

**Files:**
- Modify: `docs/WORK-STATUS.md`

**Interfaces:**
- Consumes: Tasks 1-3 的测试基线提交。
- Produces: 可复核的全量测试结果与 GitHub 备份。

- [ ] **Step 1: 运行后端全量测试**

Run: `python -m pytest -q`

Expected: 0 failed；允许既有明确 skip 和 Starlette/httpx 弃用 warning。

- [ ] **Step 2: 检查差异和文档状态**

Run: `git diff --check`、`git status --short`、`git diff origin/main...HEAD`

在 `docs/WORK-STATUS.md` 记录修改范围、测试结果、未修改生产行为、未发布生产。

- [ ] **Step 3: 提交并推送**

```bash
git add docs/WORK-STATUS.md
git commit -m "docs: record backend test baseline cleanup"
git push -u origin codex/admin/test-baseline
```

- [ ] **Step 4: 创建并核验 PR**

创建目标为 `main` 的 PR，描述测试基线调整、生产行为不变、全量验证结果及未发布生产；只在 GitHub 显示真实合并结果后报告已合入。
