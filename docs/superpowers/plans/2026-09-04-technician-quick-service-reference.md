# 技师快速服务参考 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将技师画像改成 20～30 秒完成的点选式服务参考，并让同店技师在活动服务位中安全查看最近一次顾客已确认摘要。

**Architecture:** 继续使用现有 `customer_profile_records` 追加式事实表；新记录采用版本化 JSON 和稳定编码，关系列承载版本与确认状态。写接口保持旧版兼容，技师摘要接口只投影安全字段并写审计。前端把编码映射、请求构造与界面拆开，避免展示文案进入数据库。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、PostgreSQL/SQLite 测试；React、TypeScript、Ant Design、Node test runner、Vite。

**Status:** 2026-09-04 已按计划实现并完成本地验证；生产发布另按发布流程执行。

## Global Constraints

- [ ] 严格按 TDD：每一项先写失败测试并观察预期失败，再写最小实现并观察通过。
- [ ] 不读取或依赖 `_build_plan/`；不建设数据仓库、报表、推荐模型或自由标签系统。
- [ ] 保留旧版画像 API/历史记录兼容，不让新技师表单继续采集人口属性。
- [ ] 所有在线读取先按 `store_id` 收窄；摘要不返回备注、顾客原话、人口属性或联系方式。
- [ ] 每个任务完成后运行相关测试；全部实现后再运行后端目标测试、前端全量测试和构建。

---

### Task 1: 数据库与模型的数据底座

**Files:**
- Create: `hxy-server/alembic/versions/20260904_service_reference_v2.py`
- Modify: `hxy-server/app/models/customer_profile.py`
- Modify: `hxy-server/tests/test_alembic_contract.py`
- Modify: `hxy-server/tests/test_profile_record_contract.py`

- [ ] 新增失败契约测试，断言迁移以 `20260830_media_assets` 为父版本，包含 `schema_version`、`taxonomy_version`、`customer_confirmed`、`confirmed_at` 及两条复合索引。
- [ ] 运行：`python -m pytest tests/test_alembic_contract.py tests/test_profile_record_contract.py -q`，确认因缺少新字段/迁移失败。
- [ ] 编写幂等迁移：旧记录 `schema_version=1`、`customer_confirmed=false`；升级增加列与 `ix_customer_profile_store_user_confirmed_created`、`ix_customer_profile_store_technician_created`，降级逆序删除。
- [ ] 模型增加对应类型字段：`int`、`str | None`、`bool`、`datetime | None`，默认值与数据库默认一致。
- [ ] 重跑上述测试并确认通过。

### Task 2: v2 快记结构、校验与兼容写入

**Files:**
- Modify: `hxy-server/app/api/admin_v2.py`
- Modify: `hxy-server/tests/test_technician_profile_quick_note_contract.py`
- Modify: `hxy-server/tests/test_customer_profile_records_api.py`

- [ ] 先添加 API 失败测试：接受完整 v2；拒绝未知编码、未知字段、重复数组值、超过 100 字原话和医疗禁词；空数组与缺失字段保持不同；旧 v1 请求仍成功。
- [ ] 添加保存语义失败测试：v2 顶层 `schema_version=2`、`taxonomy_version=service_reference_v1`，确认后写 `customer_confirmed=true`、`confirmed_at`、`source=both`，未确认写 `source=service_observation`；幂等重放和内容冲突继续有效。
- [ ] 运行：`python -m pytest tests/test_technician_profile_quick_note_contract.py tests/test_customer_profile_records_api.py -q`，确认测试按预期失败。
- [ ] 定义禁止额外字段的嵌套 Pydantic 模型与固定枚举；数组在入库前拒绝重复，不静默修正；顾客原话去首尾空白并执行非医疗用语校验。
- [ ] 扩展 `CustomerProfileRecordIn`，以可选 v2 元数据区分新旧请求；统一生成规范化 profile、来源、确认时间，并把这些字段加入幂等指纹与响应。
- [ ] 保持管理员旧入口和旧画像列表可用；v2 至少包含一个受控选择或顾客原话，否则返回 422。
- [ ] 重跑上述测试并确认通过。

### Task 3: 活动服务位的安全摘要接口

**Files:**
- Modify: `hxy-server/app/api/technician.py`
- Modify: `hxy-server/tests/test_technician_portal_api.py`

