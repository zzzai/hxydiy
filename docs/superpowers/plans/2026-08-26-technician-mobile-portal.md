# 技师移动端工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有服务端业务边界的前提下，新增独立手机优先的 `/technician/` 技师端，并移除技师进入桌面管理后台的正式路径。

**Architecture:** 继续复用现有 `admin-react` 构建产物和 `/api/v1` 技师 API，但在 `App.tsx` 根据 `/technician` 入口渲染独立的移动端 React 壳；FastAPI 将同一静态资源以 `/technician` 挂载并支持真实路径回退。管理端 `/admin` 保留给管理员/店员，技师账号从 `/admin` 登录后立即被引导到 `/technician/`。

**Tech Stack:** React 18、React Router 6、Ant Design 5、Vite、FastAPI `StaticFiles`、现有 Staff/Technician API、Node test、pytest、Playwright CLI。

## Global Constraints

- 技师端只允许查看完成当前服务所必需的信息，所有数据按门店隔离。
- 所有写操作必须由服务端执行角色校验、本人技师关联校验、门店范围校验、幂等处理和审计记录。
- DIY 不承接智慧宝的开房、开沙发、派钟、离位、清洁和物理资源释放。
- 顾客画像文案使用“顾客自述/服务观察/服务注意事项”，不得记录诊断或治疗结论。
- 首期登录继续复用现有账号密码模型；手机号验证码列为后续开放问题，不在本计划新增。
- 移动端需在 320px、375px、430px 视口无横向滚动，主要动作满足触控尺寸。
- 生产发布前必须完成测试、构建、数据库备份（若无迁移也记录确认）、Manifest 校验、原子切换和线上健康检查。

---

### Task 1: 新增 `/technician` 静态入口与回退测试

**Files:**
- Modify: `hxy-server/app/release_static.py`
- Test: `hxy-server/tests/test_release_static_files.py`

**Interfaces:**
- Consumes: release root containing `admin-react/dist/index.html`.
- Produces: `GET /technician/` and nested paths serve the admin bundle index while `/admin/` behavior remains unchanged.

- [ ] **Step 1: Write the failing tests**

在 `ReleaseStaticFilesTests` 增加：

```python
def test_serves_technician_entry_and_nested_path_from_admin_bundle(self):
    with TemporaryDirectory() as directory:
        release = Path(directory)
        customer = release / "diy-web" / "dist"
        admin = release / "admin-react" / "dist"
        customer.mkdir(parents=True)
        admin.mkdir(parents=True)
        (customer / "index.html").write_text("customer app", encoding="utf-8")
        (admin / "index.html").write_text("admin bundle", encoding="utf-8")

        app = FastAPI()
        mount_release_static_files(app, release)
        client = TestClient(app)

        assert client.get("/technician/").text == "admin bundle"
        assert client.get("/technician/today").text == "admin bundle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest hxy-server/tests/test_release_static_files.py -q`

Expected: FAIL because `/technician/` is currently handled by the customer mount and does not return the admin bundle.

- [ ] **Step 3: Implement the minimal mount**

在 `mount_release_static_files` 校验 admin index 后，先挂载：

```python
app.mount("/technician", ReleaseStaticFiles(directory=admin, html=True), name="diy-technician")
app.mount("/admin", ReleaseStaticFiles(directory=admin, html=True), name="diy-admin")
```

保持 `/` customer mount 在最后，避免吞掉两个应用前缀。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest hxy-server/tests/test_release_static_files.py -q`

Expected: all release static tests PASS。

---

### Task 2: 增加入口识别和技师账号跳转契约

**Files:**
- Modify: `admin-react/src/auth.ts`
- Modify: `admin-react/src/api.ts`
- Modify: `admin-react/src/App.tsx`
- Modify: `admin-react/src/pages/LoginPage.tsx`
- Test: `admin-react/tests/auth.test.ts`

**Interfaces:**
- Consumes: `window.location.pathname`, existing `getToken`, `login` response `{ token, staff }`.
- Produces: `isTechnicianEntry()`, `getEntryLoginPath()`, `getEntryHomePath()`, and deterministic redirection for technician/admin entries.

- [ ] **Step 1: Write the failing auth tests**

在 `auth.test.ts` 增加纯函数测试（通过临时传入 pathname 参数，避免测试依赖浏览器）：

```ts
test('技师入口使用独立移动路径', () => {
  assert.equal(isTechnicianEntry('/technician/'), true);
  assert.equal(isTechnicianEntry('/technician/today'), true);
  assert.equal(isTechnicianEntry('/admin/'), false);
  assert.equal(getEntryLoginPath(true), '/technician/login');
  assert.equal(getEntryHomePath(true), '/technician/today');
});

