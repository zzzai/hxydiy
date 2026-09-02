# 顾客端页面收口与轻动效 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变业务合同的前提下，完善顾客端服务位、菜单、详情、底部选购和清单的状态反馈，并加入克制、可降级的轻动效。

**Architecture:** 继续使用现有 React/Vite 页面和纯函数业务层。动效集中在 `motionPresets.ts` 与 CSS，服务位和选单规则继续由 `positionSelection.ts`、`selectionFlow.ts`、`selectionSummary.ts` 提供；页面组件只负责状态映射和交互呈现。

**Tech Stack:** React 18、TypeScript、Vite、Framer Motion、Node test runner、CSS media queries。

## Global Constraints

- 不新增轻推荐、自动轮播、游戏化营销或价格数字滚动。
- 不修改管理后台、技师端、智慧宝物理资源流程及顾客端 API 合同。
- 会员不显示领券或会员卡推荐；价格仍区分门店价、会员价与节省金额。
- 已提交服务与待提交草稿必须分离；提交后草稿清空并在刷新后保持为空。
- 所有行为改动遵循 TDD：先写失败测试，再实现最小代码，再运行回归。
- `prefers-reduced-motion: reduce` 下保留功能与状态文字，禁用非必要动画。

### Task 1: 动效预设与低动态降级

**Files:**
- Modify: `src/motionPresets.ts`
- Modify: `src/styles.css`
- Test: `tests/motion-presets.test.ts`

**Interfaces:**
- Produces `detailMotion`, `selectionFeedbackMotion`、`sheetMotion` 和 `toastMotion` 四个仅改变 opacity/transform 的预设。

- [ ] **Step 1: Write the failing test**

```ts
test('页面动效预设只改变透明度和位移缩放，不动画布局尺寸', () => {
  for (const preset of [detailMotion, selectionFeedbackMotion, sheetMotion, toastMotion]) {
    assert.equal('width' in preset.animate, false);
    assert.equal('height' in preset.animate, false);
    assert.ok('opacity' in preset.animate || 'transform' in preset.animate || 'x' in preset.animate || 'y' in preset.animate || 'scale' in preset.animate);
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --experimental-strip-types --test tests/motion-presets.test.ts`
Expected: FAIL because the named presets do not exist.

- [ ] **Step 3: Write minimal implementation**

Export typed Framer Motion-compatible objects in `src/motionPresets.ts`; add a CSS `@media (prefers-reduced-motion: reduce)` rule covering transform/opacity transitions and `animation` without disabling scroll or focus behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --experimental-strip-types --test tests/motion-presets.test.ts`
Expected: PASS.

- [ ] **Step 5: Run existing regression**

Run: `npm test`
Expected: all existing tests remain green.

### Task 2: 服务位与菜单状态反馈

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/SeatMapDialog.tsx`
- Modify: `src/styles.css`
- Test: `tests/accessibility-markup.test.ts` or a new focused test under `tests/`

**Interfaces:**
- Consumes `resolveRequestedPosition`, `resolveActivePositionCode` and `getPositionSelectionDecision`.
- Produces visible `当前服务位`、`可切换/需前台处理` 和加载/空态/错误恢复状态，不改变权限判断。

- [ ] **Step 1: Write the failing test**

Assert that the service-position context exposes a stable status label and that menu loading/empty/error states include a user-readable status role. The test must fail against the current markup.

- [ ] **Step 2: Run test to verify it fails**

Run the focused test and confirm failure is due to missing status semantics, not a selector typo.

- [ ] **Step 3: Write minimal implementation**

Use a semantic `<button>` for the service-position context where possible, add a compact status line in the position dialog, and add `role="status"`/`role="alert"` for transient connection states. Keep QR-bound positions non-editable.

- [ ] **Step 4: Run test to verify it passes**

Run the focused test, then `npm test`.

### Task 3: 菜单与详情页轻动效

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/ProjectDetailPage.tsx`
- Modify: `src/components/TeaDetailPage.tsx`
- Modify: `src/components/LocalDetailPage.tsx`
- Modify: `src/styles.css`
- Test: `tests/accessibility-markup.test.ts`, `tests/project-detail-visuals.test.ts`

**Interfaces:**
- Consumes `detailMotion` and existing overlay history.
- Produces detail overlays with enter/exit motion and project/option selection feedback without changing price calculations or selected values.

- [ ] **Step 1: Write the failing test**

Assert that detail overlay roots include a motion class/data marker and that selection controls expose immediate pressed state. Assert no animation declaration changes width/height.

- [ ] **Step 2: Run test to verify it fails**

Run focused tests and confirm missing motion marker/transition behavior.

- [ ] **Step 3: Write minimal implementation**

Wrap detail overlays with `AnimatePresence`/`motion` using `detailMotion`; add a 120–160ms transform/color feedback class for selected options and add-to-cart buttons. Keep base image and summary card layout unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run focused tests, then `npm test` and `npm run build`.

### Task 4: 底部选购栏与清单动效及边界提示

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/components/SelectionSummarySheet.tsx`
- Modify: `src/styles.css`
- Test: `tests/selection-summary.test.ts`, `tests/submitted-selection-restore.test.ts`, new markup test if needed

**Interfaces:**
- Consumes `SelectionSummary`, `selectionSettlementNote`, `shouldHydrateStoredSelection` and `sheetMotion`.
- Produces an animated draft footer/sheet while preserving empty-draft-after-submit behavior and read-only submitted summaries.

- [ ] **Step 1: Write the failing test**

Assert that the selection sheet has a draft/submitted context label, a stable live region for total updates, and a motion marker; assert submitted restore still yields an empty draft.

- [ ] **Step 2: Run test to verify it fails**

Run focused tests and confirm the new marker/context assertion fails.

- [ ] **Step 3: Write minimal implementation**

Animate only opacity/translateY for footer and sheet, add explicit `aria-live="polite"` total updates, and show `本次待提交` vs `已提交服务` labels without changing calculations or submission handlers.

- [ ] **Step 4: Run test to verify it passes**

Run focused tests, then `npm test` and `npm run build`.

### Task 5: 端到端验证与文档更新

**Files:**
- Modify: `docs/WORK-STATUS.md`
- Test artifacts: `output/playwright/` (only if browser run is performed)

- [ ] **Step 1: Run full local verification**

Run `npm test` and `npm run build` from `diy-web`; record exact pass/fail counts.

- [ ] **Step 2: Run no-cache mobile smoke**

Use a fresh Playwright context against the production URL or local preview. Verify QR-bound service position, category scrolling, detail entry/exit, add-to-selection feedback, sheet totals, submitted/read-only boundary, refresh behavior, and console errors.

- [ ] **Step 3: Update work status**

Add a dated entry separating local completion, production publication (if any), and remaining on-site acceptance. Do not claim real-store acceptance from automation.

- [ ] **Step 4: Final review**

Check reduced-motion behavior, keyboard focus, price semantics, and no accidental changes outside顾客端源码.
