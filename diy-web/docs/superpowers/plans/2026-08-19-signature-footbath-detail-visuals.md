# 招牌草本沐足详情视觉 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用同一荷小悦人物 IP 生成四张招牌草本沐足详情场景图，轻量接入移动端详情页并发布生产。

**Architecture:** AI 仅生成无文字的体验场景图，项目标题、服务说明和规则由 React 渲染。四张图片作为 `hxy-xiaoqi-90` 的静态详情模块，在选项区后懒加载；图片映射和文案配置集中在独立模块，避免继续扩大 `ProjectDetailPage.tsx`。

**Tech Stack:** gpt-image-2 edits API、React、TypeScript、原生 CSS、WebP、Node 测试、FastAPI 静态发布。

## Global Constraints

- 每张只出现一个荷小悦人物 IP，严格保持脸型、荷叶帽、服装、身体比例和水彩勾线。
- 基础内容面纯白，深绿为主色，浅荷叶绿辅助，暖金仅少量点缀。
- 图片无中文、数字、价格、Logo、水印、真人技师、医疗器械、人体红痕或诊疗暗示。
- 原始生成尺寸 1536×1024；前端成品约 960×640 WebP，质量约 78，目标单张 70–130 KB。
- 四张图位于项目选择内容之后、品牌故事之前，并使用原生懒加载。
- 不改变项目价格、时长、选项、会员规则或结算逻辑。

---

### Task 1: 生成并筛选四张详情场景图

**Files:**
- Read: `docs/superpowers/specs/2026-08-19-signature-footbath-detail-visual-design.md`
- Read: `C:/Users/gaoji/AppData/Local/Temp/codex-clipboard-d24b3c06-67f7-4adb-a15b-38bc206d5d58.png`
- Read: `public/assets/projects/hxy-xiaoqi-90.webp`
- Create: `C:/Users/gaoji/WorkBuddy/2026-07-31-12-31-02/tmp/imagegen/hxy-xiaoqi-90-detail-*.png`

**Interfaces:**
- Consumes: 四条已批准提示词、人物 IP 参考图、现有主图画风锚点。
- Produces: `herbal`、`release`、`signature`、`finish` 四张 1536×1024 PNG。

- [ ] **Step 1: 使用 gpt-image-2 edits API 分别生成四张原始图**
- [ ] **Step 2: 检查人物身份、单人物、服务语义、医疗化风险和移动端裁切**
- [ ] **Step 3: 仅对不合格场景使用单一针对性修正重新生成**
- [ ] **Step 4: 生成四图总览，确认整套颜色、线条和人物比例一致**

### Task 2: 生成轻量 WebP 前端资产

**Files:**
- Create: `public/assets/projects/hxy-xiaoqi-90-detail-herbal.webp`
- Create: `public/assets/projects/hxy-xiaoqi-90-detail-release.webp`
- Create: `public/assets/projects/hxy-xiaoqi-90-detail-signature.webp`
- Create: `public/assets/projects/hxy-xiaoqi-90-detail-finish.webp`

**Interfaces:**
- Consumes: Task 1 选定 PNG。
- Produces: 四张约 960×640、70–130 KB 的 WebP。

- [ ] **Step 1: 缩放并以 WebP 质量 78 导出**
- [ ] **Step 2: 验证格式、像素尺寸、文件体积和视觉清晰度**
- [ ] **Step 3: 若超出体积目标，优先逐步降低质量或减少无意义细节，不降低到主体模糊**

### Task 3: 建立项目详情视觉配置

**Files:**
- Create: `src/projectDetailVisuals.ts`
- Test: `tests/project-detail-visuals.test.ts`

**Interfaces:**
- Produces: `projectDetailVisuals(code: string): ProjectDetailVisualSection[]`。
- Type: `ProjectDetailVisualSection = { image: string; title: string; body: string; alt: string }`。

- [ ] **Step 1: 写失败测试，断言只有 `hxy-xiaoqi-90` 返回四个有序模块，且图片为 WebP**
- [ ] **Step 2: 运行 `npx tsx --test tests/project-detail-visuals.test.ts`，确认因模块不存在而失败**
- [ ] **Step 3: 实现四个模块及顾客文案，不添加医疗功效表述**
- [ ] **Step 4: 重跑目标测试，确认通过**

### Task 4: 接入详情页并保持非目标项目不变

**Files:**
- Modify: `src/components/ProjectDetailPage.tsx`
- Modify: `src/styles.css`
- Test: `tests/project-detail-visuals.test.ts`

**Interfaces:**
- Consumes: `projectDetailVisuals(project.code)`。
- Produces: 选项区之后、品牌故事之前的四段懒加载详情视觉。

- [ ] **Step 1: 扩充失败测试，检查图片使用 `loading="lazy"`、标题与正文为 HTML 文本**
- [ ] **Step 2: 运行目标测试并确认失败原因是页面尚未接入**
- [ ] **Step 3: 在 `ProjectDetailPage` 渲染配置模块，并为图片提供准确 alt**
- [ ] **Step 4: 添加纯白背景、克制留白和移动端 3:2 裁切样式，不增加转场动画**
- [ ] **Step 5: 运行目标测试、顾客端全套测试、TypeScript 检查和生产构建**

### Task 5: 同步服务器并发布生产

**Files:**
- Sync: Task 2 至 Task 4 的新增和修改文件
- Update: `/root/hxy-diy-20260811/current/MANIFEST.sha256`

**Interfaces:**
- Produces: 生产详情页可访问的四张 WebP 与对应 UI。

- [ ] **Step 1: 打包时排除 `node_modules`、`.venv` 和 `dist`，同步到 `/root/hxy-workspace`**
- [ ] **Step 2: 服务器运行后端、顾客端和管理端全套测试**
- [ ] **Step 3: 构建前端并同步到生产构建上下文，重新生成 `MANIFEST.sha256`**
- [ ] **Step 4: 运行 Docker Compose 重建生产容器**
- [ ] **Step 5: 验证健康接口、四张图片的 `200 image/webp`、页面真实加载及移动端裁切**
