# 顾客端菜单权益区与选购轻动效 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将菜单页顶部升级为方案 A 的克制权益区，并为顾客的打开、加入、查看选购和金额变化提供不干扰选购的轻反馈。

**Architecture:** 继续由 `App.tsx` 持有项目、身份、选单和覆盖层状态；顶部权益区仅消费现有的会员身份、项目和页面运营内容，不新增 API、缓存或价格计算。将 Framer Motion 的轻量预设集中在 `motionPresets.ts`，各展示组件仅根据 `useReducedMotion()` 选择正常或降级预设；所有业务状态仍由既有选单状态机决定。

**Tech Stack:** React 18、TypeScript、Framer Motion 13、Vite、Node 内置测试运行器、CSS scroll snap。

## Global Constraints

- 不新增 API、埋点字段、浏览器持久化数据、价格规则、服务位规则或跨端契约。
- 顶部权益区使用方案 A：一张主权益卡与下一张卡的轻露出；不自动轮播、不使用惯性翻页公式、倾斜、长按或夸张缩放。
- 左侧一级分类导航必须保留，仍可滚动和切换，且不被权益区遮挡。
- 只展示当前身份、门店和活动状态下真实适用的内容；匿名顾客不展示已停止的送券策略；无有效卡片时整体不渲染。
- 只动画 `opacity` 和 `transform`，时长 150–240ms；不得动画宽高、top/left、filter 或大面积 `box-shadow`。
- `prefers-reduced-motion` 时只保留短淡入淡出，不保留位移、缩放或错峰；动效不等待网络、不阻塞提交。
- 内容区域保持纯白，深绿色为主、浅绿色为辅助、暖金色仅作少量强调；不得改动项目图片原比例或详情长图规则。
- 不修改根工作区；只在 `customer-cart-auto-height` 独立 worktree 实施。每完成一个可审查任务提交一次。

---

## File Structure

| 文件 | 责任 |
| --- | --- |
| `diy-web/src/App.tsx` | 按现有身份和项目数据组装权益卡；保留分类导航；给顶部、底栏数量/金额应用共享动效。 |
| `diy-web/src/motionPresets.ts` | 定义只涉及透明度/transform 的顶部、数值替换与抽屉分段预设，并提供减少动态效果的确定性降级函数。 |
| `diy-web/src/components/ProjectDetailPage.tsx` | 详情层采用减少动态效果兼容的进入/退出预设；“加入”只提供按压反馈。 |
| `diy-web/src/components/LocalDetailPage.tsx` | 局部调理详情层采用同一降级逻辑；不改保存行为。 |
| `diy-web/src/components/TeaDetailPage.tsx` | 茶饮详情层采用同一降级逻辑；不改保存行为。 |
| `diy-web/src/components/SelectionSummarySheet.tsx` | 在保持自适应高度和焦点管理的前提下，为标题、上下文、明细、金额区添加分段进入和金额替换。 |
| `diy-web/src/styles.css` | 实现方案 A 的卡片比例、横滑提示、键盘焦点和触屏尺寸；保留分类栏与已有抽屉自适应规则。 |
| `diy-web/tests/promo-strip.test.ts` | 锁定权益区的展示条件、分类导航保留和方案 A 的滚动/无自动轮播结构。 |
| `diy-web/tests/motion-presets.test.ts` | 锁定新增预设只使用允许属性及减少动态效果降级。 |
| `diy-web/tests/motion-markup.test.ts` | 锁定顶部、详情、底栏与抽屉使用正确的动效标记和关键可访问性属性。 |
| `docs/workstreams/customer.md` | 记录本次已完成的前端体验改动、测试和生产事实。 |

### Task 1: 锁定方案 A 权益区与分类导航回归

**Files:**
- Create: `diy-web/tests/promo-strip.test.ts`
- Modify: `diy-web/tests/motion-markup.test.ts`

**Interfaces:**
- Consumes: `App.tsx` 中的 `shouldShowMembershipPromos(isMember)`、`featuredProjects(projects)` 与 `<nav className="category-nav">`。
- Produces: 对权益区存在条件、无自动轮播、横滑可达性和分类导航持续存在的回归保护。