- [ ] 先添加失败测试覆盖：同店活动占用可读、只取最新已确认且未被更正替代的 v2 记录、空摘要不审计、有效摘要写 `technician_view_service_reference` 审计。
- [ ] 添加边界失败测试：跨店/不存在返回 404；已释放或非活动状态返回 409 `SERVICE_REFERENCE_UNAVAILABLE`；未关联顾客返回 `record:null`；响应不含 quote、note、手机号、人口属性和创建人。
- [ ] 运行：`python -m pytest tests/test_technician_portal_api.py -q`，确认新接口测试失败。
- [ ] 实现 `GET /api/v1/technician/occupancies/{occupancy_id}/service-reference`：验证绑定技师、门店、活动占用、有效选单与顾客；查询条件包含门店、顾客、v2、已确认，并排除被后续记录引用的 ID，按创建时间和 ID 倒序取一条。
- [ ] 仅把稳定编码映射为约定中文安全字段、日期和固定提示；有记录时写包含 occupancy/customer/technician/source_record_id 的审计并提交，空结果不写审计。
- [ ] 重跑上述测试并确认通过。

### Task 4: 前端领域模型与 API

**Files:**
- Create: `admin-react/src/technician/serviceReference.ts`
- Modify: `admin-react/src/api.ts`
- Create: `admin-react/tests/technician-service-reference.test.ts`

- [ ] 先添加失败测试，覆盖稳定编码字典、选择顺序、空表单判断、v2 请求体、确认状态到来源的映射及摘要类型边界。
- [ ] 运行：`npm test -- --test-name-pattern="服务参考"`，确认因模块/函数缺失失败。
- [ ] 实现只含纯数据与纯函数的 `serviceReference.ts`：选项常量、类型、`hasServiceReferenceInput`、`buildServiceReferencePayload`；不得把中文 label 当 value 提交。
- [ ] 在 `api.ts` 增加 v2 创建类型和 `getTechnicianServiceReference(occupancyId)`，复用现有认证与错误处理。
- [ ] 重跑目标前端测试并确认通过。

### Task 5: 快记表单与上次摘要界面

**Files:**
- Modify: `admin-react/src/technician/TechnicianProfileSheet.tsx`
- Create: `admin-react/src/technician/TechnicianServiceReferenceDrawer.tsx`
- Modify: `admin-react/src/technician/TechnicianTodayPage.tsx`
- Modify: `admin-react/src/technician/technician-mobile.css`
- Modify: `admin-react/tests/technician-workspace.test.ts`
- Modify: `admin-react/tests/technician-service-reference.test.ts`

- [ ] 先添加失败契约/交互测试：界面不再包含年龄、性别、体型、职业；包含六组快捷字段、默认关闭的顾客确认、100 字原话、空表单拦截和 v2 保存请求。
- [ ] 添加摘要抽屉失败测试：活动顾客服务单显示查看入口；加载、空、有记录和错误状态清楚；渲染不引用 quote/note/人口属性。
- [ ] 运行目标测试并确认失败。
- [ ] 将 `TechnicianProfileSheet` 改成标签多选、单选按钮和确认开关；保存失败保留表单并复用原幂等键，保存成功才重置。
- [ ] 新增摘要抽屉并在今日服务单接入显式点击加载；没有活动 occupancy 或顾客时不显示入口。
- [ ] 增加移动端样式，保证 390×844 下底部操作不遮挡、主要触控项最小高度 40px。
- [ ] 重跑目标测试并确认通过。

### Task 6: 集成验证、文档与提交

**Files:**
- Modify: `docs/workstreams/technician.md`
- Modify: `WORK-STATUS.md`

- [ ] 运行后端：`python -m pytest tests/test_technician_profile_quick_note_contract.py tests/test_technician_portal_api.py tests/test_customer_profile_records_api.py tests/test_profile_record_contract.py tests/test_alembic_contract.py -q`。
- [ ] 运行迁移检查：`python -m alembic heads`，确认只有 `20260904_service_reference_v2`；在一次性测试库执行 upgrade，并确认新增列/索引存在。
- [ ] 运行前端：`npm test`、`npm run build`。
- [ ] 更新工作流与状态文档，只记录本地完成、测试证据和待生产发布，不误写已上线。
- [ ] 运行 `git diff --check` 与 `git status --short`，检查无临时文件、密钥或 `_build_plan/` 依赖。
- [ ] 按功能边界提交代码；完成代码审查后再决定合并和生产发布。
