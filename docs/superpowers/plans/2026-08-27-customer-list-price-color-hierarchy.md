# Customer List Price Color Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让项目列表通过克制的绿色与金色区分普通价格和会员价格，同时保持身份对应的主次层级。

**Architecture:** 保留现有 `ProjectPrice` 结构和 `projectListPricePresentation` 业务逻辑，仅在 `styles.css` 中引入三个价格语义令牌并映射匿名/非会员与会员状态。使用静态 CSS 回归测试锁定令牌和选择器映射，再以真实浏览器计算样式验证视觉结果。

**Tech Stack:** React 18、TypeScript、CSS、Node test runner、Vite、Playwright CLI。

## Global Constraints

- 仅调整顾客端项目列表卡片，不改详情页、底部选单或结算页。
- 保持单行，不增加“门店价”“可省”、色块、边框或促销标签。
- 匿名与非会员：普通价格为低饱和绿色主价格，会员参考价为低饱和金色次价格。
- 会员：会员价为低饱和金色主价格，普通价格为灰绿色删除线。
- 375px、390px、430px 下不得溢出或遮挡加购按钮。

---

### Task 1: 项目列表价格颜色语义

**Files:**
- Modify: `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\diy-web\src\styles.css`
- Create: `C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\diy-web\tests\project-list-price-colors.test.ts`
- Modify: `C:\Users\gaoji\Documents\ChatGPT\hxy-diy\docs\WORK-STATUS.md`

**Interfaces:**
- Consumes: `ProjectPrice` 输出的 `.project-meta`、`.member-price`、`.member-active` 和 `del` 结构。
- Produces: `--price-regular`、`--price-member`、`--price-reference` 三个 CSS 语义令牌及身份状态选择器映射。

- [ ] **Step 1: 写失败测试**

```ts
test('项目列表使用克制的绿色普通价和金色会员价区分身份', () => {
  const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
  assert.match(styles, /--price-regular:\s*#2f6658/i);
  assert.match(styles, /--price-member:\s*#8a6a32/i);
  assert.match(styles, /--price-reference:\s*#66736d/i);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta strong\s*\{[^}]*color:\s*var\(--price-regular\)/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta \.member-price\s*\{[^}]*color:\s*var\(--price-member\)[^}]*font-weight:\s*600/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta \.member-active strong\s*\{[^}]*color:\s*var\(--price-member\)/s);
  assert.match(styles, /\.miniapp-catalog-layout \.project-meta del\s*\{[^}]*color:\s*var\(--price-reference\)/s);
});
```

- [ ] **Step 2: 运行测试并确认因令牌尚不存在而失败**

Run: `node --experimental-strip-types --test tests/project-list-price-colors.test.ts`

Expected: FAIL，提示未匹配 `--price-regular`。

- [ ] **Step 3: 实现最小 CSS 修改**

在现有根级设计令牌中加入：

```css
--price-regular: #2f6658;
--price-member: #8a6a32;
--price-reference: #66736d;
```

把项目列表对应选择器映射到三个令牌；非会员主价格保持 20px，会员参考价改为 11px/600，会员主价格保持 20px，普通参考价保持 10px 删除线。

- [ ] **Step 4: 运行目标测试与完整测试**

Run: `node --experimental-strip-types --test tests/project-list-price-colors.test.ts`

Expected: PASS。

Run: `npm test -- --run`

Expected: 0 failed。

- [ ] **Step 5: 构建和设计检查**

Run: `npm run build`

Expected: Vite production build 成功。

Run: `node C:\Users\gaoji\.codex\skills\impeccable\scripts\detect.mjs --json src\styles.css`

Expected: 本轮选择器无新增机械设计问题。

- [ ] **Step 6: Playwright 视觉验收**

在 375px、390px、430px 下验证匿名/非会员：普通价为绿色主价格，会员价为金色次价格；验证会员：会员价为金色主价格，普通价为灰绿色删除线。所有价格保持单行且不遮挡加购按钮，并保存本地截图。

- [ ] **Step 7: 更新状态并按实时生产基线发布**

更新 `docs/WORK-STATUS.md`。读取服务器实时 `current`，从该版本复制新 release，仅替换 `diy-web/dist`，生成并校验 `MANIFEST.sha256`，激活前再次确认基线未变化；不执行数据库迁移。

- [ ] **Step 8: 线上验收**

验证公网健康接口、12 个项目、静态资源哈希、容器 `running` 且重启次数为 0，并用 Playwright 验证生产项目列表的计算颜色、单行布局、无“门店价/可省”。

