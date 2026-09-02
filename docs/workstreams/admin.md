# 管理后台与员工工作台工作流

更新时间：2026-08-31

## 负责范围

- 店长、总部管理员、普通员工工作台。
- 商品、项目、加项、技师档案、门店和服务位配置。
- 管理端导航、表格、表单、Refine 渐进式数据访问和门店隔离。
- 技师移动端保持独立路由；DIY 管理端不开放智慧宝派单、开房、离位、清洁或物理资源释放。

## 三端协作入口

- 统一代码仓库：GitHub `zzzai/hxydiy`。
- 管理端代码：`admin-react/`；顾客端和后端仅作为同仓库联调基线，不在本工作流中修改其业务。
- 共享记忆：`docs/TEAM-MEMORY.md`；任务交接：本目录；发布事实：`docs/WORK-STATUS.md`。
- Obsidian 打开仓库根目录即可阅读上述 Markdown；代码变更必须走 `codex/admin/<task>` 分支和 Pull Request。

## 本轮完成

- 管理权限 helper 对旧/非法角色统一返回结构化 403，避免 `ValueError` 变成 500。
- 总部管理员更新任意门店加项时不再错误要求绑定门店；店长权限边界保持不变。
- 运营统计测试夹具与真实埋点契约对齐，统计继续只信任规范化 `EventLog.store_id`。
- 对已下线的 DIY 物理资源接口更新契约测试，明确返回 `410 DIY_PHYSICAL_RESOURCE_FORBIDDEN`。
- 对齐正式菜单 13 项和实际 Alembic revision 的过期测试断言。

## 验证

- 管理端：`npm test`，107 passed；`npx tsc -b` 通过；`npm run build` 成功（Vite 4000 modules）。
- 后端管理/权限/目录/菜单/Alembic 组合回归：75 passed。
- 后端 API 契约：37 passed。
- 最新后端全量：`525 passed, 4 failed, 7 skipped`；4 个失败均为旧 `staff` 临时角色/占用续留迁移契约，当前实现按正式角色规则返回 `403 ROLE_MIGRATION_REQUIRED`，未作为生产通过依据。
- 构建仍有既有共享 chunk 体积警告（约 1.23 MB、710 KB），不影响构建成功。

## 发布与验收

- 本轮未发布生产，服务器 `current` 与生产 release 未改变。
- 待完成数据库备份与恢复演练、Manifest 校验、线上健康检查、跨店权限穿透、断网/并发幂等和智慧宝联调后，再安排生产发布与现场验收。

## CI/CD 自动化（2026-09-01，本地完成，未发布）

- `AI PR Review` 改为 PR 头 SHA 的必需 Check Run：模型异常、凭据缺失、JSON 无效和 `critical/high` 均失败，不再提交 `REQUEST_CHANGES`，不自动批准。
- 新增 `Trusted PR Gate`：默认分支工作流拒绝 fork，在无 secrets、只读权限和隔离 Runner 中检出 PR merge ref，运行静态契约、管理端、顾客端和后端验证，并将结果写回 PR 头 SHA。
- 新增 `Auto Merge PR`：只处理同仓库、非草稿、目标 `main` 且当前 head SHA 的全部必需检查成功的 PR，使用精确 SHA squash 合并；PR 更新或 GitHub 409/422 时跳过。
- `CI` 继续提供 PR 开发反馈和 `main` 发布前回归；`Deploy Production` 继续绑定 `production` Environment，生产审批不因 PR 自动合并而取消。
- 发布脚本与 compose/Dockerfile 保持 PostgreSQL 备份/恢复演练、Manifest、原子切换、健康检查、失败回滚和 Alembic 迁移阻断。

## 自动化验证

- `python -m unittest tests/test_github_automation_contract.py`：7 passed。
- `bash -n deploy/diy/create-release.sh deploy/diy/activate-release.sh deploy/diy/deploy-production.sh`：通过。
- `git diff --check`：通过。
- PR #6 分支 CI：Static contracts、Admin tests and build、Customer tests and build、Backend tests 全部通过；新增可信门禁和自动合并工作流待合并到 `main` 后才会对后续 PR 生效。
- Codex Security diff scan（发布脚本/Compose）：4 个文件、0 个可报告发现；未执行真实生产发布。

## 生产状态

- 本轮仅完成仓库自动化基础设施，未发布生产，未修改生产数据库或 `current`。
- 待 monorepo 基线合并、GitHub Ruleset required checks 配置、`production` Environment 审批人和 Secrets 配置后，才可启用真实自动合并/发布。
- GitHub 主分支尚未加载 `AI PR Review`、`Trusted PR Gate` 和 `Auto Merge PR`；合并本 PR 后才会对后续 PR 生效，当前 PR 不会追溯触发。
