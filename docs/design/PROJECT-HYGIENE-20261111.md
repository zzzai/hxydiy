# 项目开发卫生审计

日期：2026-11-11  
范围：`hxy-diy` 工作区、生产发布、设计系统、测试、文档、资产  
性质：只读盘点 + 整改建议，不改业务代码

## 结论

当前功能能跑，但工程侧有大量“并行版本 + 手工流程 + 未收口资产”。

最危险的不是代码质量，而是：

```text
无法快速判断哪一份代码、哪一套设计、哪一个分支才是真的
```

生产当前：

```text
main:    243cde797b7f7db2c1b1abc83a7042e0ef591c61
release: github-243cde797b7f-43011413726
```

本地工作区：

```text
branch:  store-switcher
HEAD:    fe4e621
dirty:   64 个文件
untracked: 16 个文件
```

本地分支比生产落后很多，且带大量未提交改动。  
这意味着本地工作区**不能作为生产源码的可靠参照**。

---

## 1. 分支 / Worktree

### 现状

```text
git worktree: 140 个
open PR:      20 个
本地 dirty:   64 个文件
```

Worktree 覆盖大量历史主题：

```text
dsh-*（几十个后台实验）
customer-*
technician-*
store2-*
feedback-*
report-*
manager-daily-report
```

### 风险

- 同一个文件在多个 worktree 被不同版本修改
- 无法判断哪个 worktree 是当前主线
- 新会话容易在旧 worktree 上继续开发
- 发布时容易从错误基线上取文件
- CI/部署排障被历史实验干扰

### 建议

1. 冻结并归档超过 30 天未动的 worktree
2. 只保留 3 类活动 worktree：
   - 当前生产修复
   - 当前功能开发
   - 当前设计/评估
3. 所有新开发从最新 `main` 建短分支
4. 合并后 24 小时内删除分支和 worktree
5. 禁止在 worktree 里长期保留未提交改动

---

## 2. Open PR 积压

### 现状

20 个 open PR，包含：

```text
#421 #415 #292 #195 #193 #175 #127 #116 #92 #78
#77 #74 #60 #54 #53 #42 #12 #8 #7 #5
```

其中不少是历史功能、文档记录或已被后续实现覆盖的旧方案。

### 风险

- 旧 PR 可能基于旧 main，合并会回退新功能
- 评审注意力被稀释
- CI 资源浪费
- “到底哪个 PR 是当前方案”无法判断

### 建议

逐个标注：

```text
merge（仍需要）
close（已被替代/过期）
rebase（需要更新）
archive（只保留记录）
```

超过 60 天未动的 PR 默认关闭，并在描述里写替代方案。

---

## 3. 设计与 Token

### 现状

至少 4 套绿色：

```text
#197A3B  管理后台 / 品牌 v1.0
#145545  店长 P0 / 顾客端
#1f8f75  店长 P0 / 顾客端强调
#27745d  顾客端旧 token
#176856  券页面
```

同时存在：

- AntD ConfigProvider token
- 店长 `--mobile-*` 变量
- 店长 P0 硬编码 hex
- 顾客端 `--green-*` 变量
- 券页面独立 CSS

### 风险

- 同一品牌出现多种绿色
- 页面越改越像不同产品
- 新页面不知道该用哪套
- 视觉回归没有唯一基线

### 建议

1. 以根目录 `DESIGN.md` 为唯一 UI 契约
2. 建立 `design-tokens.css`，三端共享
3. 新代码禁止散落 hex
4. 按页面迁移，不做一次性全站换色
5. 先收口店长 P0 和券页面

---

## 4. 图片与资产

### 现状

- 项目主图依赖 `project.code` 映射
- 门店 2 编码使用 `s2-` 前缀，曾导致全部主图回退到同一张通用照片
- 部分项目没有专属主图，长期借用其他项目图
- `image_url` 与 generated asset 两套来源并存
- 曾出现 WebP 被 CRLF 归一化损坏，图片空白
- 本地 `astryx-pilot/`、`project-image-previews/` 不在仓库中

### 风险

- 新门店/新编码再次触发“全部同一张图”
- 二进制文件被文本工具改坏
- 新图未登记，旧图被静默覆盖
- 设计预览和仓库资产脱节

### 建议

1. 建立项目主图清单：`code -> asset -> 来源 -> 状态`
2. 编码统一使用 canonical code，不允许在 UI 层散落 `s2-` 判断
3. 二进制提交禁止 CRLF 转换
4. 缺图必须有登记和兜底规则
5. 设计预览图确认后再进入 `public/assets/projects/`

---

## 5. 测试

### 现状

```text
backend tests: 134 个文件
web tests:     51 个文件
admin tests:   74 个文件
```

测试框架并存：

- `pytest`
- Node `--test`
- React renderer
- Playwright / browser scripts
- 多个手工脚本

### 风险

