# 技师服务后快记收敛 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将技师服务结束后的默认记录收敛为 30 秒三项快记，并把身体记录改为按需的二级入口。

**Architecture:** 仅调整 `TechnicianProfileSheet` 和 `BodyMapNoteDrawer` 的展示顺序、文案与进入路径，复用 `ServiceReferenceInput`、`buildServiceReferenceV5Payload` 和既有 API。没有新字段、迁移或权限变化；源码结构测试和载荷单元测试锁定默认层与按需层的边界。

**Tech Stack:** React、TypeScript、Ant Design、Node test runner、v5 服务参考 API。

## Global Constraints

- 不新增数据库迁移，不修改 `schema_version=5`、`taxonomy_version=service_reference_v4` 或 API 字段。
- 默认页只呈现沟通方式、关键调整、结果与可选 200 字交接一句话。
- 温度、避让区域、下次提醒默认折叠；人体图不得位于常规快记默认路径。
- 自由文本只举服务交接例子；不引导收集来店原因、家庭、职业、收入、诊断或用药。
- `service_note` 仍仅对记录技师本人历史可见；不改变管理端、当前画像、跨技师摘要、营销、定价或算法边界。
- “本次无新增”保留 `recording_outcome=no_additional_notes` 语义，不能与内容或顾客确认混写。
- 所有功能改动先写失败测试，再写最小实现。

---

### Task 1: 锁定默认快记和身体按需入口

**Files:**
- Modify: `admin-react/tests/technician-workspace.test.ts`
- Modify: `admin-react/src/technician/TechnicianProfileSheet.tsx`

**Interfaces:**
- Consumes: `ServiceReferenceInput` 与 `BodyMapNoteDrawer` 的既有属性。
- Produces: 默认页只出现 `communicationPreference`、`focusAreas`、`forcePreference`、`serviceFeedback`、`serviceNote`，身体抽屉只能由独立按钮打开。

- [ ] **Step 1: 写失败测试**

```ts
test('技师快记默认层只保留三项交接，身体记录必须按需进入', () => {
  const source = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  assert.match(source, /label="顾客怎么更舒服"/);
  assert.match(source, /label="本次关键调整"/);
  assert.match(source, /label="结果与下次"/);
  assert.match(source, /label="交接一句话"/);
  assert.match(source, /需要记录身体情况/);
  assert.doesNotMatch(source, /<Collapse ghost[\s\S]{0,600}精确补充身体情况/);
});
```

- [ ] **Step 2: 运行 RED**

Run: `npm test -- technician-workspace.test.ts`

Expected: FAIL，因为字段标签和身体入口仍是旧结构。

- [ ] **Step 3: 实现最小页面变更**

```tsx
<Form.Item name="communicationPreference" label="顾客怎么更舒服"><Choices options={SERVICE_REFERENCE_OPTIONS.communication} /></Form.Item>
<Form.Item label="本次关键调整"><Form.Item name="focusAreas" noStyle><Choices multiple options={SERVICE_REFERENCE_OPTIONS.focusAreas} /></Form.Item><Form.Item name="forcePreference" noStyle><Choices options={SERVICE_REFERENCE_OPTIONS.force} /></Form.Item></Form.Item>
<Form.Item name="serviceFeedback" label="结果与下次"><Choices options={SERVICE_REFERENCE_OPTIONS.feedback} /></Form.Item>
<Form.Item name="serviceNote" label="交接一句话"><Input.TextArea rows={3} maxLength={200} showCount placeholder="例如：左肩轻一点更舒服；下次先确认" /></Form.Item>
<Button block size="large" onClick={() => setBodyNoteOpen(true)}>需要记录身体情况</Button>
```

温度、避让、下次提醒继续放在 `Collapse`；把身体抽屉入口移至折叠区之后。

- [ ] **Step 4: 运行 GREEN**

