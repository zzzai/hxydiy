# Task 4 修复 scoped 只读复审

## 结论

此前报告的 2 个 P1 和 1 个 P2 均已解决，本次限定范围内未发现残余问题，Task 4 可通过本轮代码复审。

本次仅静态读取指定源码与测试，未运行测试、构建、服务器验证、提交或发布；除用户明确要求的本报告外，未编辑任何源码或文档。

## 三项复核

### 已解决：provider 跨门店复用缓存（原 P1）

- `src/core/dataProvider/index.ts:19-22`：`setStoreId` 每次更新门店上下文时都会执行 `this.cache.clear()`，因此同一 SPA 会话登出/重新登录或切换门店后，旧门店的 list/one 缓存不会继续命中。
- `tests/dataProvider.test.ts:60-72`：新增门店切换回归测试，在相同 resource 和 params 下先后设置 store 101/202，断言产生两次请求并返回不同结果，覆盖了原发现的复现路径。
- 残余：无。

### 已解决：TodayPage 越界恢复上钟/结账动作（原 P1）

- `src/pages/TodayPage.tsx:4`、`src/pages/TodayPage.tsx:54-63`：已移除 `startService`、`settleService`，动作请求表仅保留 `readyService` 和 `finishService`。
- `src/operations.ts:1`、`src/operations.ts:70-81`：`OperationAction` 已收窄为 `ready | finish`，状态映射只返回“确认服务”和“服务结束”；`assigned/ready` 与 `pending_checkout/pending_checkout` 不再生成上钟或结账动作。
- `tests/today-page-error.test.ts:5-8`、`tests/operations.test.ts:64-76`：负向源码断言和状态机单元测试同时覆盖不暴露 `startService` / `settleService` 及不映射相关状态。
- 残余：无。

### 已解决：同 URL 无差别 fallback 破坏统一错误契约（原 P2）

- `src/pages/TodayPage.tsx:33-41`：服务单看板只调用 `dataProvider.getList(resources.serviceOrders)`；失败直接进入页面统一错误态，不再通过 `.catch` 对同一 endpoint 发起第二次请求，也不会以原始 AxiosError 覆盖 provider 的 401/403/409 归一化错误。
- `tests/today-page-error.test.ts:4`：新增负向断言，明确禁止 `getLiveBoard` 和 `.catch(async` 回退路径，同时保留 provider、资源键、加载错误和重试检查。
- 残余：无。

## 复审判定

- P0：0
- P1：0
- P2：0
- 规格合规：此前三项发现均已按业务边界修复。
- 代码质量：修复范围集中，类型约束、实现和回归测试一致，未发现为修复引入的同类风险。