- [ ] **Step 1: 写出失败的权益区结构测试**

```ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

test('菜单权益区采用方案 A，并保留左侧分类导航', () => {
  assert.match(app, /data-motion=["']promo-strip["']/);
  assert.match(app, /aria-label=["']到店权益["']/);
  assert.match(app, /className=["']category-nav["']/);
  assert.match(styles, /\.miniapp-promo-scroll\s*\{[^}]*scroll-snap-type:\s*x proximity/s);
  assert.match(styles, /\.miniapp-promo\s*\{[^}]*flex:\s*0 0 min\(78vw, 300px\)/s);
});

test('权益区不包含自动轮播或定时切换逻辑', () => {
  assert.doesNotMatch(app, /setInterval\([^\n]*(promo|banner|carousel)/i);
  assert.doesNotMatch(app, /autoPlay|autoplay|carouselIndex/i);
});
```

- [ ] **Step 2: 运行测试，确认它因尚未实现而失败**

Run: `npm test -- --test-name-pattern="菜单权益区|权益区不包含"`

Expected: FAIL，提示缺少 `data-motion="promo-strip"`、`miniapp-promo-scroll` 或对应 CSS。

- [ ] **Step 3: 扩展现有动效标记测试，保护抽屉语义**

```ts
test('权益区、底部选购栏和详情层声明轻动效标记', () => {
  assert.match(app, /data-motion=["']promo-strip["']/);
  assert.match(app, /data-motion=["']selection-footer["']/);
  assert.match(detail, /data-motion=["']detail["']/);
  assert.match(sheet, /data-motion=["']selection-sheet["']/);
});
```

- [ ] **Step 4: 提交测试基线**

```bash
git add diy-web/tests/promo-strip.test.ts diy-web/tests/motion-markup.test.ts
git commit -m "test(customer): cover menu promo strip behavior"
```

### Task 2: 实现方案 A 顶部权益区，且不改变分类路径

**Files:**
- Modify: `diy-web/src/App.tsx:55, 416-417, 1481-1501`
- Modify: `diy-web/src/styles.css:1039-1052, 1122-1144, 1520-1527`
- Test: `diy-web/tests/promo-strip.test.ts`

**Interfaces:**
- Consumes: `isMember: boolean`、`featured: Project[]`、`pageContent?.promo_banners`、`openMembership(kind)`、`openProjectDetail(project)`。
- Produces: `<section data-motion="promo-strip" className="miniapp-promo-strip" aria-label="到店权益">`；其中 `.miniapp-promo-scroll` 是唯一横滑容器，`<nav className="category-nav">` 保持在紧随其后的 `miniapp-catalog-layout` 中。

- [ ] **Step 1: 在 `App.tsx` 组装真实可用的权益项**

```tsx
const showMembershipPromos = shouldShowMembershipPromos(isMember);
const promoItems = [
  ...(showMembershipPromos ? [{ key: 'annual', kind: 'membership' as const, membershipKind: 'annual' as const }] : []),
  ...featured.map((project, index) => ({ key: `project-${project.id}`, kind: 'project' as const, project, index })),
];
```

仅保留既有、真实的会员卡与项目入口；不把 `featuredCoupon` 或任何已停止发放的优惠券放入 `promoItems`。`promoItems.length === 0` 时不输出 `<section>`。

- [ ] **Step 2: 用可访问的横滑容器替换当前散列卡片**

```tsx
{promoItems.length > 0 && (
  <section data-motion="promo-strip" className="miniapp-promo-strip" aria-label="到店权益">
    <div className="miniapp-promo-scroll" role="list" tabIndex={0} aria-describedby="promo-strip-hint">
      {/* membership item calls openMembership('annual'); project item calls openProjectDetail(project) */}
    </div>
    <span id="promo-strip-hint" className="sr-only">向左滑动查看更多到店权益</span>
    <span className="promo-strip-progress" aria-hidden="true"><i /><i /></span>
  </section>
)}
```

