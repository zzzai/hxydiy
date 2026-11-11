# 质量门禁

日期：2026-11-11
目标：把“乱飞”变成“有门才能过”。

五道门：

```text
版本门
设计门
资产门
测试门
发布门
```

---

## 1. 版本门

### 必须

- 新任务从最新 `main` 建短分支
- 一个任务只允许一个 worktree
- 合并后 24 小时内删除分支和 worktree
- 发布前工作区必须 clean
- 本地落后 main 时先 rebase，不允许直接覆盖
- 服务器只部署，不直接改业务文件

### 分支命名

```text
feat/<scope>-<topic>
fix/<scope>-<topic>
docs/<topic>
chore/<topic>
```

### 当前基线

```text
main: 243cde7
worktree: 140
open PR: 20
本地 dirty: 64
```

### 人工动作

- 归档 30 天未动 worktree
- 关闭过期 PR
- 开启 main 分支保护：
  - 禁止直接 push
  - 必须 PR
  - 必须 CI 绿
  - 禁止 force push
  - 生产环境 required reviewer

### 检查命令

```bash
git fetch origin
git status --short
git log --oneline -5
git worktree list
pwsh -File scripts/gates/check-version.ps1 -Release
pwsh -File scripts/gates/audit-worktrees.ps1
```

---

## 2. 设计门

### 必须

- 遵守根目录 `DESIGN.md`
- UI 改动先线框，再实现
- 附 390px 手机截图
- 涉及后台附 1280px 截图
- 附改前/改后对比
- 空 / 错 / 加载状态至少说明
- 不新增 DESIGN.md 之外的绿色、字号、圆角
- 不新增未批准插画

### PR 必须包含

```text
## 设计验收

- 页面：
- 390px 截图：
- 改前/改后：
- 空/错/加载：
- 无需视觉验收时说明原因：
```

### 自动门

`.github/workflows/quality-gates.yml` 会检查：

- 改动 `diy-web/src` 或 `admin-react/src` 的 PR
- PR 描述必须包含“设计验收”或“无需视觉验收”

### 人工门

- 设计/产品确认截图
- 不接受“我觉得好看”
- 不接受没有状态说明的 UI PR

---

## 3. 资产门

### 必须

- 每个项目 code 对应一个已存在的主图
- 门店编码先 canonical 化，再匹配资产
- 详情视觉引用的图片必须存在
- 新图先预览，确认后再进 `public/assets/projects`
- 二进制文件禁止 CRLF 归一化
- 不使用代码绘制人物插画
- 缺图必须登记，不静默借用

### 自动门

`diy-web/tests/project-assets.test.ts`：

- 检查所有可见项目主图
- 检查 `s2-` 门店编码
- 检查项目详情图片
- 检查门店 2 与基础编码的详情视觉一致

运行：

```bash
cd diy-web
npm test
```

失败处理：

- 不允许跳过
- 补图或登记兜底
- 不允许用通用照片临时顶替

### 资产清单

维护：

```text
docs/design/project-assets.json
```

字段：

```json
{
  "code": "hxy-xiangxiang-60",
  "asset": "/assets/projects/hxy-xiangxiang-60.webp",
  "source": "approved",
  "status": "active"
}
```

---

## 4. 测试门

### 固定命令

```bash
make test-api
make test-web
make test-admin
make test-all
```

等价的直接命令：

```bash
cd hxy-server && python -m pytest -q
cd diy-web && npm test
cd admin-react && npm test
```

### 必须通过

- 后端测试
- 顾客端测试 + 构建
- 管理/店长端测试 + 构建
- 静态合同
- 凭据扫描
- 空白/EOF 检查

### UI 截图基线

至少覆盖：

```text
顾客菜单
项目详情
券包 / 领券
店长今日
店长经营
后台列表
```

当前没有自动视觉回归；在建立前，用 PR 截图人工验收。

### 失败处理

- 不允许用“之前也失败”跳过
- 先确认是环境问题还是代码问题
- 环境问题记录命令和输出
- 代码问题必须修复或回滚

---

## 5. 发布门

### 必须

- main CI 绿
- 发布 commit 精确匹配 CI run
- 迁移在 `deploy/diy/deploy-production.sh` approved 列表
- 备份完成
- health 通过
- release 记录写入
- 回滚路径明确

### 发布命令

由 GitHub Actions `deploy-production.yml` 执行，输入：

```text
commit_sha
ci_run_id
```

### 发布后验证

```bash
curl -fsS https://diy.hexiaoyue.com/api/v1/health
readlink -f /root/hxy-diy-20260811/current
```

记录：

```text
commit
CI run
Deploy run
release
health
```

### 禁止

- 从旧本地 worktree 直接取文件发布
- 服务器上直接改业务代码
- 未 approved 的迁移
- 用文本工具处理二进制资产
- 发布后不记录

---

## 5.1 GitHub 分支保护状态

2026-11-11 已开启 `main` 保护：

- 禁止直接 push
- 必须通过 PR
- 必须通过 required checks：
  - Static contracts
  - Backend tests
  - Admin tests and build
  - Customer tests and build
  - Design evidence
  - Trusted PR Gate
- required checks 必须基于最新 main
- 禁止 force push
- 禁止删除 main
- 要求线性历史
- 要求解决所有 review conversation
- 管理员同样受保护

仍需人工维护：

- CODEOWNERS 的 review 要求
- 生产环境 required reviewer
- 旧 worktree / 旧 PR 清理

## 6. 当前执行顺序

### 第 1 周

1. 归档旧 worktree
2. 关闭过期 PR
3. 合并 DESIGN.md / 质量门禁
4. 开启 main 分支保护
5. 资产测试接入 CI

### 第 2 周

6. 统一 `make test-*`
7. 建立关键页面截图基线
8. 店长 P0 颜色 token 收口
9. 券页面颜色收口

### 第 3 周

10. 项目主图清单
11. 发布 checklist 执行
12. Super Agent 只在门禁内启用

---

## 7. 门禁失败时的默认动作

```text
版本门失败 → 不开始
设计门失败 → 不合并
资产门失败 → 不发布
测试门失败 → 不合并
发布门失败 → 回滚或保持上一版
```

没有例外。
例外必须由人明确批准，并写入 PR/发布记录。