Run: `npm test -- technician-workspace.test.ts`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add admin-react/src/technician/TechnicianProfileSheet.tsx admin-react/tests/technician-workspace.test.ts
git commit -m "feat: simplify technician quick note flow"
```

### Task 2: 大部位优先，精确点位按需显示

**Files:**
- Modify: `admin-react/tests/technician-workspace.test.ts`
- Modify: `admin-react/src/technician/TechnicianProfileSheet.tsx`
- Modify: `admin-react/src/technician/BodyMapNoteDrawer.tsx`

**Interfaces:**
- Consumes: `BodyMapNoteDrawer` 的 `open`、`value`、`onChange`、`onClose` 和 `context`。
- Produces: `showPreciseMap: boolean`；身体抽屉先呈现大部位入口，点击“精确位置”才渲染当前 SVG 点位图，且不改变 `V5BodyServiceNote` 载荷。

- [ ] **Step 1: 写失败测试**

```ts
test('快记文本仅引导服务交接，身体补充先选大部位再显示精确图', () => {
  const quickNote = readFileSync(new URL('../src/technician/TechnicianProfileSheet.tsx', import.meta.url), 'utf8');
  const bodyMap = readFileSync(new URL('../src/technician/BodyMapNoteDrawer.tsx', import.meta.url), 'utf8');
  assert.match(quickNote, /左肩轻一点更舒服；下次先确认/);
  assert.doesNotMatch(quickNote, /来店原因|未满足需求/);
  assert.match(bodyMap, /肩颈/);
  assert.match(bodyMap, /精确位置/);
  assert.match(bodyMap, /showPreciseMap/);
});
```

- [ ] **Step 2: 运行 RED**

Run: `npm test -- technician-workspace.test.ts`

Expected: FAIL，因为当前提示包含“来店原因、未满足需求”，打开身体抽屉即渲染精确图。

- [ ] **Step 3: 写最小实现**

```tsx
const [showPreciseMap, setShowPreciseMap] = useState(false);
<Typography.Title level={4}>先选常用部位</Typography.Title>
<Space wrap><Button>肩颈</Button><Button>腰背</Button><Button>腿足</Button><Button>腹部</Button><Button>其他</Button></Space>
<Button type="link" onClick={() => setShowPreciseMap(true)}>精确位置</Button>
{showPreciseMap ? <ExistingBodyMap /> : null}
```

关闭抽屉时重置 `showPreciseMap`，不清空已选 `value`；大部位按钮只缩小选择范围，最终仍写入当前稳定 `region`、`side`、`context`、`currentState`、`sessionHandling` 与 `reconfirmNextVisit`。

- [ ] **Step 4: 运行 GREEN**

Run: `npm test -- technician-workspace.test.ts`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add admin-react/src/technician/TechnicianProfileSheet.tsx admin-react/src/technician/BodyMapNoteDrawer.tsx admin-react/tests/technician-workspace.test.ts
git commit -m "feat: defer technician body map detail"
```

### Task 3: 回归 v5 契约和移动端构建

**Files:**
- Verify: `admin-react/tests/technician-minimal-note.test.ts`
- Verify: `admin-react/tests/technician-workspace.test.ts`
- Modify: `docs/workstreams/technician.md`

**Interfaces:**
- Consumes: `buildServiceReferenceV5Payload(userId, selectionSessionId, values)`。
- Produces: 已验证的 UI 收敛不改变 v5 载荷、无新增语义、文字隐私边界、幂等保存或历史可见范围。

- [ ] **Step 1: 运行专项回归**

Run: `npm test -- technician-minimal-note.test.ts technician-workspace.test.ts`

Expected: PASS；`recording_outcome` 与内容仍互斥，沟通偏好仍写入 `customer_reported`，补充文字仍写入 `technician_observed`。

- [ ] **Step 2: 全量测试和构建**

Run: `npm test && npm run build`

Expected: PASS；没有 TypeScript 错误。

- [ ] **Step 3: 检查差异并记录范围**

Run: `git diff origin/main...HEAD --check`

Expected: PASS；仅包含本设计定义的移动端交互、测试和技师工作流本地实现事实。

在 `docs/workstreams/technician.md` 追加本次默认三项快记、身体按需进入和测试结果；明确不宣称合并或生产发布。

- [ ] **Step 4: 提交**

```bash
git add docs/workstreams/technician.md
git commit -m "docs: record quick note flow refinement"
```