卡片按钮仍保留项目名或会员权益为可见文本；项目卡价格继续由 `priceGuidance(project, customerAuth?.user || null).primaryCents` 计算。不要更改 `openMembership`、`openProjectDetail`、`featuredProjects`、`priceGuidance` 或 `category-nav` 的状态逻辑。

- [ ] **Step 3: 在 CSS 中落实“一主一卡、次卡轻露出”**

```css
.miniapp-promo-strip { position: relative; padding: 10px 0 12px; overflow: hidden; background: #fff; }
.miniapp-promo-scroll { display: flex; gap: 10px; overflow-x: auto; padding: 0 16px 8px; scroll-snap-type: x proximity; scroll-padding-left: 16px; scrollbar-width: none; }
.miniapp-promo { flex: 0 0 min(78vw, 300px); height: 96px; scroll-snap-align: start; border-radius: 16px; }
.miniapp-promo.primary { background: linear-gradient(135deg, #176856, #0e4d40); }
.promo-strip-progress { display: flex; gap: 4px; justify-content: center; }
.promo-strip-progress i:first-child { width: 16px; background: #176856; }
.miniapp-promo-scroll:focus-visible { outline: 3px solid rgba(31, 143, 117, .35); outline-offset: -3px; }
```

将旧 `.miniapp-promo-strip` 的固定 `height: 112px` 删除，改为由卡片与内边距决定；同步更新 `.miniapp-catalog-layout` 的 `height: calc(...)`，使其只扣除最终权益区高度与底栏高度。触屏平板媒体查询使用同一逻辑，不得通过隐藏 `.category-nav` 解决空间问题。会员卡样式收敛为主卡视觉，不保留右下大圆价签。

- [ ] **Step 4: 运行权益区回归测试并检查分类导航源码仍存在**

Run: `npm test -- --test-name-pattern="菜单权益区|权益区不包含|动效标记"`

Expected: PASS；`App.tsx` 仍包含 `<nav className="category-nav" aria-label="项目分类">`。

- [ ] **Step 5: 提交权益区实现**

```bash
git add diy-web/src/App.tsx diy-web/src/styles.css diy-web/tests/promo-strip.test.ts diy-web/tests/motion-markup.test.ts
git commit -m "feat(customer): refine menu promo strip"
```

### Task 3: 建立可降级的轻动效预设

**Files:**
- Modify: `diy-web/src/motionPresets.ts`
- Modify: `diy-web/tests/motion-presets.test.ts`

**Interfaces:**
- Produces: `promoStripMotion`、`valueChangeMotion`、`sheetSectionMotion(index)` 与 `motionForPreference(preset, reduced)`。
- Consumes: 调用组件传入的 `boolean | null` 型 `useReducedMotion()` 结果；`null` 按 `false` 处理。

- [ ] **Step 1: 写出新增预设与降级规则的失败测试**

```ts
import {
  motionForPreference,
  promoStripMotion,
  sheetSectionMotion,
  valueChangeMotion,
} from '../src/motionPresets.ts';

test('新增预设只改变透明度和 transform，并有有限时长', () => {
  for (const preset of [promoStripMotion, valueChangeMotion, sheetSectionMotion(2)]) {
    assert.equal('height' in preset.animate, false);
    assert.equal('width' in preset.animate, false);
    assert.ok('opacity' in preset.animate);
    assert.ok(preset.transition.duration >= 0.15 && preset.transition.duration <= 0.24);
  }
});

test('减少动态效果时移除位移、缩放和错峰', () => {
  const reduced = motionForPreference(sheetSectionMotion(3), true);
  assert.deepEqual(reduced.initial, { opacity: 0 });
  assert.deepEqual(reduced.animate, { opacity: 1 });
  assert.equal(reduced.transition.delay, 0);
});
```

- [ ] **Step 2: 运行预设测试，确认新增导出尚不存在**

Run: `npm test -- --test-name-pattern="新增预设|减少动态效果"`

