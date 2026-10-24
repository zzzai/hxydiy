# 门店日常作业下一批预览验收 v1

日期：2026-10-24。基线 `26fff1c8243dcf845c2f507a3e82ce659fa7aa12`。
分支：`codex/admin-daily-operations-preview-20261024`。
工作区：hxy `/root/hxy-diy-development/mobile-workbench-closeout-20261023`。
状态：未提交候选及本地预览；没有合并、发布或生产数据写入。

## 交付

- PRD：`admin-daily-operations-prd-v1-20261024.md`，包含源码确认的问题、业务边界、优先级、三页交互及后续待核验事项。
- 三个真实 React 页面组件：今日工作台、到店选单、服务待办。模拟接口只提供合成数据；未开放请求默认拒绝，无真实 API 代理。
- 预览入口：`http://127.0.0.1:4215/tests/daily-operations-preview.html?page=today`。导航可切页，场景可切换正常、部分失败、空列表及保存失败。重置只清空演示数据。
- hxy 源码快照 `source-v2.tgz` SHA256：`4afdd75f9bda66393278fef40b28e36cd7928f0532f52da2234ffabb75841ecb`。本机快照哈希一致，依赖复用既有版本；本机未编辑业务源码。

## 已验证

- hxy 定向行为单元测试 5 passed：未知计数不伪装0、入口目的页、知悉与处理完成区分、异常响应不伪装空列表、枚举中文回退。
- hxy TypeScript no-emit 通过；git diff --check 通过。没有将这些称为完整生产构建或 CI。
- 浏览器交互 16 项记录见私有操作目录 `browser-acceptance-v2.json`：补记录汇总、待办入口、知悉后保留、处理记录回看、部分失败保留服务列表、失败保留输入并成功重试、列表/加选/座位失败恢复、只读角色页面、快速筛选与顾客参考迟到响应隔离等。
- 桌面 1365px、窄屏 390px 页面未横向溢出；窄屏跟进抽屉 DOM 宽度390px。完整页面截图已保存。IAB viewport-only 抽屉截图与模拟视口不一致，未纳入视觉证据。

## 尚未验收，不视为通过

- 真正隔离 API 的 assign/ack/resolve 写入回读、刷新持久化及门店/角色权限合同。
- 并发或重复点击对应的实际写请求数；目前实现有进行中保护，但不能用代码检查替代接口验收。
- 后端超时选单口径、异常200条分页限制；本轮明确显示范围，未更改服务器派生规则。
- 评价状态与备注一次保存、员工搜索参数、顾客档案和总部切店的真实接口巡检。
- 全量构建、CI、上线及企微/手机现场测试。本轮没有执行。

## 变更归属与保护

本轮仅修改 `TodayPage.tsx`、`ExceptionsPage.tsx`、`SelectionSessionsPage.tsx`，新增辅助函数、样式、定向测试、合成预览和两份文档。没有新增后端/迁移/依赖，没有改价格、会员、权限或支付路径。原有 node_modules 链接及 catalog/admin-live-preview 未跟踪文件均保留。

本机证据目录：`C:/Users/gaoji/Documents/ChatGPT/hxy-diy/output/admin-daily-preview-20261024/`。
服务器证据目录：`/root/hxy-diy-private-operations/admin-daily-preview-20261024/`。
