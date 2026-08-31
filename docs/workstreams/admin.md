# 管理后台与员工工作台工作流

更新时间：2026-08-31

## 负责范围

- 店长、总部管理员、普通员工工作台。
- 商品、项目、加项、技师档案、门店和服务位配置。
- 管理端导航、表格、表单、Refine 渐进式数据访问和门店隔离。
- 技师移动端保持独立路由；DIY 管理端不开放智慧宝派单、开房、离位、清洁或物理资源释放。

## 本轮完成

- 管理权限 helper 对旧/非法角色统一返回结构化 403，避免 `ValueError` 变成 500。
- 总部管理员更新任意门店加项时不再错误要求绑定门店；店长权限边界保持不变。
- 运营统计测试夹具与真实埋点契约对齐，统计继续只信任规范化 `EventLog.store_id`。
- 对已下线的 DIY 物理资源接口更新契约测试，明确返回 `410 DIY_PHYSICAL_RESOURCE_FORBIDDEN`。
- 对齐正式菜单 13 项和实际 Alembic revision 的过期测试断言。

## 验证

- 管理端：`npm test`，107 passed；`npm run build` 成功。
- 后端管理/权限/目录/菜单/Alembic 组合回归：75 passed。
- 后端 API 契约：37 passed。
- 当前后端全量仍有历史角色、旧占用续留接口等迁移契约待清理，不能据此宣称生产可用。

## 发布与验收

- 本轮未发布生产，服务器 `current` 与生产 release 未改变。
- 待完成数据库备份与恢复演练、Manifest 校验、线上健康检查、跨店权限穿透、断网/并发幂等和智慧宝联调后，再安排生产发布与现场验收。

## CI/CD 自动化（2026-08-31，本地完成，未发布）

- 新增 `AI PR Review`：使用 `pull_request_target` 只读 PR diff；高危问题请求修改，不自动批准或合并。
- 新增 `CI`：仓库契约、敏感信息扫描、管理端/顾客端测试与构建、后端测试和发布资格检查。
- 新增 `Deploy Production`：只接收 `main` 成功 CI，使用 `production` Environment 审批、固定 SSH 主机指纹、PostgreSQL 备份/恢复演练、Manifest 校验、原子切换和失败回滚。
- 新增 `deploy/diy/*` 发布脚本与 compose/Dockerfile；Alembic 迁移变化默认阻断，不自动 downgrade。

## 自动化验证

- `python -m unittest tests/test_github_automation_contract.py`：5 passed。
- `bash -n deploy/diy/create-release.sh deploy/diy/activate-release.sh deploy/diy/deploy-production.sh`：通过。
- `git diff --check`：通过。
- PR #6 分支 CI：Static contracts、Admin tests and build、Customer tests and build、Backend tests 全部通过。
- Codex Security diff scan（发布脚本/Compose）：4 个文件、0 个可报告发现；未执行真实生产发布。

## 生产状态

- 本轮仅完成仓库自动化基础设施，未发布生产，未修改生产数据库或 `current`。
- 待 monorepo 基线合并、GitHub `production` Environment 审批人和 Secrets 配置后，才可启用真实自动发布。
- GitHub 主分支尚未加载 `AI PR Review` 工作流；合并本 PR 后才会对后续 PR 生效，当前 PR 不会追溯触发。