Expected: FAIL，提示 `motionForPreference`、`promoStripMotion`、`sheetSectionMotion` 或 `valueChangeMotion` 未导出。

- [ ] **Step 3: 实现受限的预设与降级函数**

```ts
export const promoStripMotion = {
  initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: 8 }, transition: { duration: 0.2, ease: 'easeOut' },
};
export const valueChangeMotion = {
  initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -6 }, transition: { duration: 0.16, ease: 'easeOut' },
};
export const sheetSectionMotion = (index: number) => ({
  initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: 8 }, transition: { duration: 0.18, delay: Math.min(index, 3) * 0.04, ease: 'easeOut' },
});
export const motionForPreference = <T extends { initial: object; animate: object; exit: object; transition: object }>(preset: T, reduced: boolean | null) => reduced
  ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.15, delay: 0, ease: 'linear' } }
  : preset;
```

保留已有 `detailMotion`、`sheetMotion`、`toastMotion` 的名称和方向；为它们补上 150–240ms transition，并由同一函数降级，不改变现有覆盖层装卸语义。

- [ ] **Step 4: 运行全部动效预设测试**

Run: `npm test -- --test-name-pattern="动效预设|新增预设|减少动态效果"`

Expected: PASS。

- [ ] **Step 5: 提交动效基础设施**

```bash
git add diy-web/src/motionPresets.ts diy-web/tests/motion-presets.test.ts
git commit -m "feat(customer): add reduced motion presets"
```

### Task 4: 接入详情、底栏与选购抽屉的真实状态反馈

**Files:**
- Modify: `diy-web/src/App.tsx:72, 1591-1602`
- Modify: `diy-web/src/components/ProjectDetailPage.tsx:22, 222-340`
- Modify: `diy-web/src/components/LocalDetailPage.tsx:5-6, 42-72`
- Modify: `diy-web/src/components/TeaDetailPage.tsx:5-6, 35-74`
- Modify: `diy-web/src/components/SelectionSummarySheet.tsx:3-6, 169-210`
- Modify: `diy-web/tests/motion-markup.test.ts`
- Test: `diy-web/tests/motion-presets.test.ts`

**Interfaces:**
- Consumes: `useReducedMotion()`、`motionForPreference`、现有 `selectedCount`、`payableTotal`、`summary.totalCount`、`saving`、`readOnly` 和全部既有 `onConfirm`/`onClose` 回调。
- Produces: 详情、底栏与抽屉都能在正常与减少动态效果模式下展示相同业务最终状态；不改变任何 `onConfirm` 返回值、提交接口或覆盖层历史。

- [ ] **Step 1: 为详情层写出减少动态效果的标记测试**

```ts
test('详情、底栏和选购抽屉均使用统一的减少动态效果降级', () => {
  for (const source of [app, sheet, detail]) {
    assert.match(source, /useReducedMotion/);
    assert.match(source, /motionForPreference/);
  }
  assert.match(sheet, /sheetSectionMotion\(0\)/);
  assert.match(sheet, /sheetSectionMotion\(3\)/);
  assert.match(app, /key=\{`selection-total-\$\{selectedCount\}-\$\{payableTotal\}`\}/);
});
```

- [ ] **Step 2: 运行测试，确认接入前失败**

Run: `npm test -- --test-name-pattern="减少动态效果降级"`

Expected: FAIL，提示对应组件尚未引用 `useReducedMotion` 或 `motionForPreference`。

- [ ] **Step 3: 接入详情和底栏，但不改变保存或提交动作**

在四个组件中调用 `const reducedMotion = useReducedMotion()` 并将原有扩展预设替换为：

```tsx
const detailMotionProps = motionForPreference(detailMotion, reducedMotion);
<motion.div data-motion="detail" {...detailMotionProps} className="...">...</motion.div>
```

`App.tsx` 的底部选购栏按 `selectedCount` 和 `payableTotal` 构造稳定 key，仅包裹数值文本：

