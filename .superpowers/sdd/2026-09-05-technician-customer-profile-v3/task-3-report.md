# 任务 3 报告：分层快记、顾客确认摘要和本人历史页面

## 状态

- 已将技师历史从门店级 `ServiceOrderList` 切换为 `/technician/service-history`，使用本人移动卡片展示。
- 已保留默认六组 v2 快记，并增加折叠的 v3“更多服务记忆”。
- 保存前必须在摘要弹窗中明确选择“顾客已确认”或“未确认，仅保存为本次观察”；只有前者写入长期摘要确认状态。
- 未改后端、迁移、管理后台页面或跨端文档，未加入特定项目/仓点限制，未采集收入字段。

## RED

先新增 `technician-profile-v3.test.ts` 和移动状态文案测试，再运行：

`npm test -- --test-name-pattern="v3 快记|本人历史"`

结果：`140 passed, 4 failed`。失败原因符合预期：缺少“更多服务记忆”、技师专用历史 API、移动历史页面及画像状态映射。

## GREEN

- 默认区保留本次重点、避开或谨慎、力度、温度、反馈和下次建议。
- 折叠区只在技师主动展开时显示个人背景、工作生活、顾客自述的服务相关情况和本次反应；原话最多 100 字，并提示“顾客自述，服务前请再次确认”。
- 保存摘要弹窗未选择确认状态时禁用提交；未确认记录以本次观察保存。
- 历史页支持全部、待补记、已确认筛选，显示完成日期、服务位、项目、时长、脱敏顾客、确认状态与服务端白名单摘要。
- 加载失败提供可见错误与重试按钮；无本人服务、筛选无结果、未关联旧数据说明分别呈现。

## 测试与构建

- `npm test`：`144 passed, 0 failed`。
- `npx tsc -b`：退出码 0。
- `npx vite build`：退出码 0，4004 modules transformed，构建完成；保留既有大 chunk 警告，本任务不重构分包。

## 变更文件

- `admin-react/src/api.ts`
- `admin-react/src/technician/TechnicianProfileSheet.tsx`
- `admin-react/src/technician/TechnicianServiceHistoryPage.tsx`
- `admin-react/src/technician/TechnicianHistoryPage.tsx`
- `admin-react/src/technician/technicianMobile.ts`
- `admin-react/src/technician/technician-mobile.css`
- `admin-react/tests/technician-profile-v3.test.ts`
- `admin-react/tests/technician-mobile.test.ts`
- `admin-react/tests/technician-workspace.test.ts`（更新既有 v2 源码守卫，使其允许 v3 稳定编码并验证显式确认流程）

## 自审

- 本人历史不再导入或渲染门店级 `ServiceOrderList`/桌面 Table。
- 历史数据只消费服务端本人接口的脱敏白名单，不展示价格、联系方式、会员资产、自由原话或收入。
- 未确认记录不会写 `customer_confirmed=true`；确认状态必须由技师在保存前主动选择。
- 请求失败不会伪装成空态，并可原地重试。
- v2 构造器和原有调用仍保留，现有 v2 测试继续通过。

## 初次提交风险与顾虑（已由修复轮次 1 处理）

- 初次提交时 v3 严格结构不接收默认六组；修复轮次 1 已扩展合同并改为单一 v3 载荷。
- 初次提交时本人历史 API 不返回未关联旧数据数量；修复轮次 1 已增加最小聚合计数并实现互斥空态。
- 尚未进行 390×844 真机、服务器、生产或门店现场验收；当前结论仅为本地自动化和生产构建通过。

## 修复轮次 1（审查主路径缺陷）

### RED

- 后端新增 v3 混填单记录、完整枚举和 `unassigned_legacy_count` 行为测试；首次运行 `3 failed, 8 passed`，分别因严格 v3 模型拒绝六组/消费字段、枚举不完整、接口缺少旧数据计数而失败。
- 前端新增混填载荷、强类型历史摘要白名单、互斥空态和 Modal 实际摘要断言；首次运行 `4 failed, 143 passed`。

### 修复

- 扩展严格 v3 模型，使默认六组与扩展字段在一个 `schema_version=3`、`service_reference_v2` 记录中保存；数组继续拒绝重复，模型继续拒绝未知字段/编码，原 v2 类型与构造器不变。
- 补齐年龄段、体型、职业场景、睡眠、服务相关情况、决策关注和预算倾向的受控枚举及中文 taxonomy；未增加收入、资产、负债字段。
- 技师画像页统一提交单一 v3 载荷；Modal 展示所选字段的中文“待保存摘要”，并继续要求明确选择顾客确认或本次观察。
- 历史卡片只消费 `TechnicianHistoryProfileSummary` 显式白名单，通过固定映射生成展示行；未知键、自由原话、联系方式和嵌套对象不会渲染。
- 本人历史接口只增加当前门店、已结束且服务技师仍为空的聚合计数 `unassigned_legacy_count`，不返回旧记录内容。前端以纯分类函数互斥展示“尚无本人已完成服务”“旧数据未关联”“当前筛选无结果”；加载失败仍为独立可恢复错误状态。

### GREEN 与验证

- `python -m pytest tests/test_technician_profile_v3_contract.py tests/test_technician_service_history_api.py tests/test_technician_portal_api.py -q`：`28 passed, 1 warning`；warning 为既有 Starlette/httpx 弃用提示。
- `npm test`：`147 passed, 0 failed`。
- `npx tsc -b`：退出码 0。
- `npx vite build`：退出码 0，4004 modules transformed；仅既有大 chunk 警告。
- `git diff --check`：通过；仅 Git 的 LF/CRLF 工作区提示。

### 修复后风险

- v3 taxonomy 当前仍由前后端受控常量分别定义；两端合同测试覆盖提交路径和关键完整枚举，但尚未建设前端运行时动态字典加载。
- `unassigned_legacy_count` 是门店级不可归属历史总数，仅作空态解释，不代表这些记录属于当前技师。
- 仍未执行服务器、生产或 390×844 门店现场验收。
