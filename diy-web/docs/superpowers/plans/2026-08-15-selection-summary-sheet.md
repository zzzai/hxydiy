# 已选项目底部清单层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 H5 左下角“已选项目”改为可查看、修改和删除条目的紧凑底部清单层，并即时展示已生效减免与预计金额。

**Architecture:** 新建纯函数模块将现有多组选择状态映射为稳定的清单视图模型，并负责无副作用的条目删除；React 弹层组件只渲染模型和派发修改/删除意图。App 继续拥有选单状态和既有详情页，通过 overlay history 叠放清单与详情页。

**Tech Stack:** React 18、TypeScript 5.6、手写 CSS、Node test runner、Lucide React。

## Global Constraints

- 内容面纯白，深绿主色，浅翠绿辅助，暖金仅用于价格和权益强调。
- 弹层不得增加转场动画。
- 只展示已经生效的减免，不展示未达成凑单提示。
- 不提供线上支付；金额文案必须明确“预计”和“最终以门店账单为准”。
- 已提交或锁定状态保持只读，不能通过弹层修改选单。
- 当前目录未检测到 Git 元数据，因此本计划不执行提交；改动以文件清单和测试证据交付。

---

### Task 1: 清单视图模型与删除规则

**Files:**
- Create: `src/selectionSummary.ts`
- Test: `tests/selection-summary.test.ts`

**Interfaces:**
- Consumes: `Project`、`Addon`、`PricingPreview`、`effectivePrice`、`addonPriceOf`。
- Produces: `buildSelectionSummary(input)`、`activePromotion(preview, isMember)`、`removeSelectionEntry(draft, target)`、`countSelectionDraft(draft)`。

- [ ] **Step 1: 写失败测试**

```ts
test('清单按主项目、挂载加项、局部调理和赠饮生成可操作条目', () => {
  const summary = buildSelectionSummary(fixture);
  assert.equal(summary.totalCount, 5);
  assert.deepEqual(summary.groups.map((item) => item.kind), ['project', 'local', 'local', 'tea']);
  assert.equal(summary.groups[0].children[0].kind, 'addon');
});

test('未达成条件不展示减免，达成后只展示实际价格带减免', () => {
  assert.equal(activePromotion(unqualifiedPreview, false), null);
  assert.equal(activePromotion(qualifiedPreview, false)?.amountCents, -3990);
});

test('删除主项目同时清理它的偏好和加项但保留独立局部调理', () => {
  const next = removeSelectionEntry(draft, { kind: 'project', projectId: 1 });
  assert.deepEqual(next.selectedProjectIds, []);
  assert.deepEqual(next.projectAddonIds, {});
  assert.deepEqual(next.localParts, ['肩颈']);
});
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm test -- tests/selection-summary.test.ts`
Expected: FAIL，因为 `src/selectionSummary.ts` 尚不存在。

- [ ] **Step 3: 实现最小纯函数**

```ts
export function removeSelectionEntry(draft: SelectionDraft, target: SelectionTarget): SelectionDraft {
  if (target.kind === 'project') {
    const projectPreferences = { ...draft.projectPreferences };
    const projectAddonIds = { ...draft.projectAddonIds };
    delete projectPreferences[target.projectId];
    delete projectAddonIds[target.projectId];
    return { ...draft, selectedProjectIds: draft.selectedProjectIds.filter((id) => id !== target.projectId), projectPreferences, projectAddonIds };
  }
  // addon、local、tea 分支只删除目标条目。
}
```

- [ ] **Step 4: 运行专项测试确认 GREEN**

Run: `node --experimental-strip-types --test tests/selection-summary.test.ts`
Expected: PASS。

### Task 2: 弹层历史与 React 交互

**Files:**
- Modify: `src/overlayHistory.ts`
- Modify: `src/App.tsx`
- Create: `src/components/SelectionSummarySheet.tsx`
- Modify: `tests/swipe-back.test.ts`

**Interfaces:**
- Consumes: Task 1 的视图模型与删除函数、App 现有 `openProjectDetail/openLocalDetail/openTeaDetail`。
- Produces: overlay kind `selection-summary`；`SelectionSummarySheet` 的 `onModify/onRemove/onClose` 事件。

- [ ] **Step 1: 写失败的历史栈测试**

```ts
test('已选清单可作为详情页下层并在返回时恢复', () => {
  const summary = createOverlayHistoryState(null, 'selection-summary');
  const detail = createOverlayHistoryState(summary, 'project-detail');
  assert.deepEqual(readOverlayHistoryStack(detail), ['selection-summary', 'project-detail']);
});
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `node --experimental-strip-types --test tests/swipe-back.test.ts`
Expected: FAIL，历史类型尚不接受 `selection-summary`。

- [ ] **Step 3: 实现弹层和 App 事件桥接**

```tsx
<SelectionSummarySheet
  open={selectionSummaryOpen}
  summary={selectionSummary}
  promotion={promotion}
  totalCents={payableTotal}
  readOnly={readOnly}
  onModify={handleSummaryModify}
  onRemove={handleSummaryRemove}
  onClose={dismissTopOverlay}
/>
```

`handleSummaryModify` 根据目标进入主项目、局部调理或茶饮详情；`handleSummaryRemove` 使用 Task 1 纯函数一次性写回全部选单状态，并在剩余数量为零时关闭弹层。

- [ ] **Step 4: 运行相关测试和类型检查确认 GREEN**

Run: `npm test`
Expected: 所有前端测试 PASS。

Run: `npx tsc --noEmit`
Expected: exit 0。
### Task 3: 移动端布局与真实交互验收

**Files:**
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: Task 2 的语义化 class 名称。
- Produces: 固定提交栏上方、最大约 55dvh、无动画的移动端清单层。

- [ ] **Step 1: 增加弹层布局样式**

```css
.selection-summary-layer { position: fixed; z-index: 49; inset: 0 0 calc(64px + env(safe-area-inset-bottom)); display: flex; align-items: flex-end; background: rgba(17,37,31,.28); }
.selection-summary-sheet { display: flex; width: 100%; max-height: min(55dvh, 460px); flex-direction: column; border-radius: 18px 18px 0 0; background: #fff; }
```

- [ ] **Step 2: 构建并启动本地页面**

Run: `npm run build`
Expected: TypeScript 和 Vite 构建 exit 0。

- [ ] **Step 3: Browser 验收目标流程**

Flow: `DIY 页面有已选项目 -> 点击左下角摘要 -> 清单层出现 -> 修改返回清单 -> 删除条目 -> 减免和预计合计更新 -> 提交按钮保持可用`。

在 390×844 与当前桌面预览宽度下检查：无横向滚动、无底栏遮挡、长清单可滚动、无框架错误层、控制台无相关 error/warn。

- [ ] **Step 4: 全套回归**

Run: `npm test`
Expected: 所有前端测试 PASS。

Run: `npx tsc --noEmit`
Expected: exit 0。
Run: `npm run build`
Expected: exit 0。