```tsx
<AnimatePresence initial={false} mode="wait">
  <motion.strong key={`selection-total-${selectedCount}-${payableTotal}`} {...motionForPreference(valueChangeMotion, reducedMotion)}>
    {formatMoney(payableTotal)}
  </motion.strong>
</AnimatePresence>
```

不得延迟或改变 `saveProject`、`saveLocalParts`、`selectTea`、`submit`、`dismissTopOverlay`；详情按钮继续使用原生可点击语义和既有禁用条件，仅加 `whileTap={{ scale: 0.985 }}`，减少动态效果时省略该缩放。

- [ ] **Step 4: 给选购抽屉添加四段进入和金额替换**

```tsx
<motion.header {...motionForPreference(sheetSectionMotion(0), reducedMotion)} className="selection-sheet-header">...</motion.header>
<motion.div {...motionForPreference(sheetSectionMotion(1), reducedMotion)} className="selection-sheet-context">...</motion.div>
<motion.div {...motionForPreference(sheetSectionMotion(2), reducedMotion)} className="selection-sheet-scroll">...</motion.div>
<motion.footer {...motionForPreference(sheetSectionMotion(3), reducedMotion)} className="selection-sheet-total" aria-live="polite">...</motion.footer>
```

将 `summary.totalCount`、`totalCents` 的展示值放在带稳定 key 的 `AnimatePresence` 中。不得给 `.selection-summary-sheet`、`.selection-sheet-scroll`、`.selection-sheet-total` 加 `height`、`min-height` 或 `flex` 动画；保留已完成的少项自适应/多项滚动样式和关闭按钮焦点管理。

- [ ] **Step 5: 运行目标测试和 TypeScript 构建**

Run: `npm test -- --test-name-pattern="动效|选购清单|减少动态效果" && npm run build`

Expected: PASS；构建成功，无 TypeScript 报错。

- [ ] **Step 6: 提交闭环动效接入**

```bash
git add diy-web/src/App.tsx diy-web/src/components/ProjectDetailPage.tsx diy-web/src/components/LocalDetailPage.tsx diy-web/src/components/TeaDetailPage.tsx diy-web/src/components/SelectionSummarySheet.tsx diy-web/tests/motion-markup.test.ts
git commit -m "feat(customer): add selection feedback motion"
```

### Task 5: 全量验证、工作流记录与发布准备

**Files:**
- Modify: `docs/workstreams/customer.md`
- Test: `diy-web/tests/*.test.ts`

**Interfaces:**
- Consumes: 前四个任务的前端改动；不访问或变更后端数据。
- Produces: 可追溯的本地测试事实和发布前检查记录；生产事实仅由实际发布窗口在发布后写入共享状态文档。

- [ ] **Step 1: 完成工作流记录**

在 `docs/workstreams/customer.md` 顶部新增一条日期为 `2026-09-09` 的记录，包含：方案 A 顶部权益区、分类导航保留、轻动效/减少动态效果、未改 API/价格/服务位/提交契约，以及实际通过的测试命令与结果。不要把本地验证写成已发布或门店验收。

- [ ] **Step 2: 运行顾客端全量测试**

Run: `npm test`

Working directory: `diy-web`

Expected: 全部测试通过；如果已有跳过用例，保留其既有跳过原因，不把跳过计为通过。

- [ ] **Step 3: 运行生产构建和差异检查**

Run: `npm run build && git diff --check && git status --short`

Working directory: `diy-web` for build; worktree root for Git commands.

Expected: 构建成功，`git diff --check` 无输出；状态只包含本任务预期文件。

- [ ] **Step 4: 提交文档与验证记录**

```bash
git add docs/workstreams/customer.md
git commit -m "docs(customer): record menu motion verification"
```

- [ ] **Step 5: 发布后现场核验清单（仅在用户要求发布时执行）**

用匿名、非会员、会员三种身份验证：权益区只展示适用内容；左侧分类可用；横滑无自动播放；项目详情可打开/返回；加入后选购数量和金额正确；少项与多项抽屉高度正确；系统减少动态效果时操作不丢失。生产健康探针和页面加载仅证明部署可用，不替代门店触控与弱网验收。
