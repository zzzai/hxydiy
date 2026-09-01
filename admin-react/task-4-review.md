# Task 4 只读复审报告

## 结论

Task 4 当前不可判定为完成，存在 2 个 P1 和 1 个 P2；未发现 P0。主要阻断是 provider 缓存没有门店隔离，以及 TodayPage 在迁移样板资源时恢复了明确禁止的服务动作。接口分层的基本形态、`store_id` 对 create/update 输入的覆盖防护、`X-Idempotency-Key`、`If-Match` 以及 401/403/409 归一化骨架均已建立，但下述问题会突破 Task 4 的业务边界或错误处理契约。

本次按要求仅做静态只读复审，未运行测试、构建、服务器验证、提交或发布。唯一工作区写入为本报告。`tests/today-page-error.test.ts` 第 5-8 行与当前 `TodayPage.tsx` 的导入内容存在确定性冲突，因此即使不执行测试，也可以确认该测试当前不会通过。

## 发现

### P1：provider 缓存未按门店隔离，切换账号后可返回上一门店数据

- 文件与行号：`src/core/dataProvider/index.ts:19`、`src/core/dataProvider/index.ts:26-31`、`src/core/dataProvider/index.ts:34-39`
- 依据：`setStoreId` 只替换 `this.storeId`，既不清空缓存，也不把门店标识纳入 `buildQueryKey` / `resourceQueryKey`。`getList` 和 `getOne` 会在发请求前直接命中全局 singleton 的缓存。当前入口在同一 SPA 会话内登出时只执行 `dataProvider.setStoreId(null)`，再次登录又执行 `setStoreId(newStoreId)`；因此 A 店账号读取过的资源可以被 B 店账号以相同 resource/params/id 直接从内存取得，甚至不会经过服务器的 token 门店校验。这违反“门店上下文不可被输入覆盖/串店”的边界。
- 修复建议：至少在 `setStoreId` 的门店值变化时清空全部缓存；更稳妥的是将受信任的门店上下文（必要时连同账号/角色身份）纳入所有缓存键，并在登录、登出、401 清会话时显式清缓存。补充“同一浏览器先登录 store A、登出、再登录 store B，相同查询必须重新请求且不得返回 A 数据”的测试。

### P1：TodayPage 恢复了上钟和结账写操作，且现有边界测试确定失败

- 文件与行号：`src/pages/TodayPage.tsx:4`、`src/pages/TodayPage.tsx:54-63`；对应约束测试 `tests/today-page-error.test.ts:5-8`
- 依据：页面重新导入并注册 `startService`、`settleService`。状态机在相应状态下会渲染“上钟”和“结账”，用户确认后会实际调用写接口；这不是死代码。后端 `start` 会推进服务单、派工、技师、服务位及 DIY 占用状态，`settle` 会完成订单/到店记录并改变资源状态。Task 4 只要求把服务单列表迁移到 provider 并保持既有行为，不能借迁移恢复已收口动作。指定测试还明确断言 TodayPage 不得出现 `startService`、`settleService`，当前源码会直接使该测试失败。
- 修复建议：TodayPage 仅保留当前业务允许的 `ready` 与 `finish` 动作，移除 `startService`、`settleService` 的导入和请求映射；同时让页面动作 allowlist 与状态展示函数一致，避免 `getNextOperation` 返回页面无权执行的动作。保留并运行现有负向测试，另加渲染/交互测试确认禁用动作不会生成按钮或请求。

### P2：所谓旧接口回退会对同一 URL 重发所有失败请求，破坏 401/403/409 统一错误语义

- 文件与行号：`src/pages/TodayPage.tsx:33-41`；资源定义 `src/core/resources/index.ts:3`
- 依据：`resources.serviceOrders` 是 `operations/live-board`，而 `getLiveBoard()` 也请求 `/operations/live-board`。provider 失败后的 `.catch(...)` 并未切到不同兼容接口，只是用同一个 axios client 对同一 URL 再请求一次。它会无差别吞掉 provider 已归一化的 `DataProviderError`，包括 401/403/409，然后把第二次请求产生的原始 AxiosError 交给页面；结果是重复请求/重复提示，权限或冲突详情可能退化为通用 axios 文案，401 期间还可能在跳转同时再次发起未授权请求。这与 Task 4 要求统一处理 401/403/409 及 TodayPage 明确加载错误/重试反馈相冲突。
- 修复建议：当前两条路径等价，应直接使用 provider 并让归一化错误进入页面错误态。若确有兼容后端，必须把 fallback 指向真实不同的旧 endpoint/adapter，且只对明确的兼容信号（例如 404/501 或响应契约不匹配）回退；401/403/409 必须原样抛出，重试只由用户点击触发。增加测试模拟 provider 的 401/403/409，断言不调用 legacy loader、错误文案保留且只发起一次请求。

## 其余审查结论

- `withBoundStore` 会从 create/update 输入中剔除调用方提供的 `store_id`，有绑定门店时以 provider 上下文覆盖，无绑定门店时不透传该字段；该局部实现符合输入不可覆盖要求。
- `create` 在提供幂等键时发送 `X-Idempotency-Key`，`update` 在提供版本时发送 `If-Match`；成功变更后会失效资源缓存，接口形态符合 Task 4 计划。
- `normalizeProviderError` 已将 401/403/409 映射为稳定错误码，401 会清认证并跳转；但 TodayPage 的无差别 catch/fallback 目前绕开了这一页面级契约，见 P2。
- 本次范围内未发现预约入口、派单入口或物理释放调用被 TodayPage/provider 直接恢复；发现的越界写操作是上钟与结账，见 P1。

## 验收建议

修复以上问题后，至少执行计划指定的 dataProvider 测试、TodayPage 边界测试、管理端全量测试和 TypeScript 构建；由于这是业务边界与门店隔离修正，还应按项目协作说明完成本地及服务器只读验证后再决定发布。
