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

## 风险与顾虑

- 当前后端 v3 `service_reference_v2` 严格结构不接收 v2 六组字段。因此 UI 按“仅默认六组使用 v2；出现折叠扩展字段使用 v3”选择单一版本载荷；若同次同时填写默认六组和折叠扩展，v3 合同无法承载默认六组。要无损合并两层，需要后续先扩展后端 v3 合同并补齐跨端合同测试，不能在本前端任务内私自发送未知字段。
- 本人历史 API 不返回“未关联旧数据数量”。页面只能在本人历史为空时解释未关联旧数据不会被猜测归属，不能断言某位技师确有多少条未关联旧记录。
- 尚未进行 390×844 真机、服务器、生产或门店现场验收；当前结论仅为本地自动化和生产构建通过。