- 不知道哪条命令是“全量门禁”
- 本地通过不等于生产通过
- 缺少视觉回归
- store2/登录态/券流程容易漏测
- 测试数据清理靠手工

### 建议

1. 固定三条命令：
   ```bash
   make test-api
   make test-web
   make test-admin
   ```
2. 增加关键页面截图基线：
   - 顾客菜单
   - 项目详情
   - 券包/领券
   - 店长今日
   - 店长经营
   - 后台列表
3. 所有 UI PR 必须附 390px 截图
4. 生产合成测试数据必须自动清理，不靠人工 SQL

---

## 6. 文档

### 现状

```text
docs 文件: 210 个
根目录状态文档: CURRENT-STATE / WORK-STATUS / TEAM-MEMORY / CONTROL-BOARD
```

文档覆盖了大量历史发布、workstream、验收记录。

### 风险

- 同一事实在多个文档中互相矛盾
- 新会话读到旧状态
- “当前生产是什么”需要多处交叉验证
- 设计规范和实际代码不一致

### 建议

只保留四类：

```text
CURRENT-STATE.md     当前生产/分支/发布
DESIGN.md             UI 契约
docs/contracts/       稳定业务合同
docs/operations/      发布与回滚记录
```

其余历史文档移入 `docs/archive/`，不再作为当前依据。

---

## 7. 发布流程

### 现状

- 发布走 GitHub Actions + 服务器脚本
- 迁移文件有 approved 列表
- 多次通过服务器 GitHub API 直接提交
- 本地 git 与生产 main 长期不同步
- 二进制文件曾因提交流水线被改坏
- CI 静态检查多次因 EOF 空行失败
- 部署偶发 SSH 超时，需要重试

### 风险

- 本地不是发布源
- 容易把旧文件覆盖到新 main
- 发布过程依赖人工记忆
- 回滚点不明确

### 建议

1. 所有改动必须从最新 main 建分支
2. 发布前强制：
   ```text
   git fetch
   git rebase main
   git status clean
   ```
3. 禁止在服务器上直接改业务文件
4. 发布脚本只接受通过 CI 的 SHA
5. 每次发布记录：commit、CI run、deploy run、release、health
6. 二进制文件走独立校验，不做文本归一化

---

## 8. 环境与密钥

### 现状

- 腾讯云 ASR SecretId/SecretKey 写入生产 `.env`
- 本地 Downloads 仍有密码文件、SecretKey CSV
- 生产 `.env` 有备份
- 测试合成用户/券数据曾直接写生产

### 风险

- 密钥泄漏
- 测试数据污染真实顾客表
- 环境变量与代码版本不一致

### 建议

1. 配置密钥只放服务器/密钥管理，不放仓库
2. 本地明文文件用完删除
3. 合成测试使用专用测试用户，跑完自动清理
4. `.env` 变更记录版本和备份路径
5. 定期轮换密钥

---

## 9. 业务规则不一致

### 已发现

- 会员能否领半价券：普通领券接口拒绝会员，店长分享链接允许
- 游客券打开预览不占额度，但领取后未登录仍占额度
- 店长端“待处理”超时筛选参数曾丢失
- 服务号入口曾有“进入菜单”中间页，已改直达

### 建议

把规则写进 `docs/contracts/`：

```text
coupon-policy.md
- 谁可以领
- 什么时候占额度
- 会员是否可领
- 过期/退款/作废规则
- 100 张上限口径
```

---

## 10. 生成物与临时文件

### 现状

- `vite.config.js` / `vite.config.d.ts`
- `tsconfig.app.tsbuildinfo`
- `tsconfig.node.tsbuildinfo`
- 本地 Astryx 试点、React 19 spike、图片预览
- 根目录 41 张截图

### 风险

- 生成物被误提交
- 本地实验被误认为生产方案
- 仓库体积膨胀

### 建议

- 生成物全部进 `.gitignore`
- 设计预览统一放 `docs/design/previews/` 或单独仓库
- 试点代码不进入主仓库
- 截图命名带日期和页面

---

## 优先级

### P0

1. 清理 worktree / open PR / 本地 dirty
2. 统一 DESIGN.md 和 token
3. 修复图片资产清单与编码映射
4. 生产合成数据自动清理

### P1

5. 固定测试入口和视觉回归
6. 文档归档，建立单一 CURRENT-STATE
7. 发布流程强制 rebase + clean
8. 密钥清理

### P2

9. 生成物/临时文件治理
10. 业务规则合同化
11. CI 静态检查自动化修复
12. 可观测性

---

## 建议的第一个动作

不要再开新功能分支。

先做一次“收口周”：

```text
Day 1: 关闭过期 PR，归档旧 worktree
Day 2: 合并 DESIGN.md + design-tokens
Day 3: 项目主图清单 / 编码 canonical 化
Day 4: 测试入口统一 + 截图基线
Day 5: 发布流程和 CURRENT-STATE 收口
```

在这之前，任何新 UI 改动都不应该直接进生产。
