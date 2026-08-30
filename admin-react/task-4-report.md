# Task 4

## 本地完成（待 scoped 复审）

- `TodayPage` 通过 `dataProvider.getList(resources.serviceOrders)` 加载服务看板，并在整体加载失败时展示错误和“重试”。
- 移除了同 URL 的旧接口二次回退，401/403/409 保持 Provider 的统一错误契约。
- 今日运营只提供“确认服务”“服务结束”；不提供上钟、结账、预约、派单、清洁或物理释放动作。
- `dataProvider.setStoreId` 每次同步门店/会话时清空缓存，防止切换账号后复用上一门店数据。

## 涉及文件

- `src/core/auth/*`
- `src/core/dataProvider/*`
- `src/core/resources/index.ts`
- `src/pages/TodayPage.tsx`
- `src/operations.ts`
- `tests/dataProvider.test.ts`
- `tests/operations.test.ts`
- `tests/today-page-error.test.ts`

## 验证

- 定向回归：`node --experimental-strip-types --test tests/dataProvider.test.ts tests/operations.test.ts tests/today-page-error.test.ts`，18 passed。
- 尚未运行本轮管理端全量测试和生产构建；未发布生产。
