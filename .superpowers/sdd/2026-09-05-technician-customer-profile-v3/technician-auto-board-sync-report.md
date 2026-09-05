# 技师今日看板自动同步报告

日期：2026-09-05

## 范围与事实

- 顾客提交后，后端会把服务位占用从 `held` 更新为 `waiting_service`；技师看板现有 `getTechnicianTasks` 响应已能显示该状态。
- 本次只修改 `admin-react/src/technician/TechnicianTodayPage.tsx`：展示期间每 3 秒静默重拉看板；窗口重新获得焦点、页面由隐藏变为可见时立即重拉；卸载时清理定时器及事件监听。
- 后台刷新不设置 `loading`，不在刷新前清空 `tasks`，也不改变当前已打开的 `selectedOrder`；因此已有看板和已选订单不会被全屏 loading 或清空覆盖。
- 未引入 WebSocket、SSE、后端事件总线或跨端契约变更。未处理已知的 Alembic 夹具失败。

## TDD 证据

### RED

先在 `admin-react/tests/technician-workspace.test.ts` 添加两项行为约束：3 秒静默刷新且不触发全屏 loading/清空任务；可见性或焦点即时刷新且卸载清理。随后运行：

```powershell
node --experimental-strip-types --test tests/technician-workspace.test.ts
```

改动前结果：`14` 个测试中 `2 failed / 12 passed`；失败原因是 `TechnicianTodayPage` 尚未建立定时器、可见性和焦点监听，也没有后台刷新路径。

### GREEN

最小实现为 `load({ background: true })`：仅前台首次、手动重试或技师动作刷新会切换 loading 和展示错误；后台拉取成功后只更新服务位数据，失败保持静默。生命周期 effect 注册 3000ms 定时器与浏览器事件，并返回清理函数。

同一专项命令结果：`14 passed / 0 failed`。

## 验证

```powershell
node --experimental-strip-types --test tests/technician-workspace.test.ts  # 14 passed
npm test                                                                    # 155 passed
npm run build                                                               # passed
git diff --check                                                            # passed
```

构建仅输出项目既有的大 chunk 警告，未产生 TypeScript 或 Vite 构建错误。

## 提交与交付边界

- 提交：`f2b3bef`（`fix(technician): auto refresh today board`）。
- 本地：前端测试、构建和 diff 检查已通过。
- 推送 / PR / 合并 / 生产 / 门店验收：均未执行。
- 门店仍需用授权测试账号验证：顾客提交项目后，技师已打开的看板在最多 3 秒内出现待服务订单；从后台回到页面时立即刷新；订单抽屉保持可用。

## 复审补充：可见性与慢网竞态（2026-09-05）

复审指出原定时器即使页面隐藏也会发起请求，且慢网下连续 3 秒定时触发可能重叠，旧响应有覆盖较新看板的风险。本次最小修复：

- `refresh` 在 `document.visibilityState !== 'visible'` 时直接返回；`visibilitychange` 恢复到可见状态仍立即补拉，焦点刷新同样复用此可见性门禁。
- 使用 `activeLoads` 阻止任何在途请求期间启动新的后台轮询；手动操作可发起更新请求，但 `latestLoadRequest` 只允许最新请求更新 `me`、`tasks`、错误和 loading 状态，较旧响应不会覆盖看板。
- 后台路径继续不切换 loading、不清空 `tasks`，且不修改 `selectedOrder`。

### 复审 TDD 与验证

- RED：先新增“隐藏页面不轮询、可见后立即补拉”和“跳过在途自动刷新、只接受最新响应”的两项测试；专项结果为 `2 failed / 14 passed`，缺少可见性门禁和并发保护。
- GREEN：专项 `node --experimental-strip-types --test tests/technician-workspace.test.ts` 为 `16 passed / 0 failed`。
- 全量 `npm test`：`157 passed / 0 failed`。
- `npm run build` 与 `git diff --check`：通过；构建仅有既有大 chunk 警告。
- 提交：`84cc4c4`（`fix(technician): guard board auto refresh`）。
