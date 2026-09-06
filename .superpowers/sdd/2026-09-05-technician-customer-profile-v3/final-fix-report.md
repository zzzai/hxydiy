# 服务参考 v3 最终修复报告

日期：2026-09-05。仅本地修复和验证；未推送、未发布，未修改 CURRENT-STATE.md / WORK-STATUS.md。

## 提交与范围

- 修复提交：`196e3842540d34b54acbc64ac5980f824b36a8e7` — `fix: close profile v3 safety and legacy ownership gaps`。
- 报告随后的独立文档提交仅记录本次修复与验证事实。
- 基线：`5279869`；工作分支：`codex/technician/customer-profile-v3-design`。
- 业务实现、针对性合同测试、TEAM-MEMORY、服务参考契约与技师工作流已同步。

## 已修复行为

1. 当前活动服务位 service-reference GET 同时读取 v2/service_reference_v1 与 v3/service_reference_v2 的有效确认记录；继续排除本次服务、其他门店与已被更正记录。当前摘要和本人历史复用同一投影，逐层检查容器、列表及字符串类型，只输出已知编码对应文案；不会透传原话、个人概况或任意嵌套值。
2. 迁移覆盖已结束与正在进行的旧 occupancy。全部相关确认/结束审计均可解析到同门店的唯一 Staff-Technician 关联时才回填；多技师、无审计、未知员工或跨店证据保留 NULL。运行时对 NULL 的 in_service 做同样核对；只有 waiting_service 能首次写入当前技师归属，不能通过重复 confirm 抢写正在进行服务的归属。唯一原技师可以直接结束旧服务；无法唯一核对返回 `409 TECHNICIAN_SERVICE_OWNER_UNRESOLVED` 并指引店长现场核对，既有 `/api/v1/admin/occupancies/{id}/finish-service` 可结束服务且保留 NULL。
3. v3 至少包含实际内容。版本字段、空容器、空列表、null 和空白原话均不算内容，确认与未确认的空载荷都返回 422。选择不保存应使用现有“暂不记录”；有内容的未确认观察继续保存为 service_observation，确认标志 false、confirmed_at null。
4. 后端拒绝管理端创建或更正 v3，且阻止以 v1/v2 请求更正 v3 的绕过方式；v3 必须关联已完成服务。保留旧版本已有权限和必要更正兼容。
5. 本人历史摘要、confirmed/pending 筛选和总数均排除 superseded 记录。未确认更正替代旧确认后该服务变为 pending，不再显示旧确认摘要。
6. 管理端结构化展示隐藏未知稳定码与非字符串值，禁止 String(value) 原始内容回退；同时避免 constructor 等原型属性被误作标签。

## RED / GREEN

- 初始后端复现：`test_technician_profile_v3_contract.py` + `test_technician_service_history_api.py`：**8 failed / 11 passed**，覆盖五项缺口及正在进行旧服务迁移。
- 另加 malformed JSON 安全投影回归：**1 failed / 9 deselected**，真实失败为字典作为编码导致 TypeError；修复后通过。
- 管理端未知码展示复现：`technician-workspace.test.ts`：**1 failed / 11 passed**，确认原始手机号、对象字符串和未知文本被展示；修复后 **12 passed**。
- 后端修复专项：**20 passed**。
- 扩展迁移验证初次：**56 passed / 1 failed**。失败原因是旧 retention 测试用当前 metadata 构造旧库却保留新增归属列及约束，迁移重复加列导致 CircularDependencyError；已只修正旧库测试夹具，未在生产迁移加入跳过或容错逻辑。

## 最终验证

在 `hxy-server` 执行：

```powershell
python -m pytest tests/test_technician_portal_api.py tests/test_technician_service_history_api.py tests/test_technician_profile_v3_contract.py tests/test_technician_profile_quick_note_contract.py tests/test_customer_profile_records_api.py tests/test_profile_record_contract.py tests/test_occupancy_retention_migration.py -q
```

结果：**57 passed**。随后为有内容的未确认观察补充 source/confirmed_at 断言，单独重跑 v3 合同：**10 passed**。

在 `admin-react` 执行 `npm test`：**153 passed / 0 failed**；`npm run build`：TypeScript 与 Vite 构建通过。`python -m alembic heads`：唯一 head 为 `20260905_tech_history_v3`。`git diff --check` 通过。

既有提示：Starlette/httpx TestClient 弃用警告；Vite 大 chunk 警告；Windows Git LF/CRLF 提示。未发现本轮新增测试或构建错误。

## 迁移风险与发布前要求

- 本轮修改的是尚未发布的 v3 迁移；若候选环境已先执行原 v3 head，不能只重跑 upgrade head 并认为回填已更新。先核对数据库 revision 和进行中 NULL 归属数量，按部署窗口批准的迁移补证流程处理；运行时唯一审计回填可处理进行中的遗留 NULL。
- 回填依赖审计完整性和当前 Staff-Technician 映射；无法唯一解析的数据保持未归属，不根据原话、选单、邻近时间或执行请求者猜测归属。
- SQLite 临时数据库已验证迁移升级及旧迁移链。本轮未执行 PostgreSQL 服务器迁移、备份恢复、生产权限穿透、并发服务器验证或回滚演练。生产执行前需验证回填数量、NULL 分类及 SQL 时间/锁影响，并完成既定备份与恢复演练。
- 未归属旧服务由店长核对后经既有流程结束，不会写为某位技师的本人历史；若服务已有关联履约单，既有管理端履约边界仍生效，需要使用现有派钟服务流程。
- 未完成真机、网络重试或门店现场验收。自动测试和本地构建不代表服务器验证、生产上线或门店接受。

## Scoped 复审追加：跨次摘要数组契约

- 复审发现 `_history_profile_summary()` 的 v3 最小投影会省略空部位列表，而当前服务抽屉直接调用 `focus_areas.join()` / `avoid_areas.join()`。仅力度或单边部位记录会使抽屉报错。
- 本次仅在跨次 service-reference GET 响应组合处补上 `focus_areas=[]`、`avoid_areas=[]` 默认值，再由已有安全投影覆盖实际列表；history 卡片的最小摘要实现和输出均未修改。
- 新增三组真实 API 回归：仅力度、只有 focus、只有 avoid，验证写入与下一次服务读取成功，两字段始终为数组且文案正确。将同一 API 响应送入 Node.js 执行抽屉的数组 join 消费表达式，验证“未记录”回退与中文部位展示；本地 Node v22.19.0 已实际执行。仅 Python 的测试环境仍执行全部 API 数组断言，省略额外 Node 消费检查，不新增后端运行依赖。
- RED：三组均失败，缺少 focus_areas 或 avoid_areas；GREEN：`python -m pytest tests/test_technician_profile_v3_contract.py tests/test_technician_service_history_api.py tests/test_technician_portal_api.py -q` 为 **40 passed**，包括 history 精确最小摘要回归。`git diff --check` 通过。
- 追加提交主题：`fix: keep next-service reference area arrays stable`，实现、测试与本节随同一提交保存。没有推送、发布或其他范围变更。