test('技师角色不能留在管理后台入口', () => {
  assert.equal(getPostLoginRedirect('/admin/', 'technician'), '/technician/today');
  assert.equal(getPostLoginRedirect('/technician/', 'staff'), '/admin/#/today');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --runInBand`（工作目录 `admin-react`）

Expected: FAIL because the new entry helpers do not exist。

- [ ] **Step 3: Implement entry helpers and redirects**

在 `auth.ts` 新增纯函数：

```ts
export function isTechnicianEntry(pathname: string = window.location.pathname): boolean {
  return pathname === '/technician' || pathname.startsWith('/technician/');
}

export function getEntryLoginPath(technicianEntry: boolean): string {
  return technicianEntry ? '/technician/login' : '/admin/#/login';
}

export function getEntryHomePath(technicianEntry: boolean): string {
  return technicianEntry ? '/technician/today' : '/admin/#/';
}

export function getPostLoginRedirect(pathname: string, role?: string): string {
  const technicianEntry = isTechnicianEntry(pathname);
  if (role === 'technician') return '/technician/today';
  return technicianEntry ? '/admin/#/today' : '/admin/#/';
}
```

调整 `api.ts` 的 401 拦截：技师入口跳转 `getEntryLoginPath(true)`，后台入口跳转 `#/login`，不要再把技师送回桌面登录页。

调整 `LoginPage`：登录后读取 `res.data.staff.role`，技师账号在 `/admin/` 入口使用 `window.location.replace('/technician/today')`，非技师账号在 `/technician/` 入口清除 token 并提示“请使用员工后台入口”。

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- --runInBand`

Expected: all auth tests PASS。

---

### Task 3: 实现独立移动技师壳与底部导航

**Files:**
- Create: `admin-react/src/technician/TechnicianMobileApp.tsx`
- Create: `admin-react/src/technician/TechnicianMobileLoginPage.tsx`
- Create: `admin-react/src/technician/TechnicianMobileShell.tsx`
- Create: `admin-react/src/technician/technician-mobile.css`
- Modify: `admin-react/src/App.tsx`
- Modify: `admin-react/src/styles.css`
- Test: `admin-react/tests/technician-mobile.test.ts`

**Interfaces:**
- Consumes: Task 2 entry helpers and existing technician API functions.
- Produces: BrowserRouter-based routes `/technician/login`, `/technician/today`, `/technician/history`, `/technician/me`; only technician roles can render authenticated pages.

- [ ] **Step 1: Write failing route and copy tests**

新增 `technician-mobile.test.ts`，先测试导出的路由常量和状态文案：

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { TECHNICIAN_MOBILE_ROUTES, technicianStatusLabel } from '../src/technician/TechnicianMobileApp.tsx';

test('移动技师端只暴露三栏业务路由', () => {
  assert.deepEqual(TECHNICIAN_MOBILE_ROUTES, ['/technician/today', '/technician/history', '/technician/me']);
});

test('技师状态使用现场可理解文案', () => {
  assert.equal(technicianStatusLabel('waiting_service'), '待确认');
  assert.equal(technicianStatusLabel('in_service'), '服务中');
  assert.equal(technicianStatusLabel('post_service_present'), '已完成');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --runInBand`

Expected: FAIL because the mobile app module and exports do not exist。

- [ ] **Step 3: Implement mobile shell**

`TechnicianMobileApp` 使用 `BrowserRouter basename="/technician"`：

```tsx
export const TECHNICIAN_MOBILE_ROUTES = [
  '/technician/today',
  '/technician/history',
  '/technician/me',
] as const;

export function technicianStatusLabel(status: string): string {
  return ({ waiting_service: '待确认', in_service: '服务中', post_service_present: '已完成' } as Record<string, string>)[status] || '处理中';
}
```

实现要求：

- 未登录只显示 `TechnicianMobileLoginPage`。
- 已登录但角色不是 `technician` 时清理凭证并跳转 `/admin/#/today`。
- `TechnicianMobileShell` 顶部只显示门店与技师姓名，底部固定三栏“今日服务/服务记录/我的”。
- 页面内容使用 CSS 安全区、`min-height: 44px` 触控控件、单列卡片和窄屏居中容器。
- 不引入桌面 `Layout/Sider/Menu/Drawer`。

- [ ] **Step 4: Run tests and TypeScript build**

Run: `npm test -- --runInBand` and `npm run build`

Expected: mobile tests and existing tests PASS; Vite build succeeds。

---

### Task 4: 将现有服务流程改造成移动卡片和快记流程

**Files:**
- Create: `admin-react/src/technician/TechnicianTodayPage.tsx`
- Create: `admin-react/src/technician/TechnicianHistoryPage.tsx`
- Create: `admin-react/src/technician/TechnicianMePage.tsx`
- Create: `admin-react/src/technician/TechnicianProfileSheet.tsx`
- Modify: `admin-react/src/technician/TechnicianMobileApp.tsx`
- Test: `admin-react/tests/technician-mobile.test.ts`

**Interfaces:**
- Consumes: `getTechnicianMe`, `getTechnicianTasks`, `confirmTechnicianService`, `finishTechnicianService`, `createCustomerProfileRecord`.
- Produces: mobile task state machine and profile sheet with idempotent writes; no new backend mutation endpoint。

- [ ] **Step 1: Extend failing tests for task action rules**

新增纯函数测试：

```ts
test('服务状态只显示允许的主操作', () => {
  assert.deepEqual(technicianActions('waiting_service'), ['confirm']);
  assert.deepEqual(technicianActions('in_service'), ['finish']);
  assert.deepEqual(technicianActions('post_service_present'), ['profile']);
  assert.deepEqual(technicianActions('released'), []);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --runInBand`

Expected: FAIL because `technicianActions` is not implemented。

- [ ] **Step 3: Implement task pages**

`TechnicianTodayPage`：并行加载本人资料/任务，分组展示任务；按钮状态与现有 API 状态严格对应；每次写操作使用 `tech-${action}-${occupancyId}-${crypto.randomUUID()}` 幂等键，成功后刷新。

`TechnicianProfileSheet`：使用移动底部抽屉或全屏 sheet，不使用桌面 Modal；标签输入与 TextArea 文案必须是“顾客自述/服务观察/服务注意事项”，提交失败保留表单内容。

`TechnicianHistoryPage`：仅展示本人完成记录；若现有 tasks API 没有历史分页字段，则首期复用已完成任务并明确空状态，不新增跨权限接口。

`TechnicianMePage`：展示门店、技师姓名、等级和状态，提供退出登录；不展示提成、经营数据或其他技师。

- [ ] **Step 4: Run tests and build**

Run: `npm test -- --runInBand` and `npm run build`

Expected: all tests PASS and build succeeds。

---

### Task 5: 完成静态发布脚本和文档契约测试

**Files:**
- Modify: `hxy-server/tests/test_release_scripts.py`
- Modify: `docs/WORK-STATUS.md`

**Interfaces:**
- Consumes: Task 1 static mount and Task 3/4 built bundle.
- Produces: release tests that require `/technician` mount and documentation of local verification.

- [ ] **Step 1: Add release contract assertions**

在 `test_release_static_files.py` 之外，为 `test_release_scripts.py` 增加 `docker-compose`/release 契约断言，确保 release 必须包含 admin bundle（其同一 bundle 承载 technician mobile entry）且 `RUN_MIGRATIONS` 默认 false。

- [ ] **Step 2: Run backend release tests**

Run: `python -m pytest hxy-server/tests/test_release_static_files.py hxy-server/tests/test_release_scripts.py -q`

Expected: PASS。

- [ ] **Step 3: Update work status**

记录新增移动入口、涉及文件、前端/后端测试结果和“尚未发布生产”，明确旧 `/admin/#/technician` 仅作为待移除兼容路径或直接拒绝，不作为正式入口。

---

### Task 6: 移动端真实浏览器验收与生产发布

**Files:**
- No source changes unless verification finds a defect.
- Artifact: `output/playwright/technician-mobile-production.png`

**Interfaces:**
- Consumes: release from Tasks 1-5 and production test account `tech-1`.
- Produces: verified mobile login/task/action/profile flow and production release.

- [ ] **Step 1: Run complete local gates**

Run:

```powershell
cd C:\Users\gaoji\WorkBuddy\2026-07-31-12-31-02\admin-react
npm test -- --runInBand
npm run build
cd ..\hxy-server
python -m pytest tests/test_technician_portal_api.py tests/test_release_static_files.py tests/test_release_scripts.py -q
```

Expected: all selected tests PASS and production builds complete。

- [ ] **Step 2: Build release from current production baseline**

On the server, read `readlink -f /root/hxy-diy-20260811/current`; copy the current release to a new release id; replace only `admin-react/dist`; regenerate and verify `MANIFEST.sha256`. Do not overwrite a current release changed by another concurrent workflow.

- [ ] **Step 3: Activate and rebuild API without migration**

Run `sh deploy/diy/activate-release.sh <release-id>`, then rebuild/recreate API with the production `.env` and `RUN_MIGRATIONS=false`. Verify `/api/v1/health`, container status, restart count, and current symlink.

- [ ] **Step 4: Playwright mobile verification**

Open `https://diy.hexiaoyue.com/technician/` with a 390px viewport. Verify:

1. login page is mobile shell;
2. `tech-1` reaches `/technician/today`;
3. bottom navigation shows exactly three tabs;
4. no horizontal scroll;
5. task actions and profile sheet render with correct status copy;
6. `/admin/` does not render the technician desktop shell for technician credentials.

Capture `output/playwright/technician-mobile-production.png`.

- [ ] **Step 5: Update release status**

Update `docs/WORK-STATUS.md` with release id, tests, health result, screenshot path, whether database changed (expected no), production status, and remaining store现场验收 items.

